#!/usr/bin/env python3
"""Offline native Spack integration check; run with ``spack python``.

Creates only disposable fixture packages and isolated filesystem installations.
No cluster scheduler or production cache is used.
"""
# Copyright (c) 2026, Lawrence Livermore National Security, LLC and
# RADIUSS project contributors. SPDX-License-Identifier: (MIT)

import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import time

import spack.paths
import spack.environment as ev
import spack.util.spack_yaml as sy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    root = args.out.resolve()
    root.mkdir(parents=True, exist_ok=False)
    script = Path(__file__).resolve().parents[1] / "build.py"
    loader = importlib.util.spec_from_file_location("parallel_build", script)
    build = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(build)
    fixture = root / "repos/spack_repo/parallel_fixture"
    fixture.mkdir(parents=True)
    (fixture / "repo.yaml").write_text("repo:\n  api: v2.1\n")
    for name in ("parallel_leaf", "parallel_root", "parallel_independent"):
        package = fixture / "packages" / name
        package.mkdir(parents=True)
        cls = "".join(part.capitalize() for part in name.split("_"))
        dependency = '\n    depends_on("parallel-leaf", type=("link", "run"))\n' if name == "parallel_root" else ""
        (package / "package.py").write_text(
            "from spack_repo.builtin_mock.build_systems.bundle import BundlePackage\n"
            "from spack.package import version, depends_on\n\n"
            "class {}(BundlePackage):\n    version('1.0')\n{}".format(cls, dependency)
        )
    environment = root / "environment"
    environment.mkdir()
    mock = Path(spack.paths.prefix) / "var/spack/test_repos/spack_repo/builtin_mock"
    data = {"spack": {"repos": {"parallel_fixture": str(fixture), "builtin_mock": str(mock)},
                      "specs": ["parallel-root", "parallel-independent"], "view": False,
                      "concretizer": {"reuse": False, "unify": False}}}
    with (environment / "spack.yaml").open("w") as stream:
        sy.dump_config(data, stream)
    build.prepare(argparse.Namespace(environment=str(environment), store=str(root / "store"),
                                     group=__import__("grp").getgrgid(os.getgid()).gr_name, cpus=2))
    spack_executable = str(Path(spack.paths.prefix) / "bin/spack")
    env = os.environ.copy()
    env.update(SPACK_DISABLE_LOCAL_CONFIG="true", SPACK_USER_CACHE_PATH=str(root / "cache"), TMPDIR=str(root / "tmp"))
    Path(env["TMPDIR"]).mkdir()

    def run(arguments, log):
        with (root / log).open("w") as output:
            subprocess.run([spack_executable, "-e", str(environment)] + arguments, env=env,
                           stdout=output, stderr=subprocess.STDOUT, timeout=120, check=True)

    run(["concretize", "--fresh"], "concretize.log")
    run(["python", str(script), "freeze"], "freeze.log")
    run(["python", str(script), "snapshot", "--out", str(root / "before.json")], "snapshot-before.log")
    before = build.load_json(root / "before.json")
    assert len(before["nodes"]) == 3, before
    processes = []
    outputs = []
    # Two real installers share the same concrete environment and prefix locks.
    for rank in range(2):
        worker_env = dict(env, SPACK_USER_CACHE_PATH=str(root / ("worker-cache-" + str(rank))))
        output = (root / ("worker-{}.log".format(rank))).open("w")
        outputs.append(output)
        processes.append(subprocess.Popen([spack_executable, "-e", str(environment), "install", "--only-concrete", "-j2", "-p2",
                         "--log-format", "junit", "--log-file", str(root / ("worker-{}.xml".format(rank)))],
                         env=worker_env, stdout=output, stderr=subprocess.STDOUT))
    try:
        for process in processes:
            assert process.wait(timeout=120) == 0, "Inspect worker logs under {}".format(root)
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for output in outputs:
            output.close()
    run(["python", str(script), "snapshot", "--out", str(root / "after.json")], "snapshot-after.log")
    after = build.load_json(root / "after.json")
    assert all(n["installed"] for n in after["nodes"].values()), after
    # Autopush should already have published each source installation.
    from spack.url_buildcache import URLBuildcacheEntry, BuildcacheComponent
    concrete = ev.Environment(environment)
    for h in after["nodes"]:
        spec = concrete.specs_by_hash.get(h)
        if spec is None:
            spec = next(s for s in concrete.all_specs() if s.dag_hash() == h)
        entry = URLBuildcacheEntry((root / "store/buildcache").as_uri(), spec=spec, allow_unsigned=True)
        assert entry.exists([BuildcacheComponent.SPEC, BuildcacheComponent.TARBALL]), h
    # Reconciliation is a no-op for complete uploads, and native retry reuses them.
    os.environ.update(env)
    build.reconcile(spack_executable, str(environment), root / "after.json", root, "after", time.monotonic() + 120)
    run(["install", "--only-concrete", "-j2", "-p2"], "retry.log")
    # Simulate missing uploads with an empty destination, retaining the original
    # buildcache. Reconciliation must publish already-installed packages.
    with (environment / "spack.yaml").open() as stream:
        recovered = sy.load_config(stream)
    mirror = recovered["spack"]["mirrors"]["parallel-pilot"]
    mirror["url"] = (root / "recovered-buildcache").as_uri()
    build.write_manifest(environment / "spack.yaml", recovered, sy)
    build.reconcile(spack_executable, str(environment), root / "after.json", root, "recovered", time.monotonic() + 120)
    for h in after["nodes"]:
        spec = next(s for s in concrete.all_specs() if s.dag_hash() == h)
        entry = URLBuildcacheEntry(mirror["url"], spec=spec, allow_unsigned=True)
        assert entry.exists([BuildcacheComponent.SPEC, BuildcacheComponent.TARBALL]), h
    # Restore into a new install tree entirely from binaries; no removal of the
    # original prefixes or source-build fallback is necessary.
    recovered["spack"]["config"]["install_tree"]["root"] = str(root / "restored-install")
    build.write_manifest(environment / "spack.yaml", recovered, sy)
    run(["install", "--only-concrete", "--use-buildcache", "only", "-j2", "-p2"], "restore.log")
    run(["python", str(script), "snapshot", "--out", str(root / "restored.json")], "snapshot-restored.log")
    restored = build.load_json(root / "restored.json")
    assert all(n["installed"] and n["prefix"].startswith(str(root / "restored-install")) for n in restored["nodes"].values()), restored
    states = build.classify(before, after, {}, False)
    (root / "tree.txt").write_text(build.dependency_tree(after["roots"], states))
    print("Native concurrent installation, autopush, missing-upload recovery, retry and binary restore passed: {}".format(root))


if __name__ == "__main__":
    main()
