#!/usr/bin/env python3
"""Map RADIUSS CI settings to rad-bat; Jacamar owns the allocation."""

import argparse
import grp
import json
import os
import re
from pathlib import Path
import shutil
import stat
import sys
import xml.etree.ElementTree as ET
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from rad_bat.environment import EnvironmentOptions, run_environment

MACHINES = ("corona", "dane", "tioga", "tuolumne")


def segment(value, name):
    if not value or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value) or value in (".", ".."):
        raise ValueError("{} must be a single safe path component".format(name))
    return value


def positive(name, default):
    value = int(os.environ.get(name, default))
    if value < 1:
        raise ValueError("{} must be positive".format(name))
    return value


def ensure_directory(path, group):
    path.mkdir(exist_ok=True)
    gid = grp.getgrnam(group).gr_gid
    if path.stat().st_gid != gid:
        os.chown(path, -1, gid)
    path.chmod(stat.S_IMODE(path.stat().st_mode) | stat.S_ISGID | 0o070)


def settings():
    project = Path(os.environ.get("CI_PROJECT_DIR", os.getcwd())).resolve()
    env_name = segment(os.environ["MY_ENV_NAME"], "MY_ENV_NAME")
    source = project / ".gitlab/spack/envs" / env_name
    if not (source / "spack.yaml").is_file():
        raise ValueError("No environment manifest at {}".format(source))
    nodes = positive("RSC_PARALLEL_NODES", "1")
    wall = positive("RSC_PARALLEL_TIME_MINUTES", "60")
    stop = positive("RSC_PARALLEL_STOP_MINUTES", "55")
    if wall - stop < 5:
        raise ValueError("Reserve at least five minutes between soft stop and allocation expiry")
    return {
        "project": project, "source": source, "environment": env_name,
        "nodes": nodes, "wall_minutes": wall, "stop_minutes": stop,
        "packages": positive("RSC_PARALLEL_PACKAGES", "2"),
    }


def check():
    settings()
    if os.environ.get("ON_CORONA") != "OFF" and not os.environ.get("RSC_CORONA_PARALLEL_ALLOC", "").strip():
        raise ValueError("Set ON_CORONA=OFF or supply RSC_CORONA_PARALLEL_ALLOC with confirmed CI queue parameters")
    print("Parallel backend configuration accepted; Jacamar owns each allocation.")


def paths(config):
    machine = segment(os.environ["RSC_MACHINE"], "RSC_MACHINE")
    if machine not in MACHINES:
        raise ValueError("Unsupported machine: {}".format(machine))
    root = Path(os.environ.get("RSC_PARALLEL_STORAGE_ROOT", "/usr/workspace/radiuss/rsc-ci-parallel-pilot"))
    if not root.is_absolute() or root == Path("/") or str(root).startswith("/dev/shm"):
        raise ValueError("RSC_PARALLEL_STORAGE_ROOT must be a persistent absolute filesystem path")
    store = root / config["environment"] / machine
    for name, default in (("SPACK_TARGET", None), ("CACHE_TARGET", "manual"), ("RSC_PARALLEL_CASE", "pilot")):
        store /= segment(os.environ.get(name, default), name)
    pipeline = store / "pipelines" / segment(os.environ["CI_PIPELINE_ID"], "CI_PIPELINE_ID")
    # GitLab keeps the job name on retries, but assigns a new CI_JOB_ID.
    job_name = os.environ["CI_JOB_NAME"]
    if not job_name or job_name in (".", ".."):
        raise ValueError("CI_JOB_NAME must identify a job")
    workspace = pipeline / "jobs" / quote(job_name, safe="")
    attempt = workspace / "attempts" / segment(os.environ["CI_JOB_ID"], "CI_JOB_ID")
    return {"machine": machine, "store": store, "pipeline": pipeline,
            "workspace": workspace, "attempt": attempt, "temporary": root / "tmp" / os.environ["CI_JOB_ID"],
            "results": config["project"] / "parallel-results" / machine / os.environ["CI_JOB_ID"]}


def main_storage(config, machine):
    """Use the same main-generation reuse sources as configure-storage.sh."""
    root = Path(os.environ.get("SPACK_CI_STORAGE_ROOT", "/usr/workspace/radiuss/rsc-ci"))
    return root / config["environment"] / machine / os.environ["SPACK_TARGET"] / "main"


def run():
    config = settings()
    p = paths(config)
    if os.environ.get("LCSCHEDCLUSTER", p["machine"]) != p["machine"]:
        raise ValueError("Runner machine does not match RSC_MACHINE")
    os.environ["LCSCHEDCLUSTER"] = p["machine"]
    os.umask(0o002)
    group = os.environ.get("SPACK_CI_STORAGE_GROUP", "radiuss")
    storage = Path(os.environ.get("RSC_PARALLEL_STORAGE_ROOT", "/usr/workspace/radiuss/rsc-ci-parallel-pilot"))
    storage.parent.mkdir(parents=True, exist_ok=True)
    for target in (p["attempt"], p["temporary"]):
        for path in [storage] + list(reversed([x for x in target.parents if storage in x.parents])) + [target]:
            ensure_directory(path, group)
    options = EnvironmentOptions(
        environment=str(config["source"]), work_dir=str(p["workspace"]),
        install_tree=str(p["store"] / "install"), output_dir=str(p["attempt"]),
        temp_dir=str(p["temporary"]), spack_url=os.environ["MY_SPACK_REPO"],
        spack_commit=os.environ["MY_SPACK_COMMIT"], scheduler=os.environ["RSC_SCHEDULER"],
        nodes=config["nodes"], packages=config["packages"],
        stop_after=config["stop_minutes"] * 60, finish_after=config["wall_minutes"] * 60 - 30,
        group=group, buildcache=(p["store"] / "buildcache").as_uri(), push_to_buildcache=True,
        jobs=positive("RSC_PARALLEL_JOBS", "1") if os.environ.get("RSC_PARALLEL_JOBS") else None,
        lockfile=os.environ.get("RSC_PARALLEL_LOCKFILE"),
    )
    main = main_storage(config, p["machine"])
    if (main / "install/.spack-db/index.json").is_file():
        options.upstream = [str(main / "install")]
    options.read_buildcache = [(main / "buildcache").as_uri()]
    return run_environment(options)


def collect():
    p = paths(settings())
    results = p["results"]
    results.mkdir(parents=True, exist_ok=True)
    # Persist native reports/logs, excluding potentially large worker cache directories.
    for pattern in ("*.log", "*.json", "spack.yaml", "spack.lock", "workers/*/*.log",
                    "workers/*/*.json", "workers/*/*.xml"):
        for source in p["attempt"].glob(pattern):
            destination = results / source.relative_to(p["attempt"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
    status_file = p["attempt"] / "status.json"
    state = json.loads(status_file.read_text()) if status_file.exists() else {}
    suite = ET.Element("testsuite", name="environment-install", tests="1")
    case = ET.SubElement(suite, "testcase", name=p["machine"])
    if not state.get("complete"):
        ET.SubElement(case, "failure", message=state.get("error") or "Job interrupted before finalization")
        suite.set("failures", "1")
    ET.ElementTree(suite).write(results / "junit.xml", encoding="utf-8", xml_declaration=True)
    if os.environ.get("RSC_PARALLEL_REPORT", "ON") != "OFF":
        try:
            from rad_bat.report import dependency_report
            tree = dependency_report(results)
            (results / "tree.txt").write_text(tree)
            print(tree, end="")
        except Exception as error:
            print("Optional dependency report unavailable: {}".format(error))
    print("Environment results: {}".format(results))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check", "run", "collect"))
    try:
        actions = {"check": check, "run": run, "collect": collect}
        sys.exit(actions[parser.parse_args().action]() or 0)
    except Exception as error:
        print("[Error] {}".format(error), file=sys.stderr)
        sys.exit(1)
