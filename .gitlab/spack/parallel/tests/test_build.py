# Copyright (c) 2026, Lawrence Livermore National Security, LLC and
# RADIUSS project contributors. SPDX-License-Identifier: (MIT)

import argparse
import contextlib
import copy
import grp
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

SCRIPT = Path(__file__).resolve().parents[1] / "build.py"
module = importlib.util.spec_from_file_location("parallel_build", SCRIPT)
build = importlib.util.module_from_spec(module)
module.loader.exec_module(build)
try:
    import spack.util.spack_yaml as sy
    import spack.schema
    import spack.schema.env
except ImportError:
    sy = None


def node(name, dependencies=(), installed=False, external=False):
    return {"name": name, "version": "1.0", "spec": name, "prefix": "/nonexistent/" + name,
            "installed": installed, "external": external,
            "dependencies": [{"hash": h, "types": types} for h, types in dependencies]}


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        source = self.root / ".gitlab/spack/envs/example"
        source.mkdir(parents=True)
        (source / "spack.yaml").write_text("spack: {}\n")
        self.environment = {
            "CI_PROJECT_DIR": str(self.root), "MY_ENV_NAME": "example",
            "RSC_MACHINE": "dane", "SPACK_TARGET": "testcpu", "CI_PIPELINE_ID": "100",
            "CI_JOB_ID": "200", "RSC_PARALLEL_STORAGE_ROOT": str(self.root / "storage"),
            "SPACK_CI_STORAGE_GROUP": grp.getgrgid(os.getgid()).gr_name,
            "RSC_SCHEDULER": "slurm", "SLURM_JOB_ID": "999", "SLURM_JOB_CPUS_PER_NODE": "8(x2)",
            "ON_CORONA": "OFF", "MY_SPACK_COMMIT": "testcommit",
        }
        self.patcher = patch.dict(os.environ, self.environment, clear=True)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        build.STOP_REQUESTED = False
        self.graph = {"roots": ["root"], "nodes": {
            "root": node("root", [("shared", ["link"]), ("tool", ["build"])]),
            "shared": node("shared"), "tool": node("tool"),
        }}

    def quiet(self):
        stack = contextlib.ExitStack()
        stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
        return stack

    def test_default_settings_and_filesystem_paths(self):
        config = build.settings()
        self.assertEqual((config["nodes"], config["wall_minutes"], config["stop_minutes"], config["packages"]), (2, 60, 55, 2))
        paths = build.paths(config)
        self.assertNotIn("/dev/shm", str(paths["pipeline"]))
        os.environ["CI_JOB_ID"] = "201"
        retry = build.paths(config)
        self.assertEqual(paths["store"], retry["store"])
        self.assertEqual(paths["environment"], retry["environment"])
        self.assertNotEqual(paths["attempt"], retry["attempt"])

    def test_case_and_node_count_separate_cold_stores(self):
        first = build.paths(build.settings())["store"]
        os.environ["RSC_PARALLEL_CASE"] = "cold-two"
        second = build.paths(build.settings())["store"]
        os.environ["RSC_PARALLEL_NODES"] = "1"
        third = build.paths(build.settings())["store"]
        self.assertEqual(len({first, second, third}), 3)

    def test_invalid_paths_and_deadlines(self):
        for value in ("../escape", "", "a/b"):
            with self.assertRaises(ValueError):
                build.segment(value, "test")
        os.environ["RSC_PARALLEL_STOP_MINUTES"] = "59"
        with self.assertRaises(ValueError):
            build.settings()
        os.environ["RSC_PARALLEL_STOP_MINUTES"] = "55"
        for value in ("/", "/dev/shm/pilot", "relative"):
            os.environ["RSC_PARALLEL_STORAGE_ROOT"] = value
            with self.assertRaises(ValueError):
                build.paths(build.settings())

    def test_corona_requires_confirmed_parameters(self):
        os.environ.pop("ON_CORONA")
        with self.assertRaisesRegex(ValueError, "confirmed CI queue"):
            build.check()
        os.environ["RSC_CORONA_PARALLEL_ALLOC"] = "--queue=confirmed-ci --nodes=2"
        with self.quiet():
            build.check()

    def test_launch_requires_allocation_and_uses_all_assigned_cpus(self):
        command = build.launch_command("slurm", 2)
        self.assertIn("--cpus-per-task=8", command)
        self.assertIn("--ntasks-per-node=1", command)
        self.assertIn("--kill-on-bad-exit=0", command)
        os.environ.pop("SLURM_JOB_ID")
        with self.assertRaises(ValueError):
            build.launch_command("slurm", 2)
        with self.assertRaises(ValueError):
            build.launch_command("flux", 2)
        os.environ["FLUX_URI"] = "local://test"
        self.assertIn("cpu-affinity=off", build.launch_command("flux", 2))

    def test_command_streams_output_and_preserves_failure(self):
        log = self.root / "command.log"
        with self.quiet():
            build.command([sys.executable, "-c", "print('completed')"], log, time.monotonic() + 5)
            with self.assertRaises(subprocess.CalledProcessError):
                build.command([sys.executable, "-c", "raise SystemExit(3)"], log, time.monotonic() + 5)
        self.assertIn("completed", log.read_text())

    def test_command_deadline_signals_child_and_calls_remote_cleanup(self):
        calls = []
        with self.quiet(), self.assertRaises(TimeoutError):
            build.command([sys.executable, "-c", "import time; print('ready', flush=True); time.sleep(20)"],
                          self.root / "deadline.log", time.monotonic() + 0.2,
                          on_interrupt=lambda: calls.append("remote-cleanup"))
        self.assertEqual(calls, ["remote-cleanup"])

    def test_flux_submission_is_awaited_and_remote_job_is_cancelled(self):
        os.environ["FLUX_URI"] = "local://test"
        attempt = self.root / "attempt"
        attempt.mkdir()
        calls = []

        def fake_command(argv, log, deadline, **kwargs):
            calls.append(argv)
            if argv[1] == "submit":
                Path(log).write_text("f123abc\n")
            else:
                kwargs["on_interrupt"]()

        with patch.object(build, "command", side_effect=fake_command), patch.object(build, "stop_flux") as stop:
            build.launch_workers(build.launch_command("flux", 2), attempt, time.monotonic() + 5)
        self.assertEqual(calls[0][:2], ["flux", "submit"])
        self.assertEqual(calls[1][:3], ["flux", "job", "attach"])
        self.assertIn("--wait-event=clean", calls[1])
        stop.assert_called_once_with("f123abc")
        self.assertEqual(build.load_json(attempt / "worker-job.json")["jobid"], "f123abc")

    def test_flux_cleanup_waits_and_escalates(self):
        calls = []

        def fake_run(argv, **kwargs):
            calls.append(argv)
            if argv[:3] == ["flux", "job", "attach"] and len(calls) < 5:
                raise subprocess.TimeoutExpired(argv, 1)

        with patch.object(build.subprocess, "run", side_effect=fake_run):
            build.stop_flux("f123abc")
        self.assertIn(["flux", "job", "kill", "--signal=SIGINT", "f123abc"], calls)
        self.assertIn(["flux", "job", "kill", "--signal=SIGTERM", "f123abc"], calls)
        self.assertIn(["flux", "cancel", "f123abc"], calls)

    def test_failure_blocks_parents_and_preserves_independent_success(self):
        graph = copy.deepcopy(self.graph)
        graph["nodes"]["tool"]["installed"] = True
        states = build.classify(self.graph, graph, {"shared": {"message": "compile failed"}}, False)
        self.assertEqual(states["root"]["state"], "blocked")
        self.assertEqual(states["shared"]["state"], "failed")
        self.assertEqual(states["tool"]["state"], "success")

    def test_cached_roots_do_not_require_missing_build_tools(self):
        graph = copy.deepcopy(self.graph)
        graph["nodes"]["root"]["installed"] = True
        graph["nodes"]["shared"]["installed"] = True
        states = build.classify(self.graph, graph, {}, False)
        self.assertEqual(states["tool"]["state"], "not-needed")
        self.assertEqual(states["root"]["state"], "success")

    def test_interruption_keeps_successes_and_external_packages(self):
        graph = copy.deepcopy(self.graph)
        graph["nodes"]["shared"]["installed"] = True
        graph["nodes"]["tool"]["external"] = True
        states = build.classify(self.graph, graph, {}, True)
        self.assertEqual(states["root"]["state"], "interrupted")
        self.assertEqual(states["shared"]["state"], "success")
        self.assertEqual(states["tool"]["state"], "external")

    def test_native_reports_deduplicate_full_hash_and_fallback_to_logs(self):
        hashes = ["a" * 32, "b" * 32]
        for rank in ("0", "1"):
            directory = self.root / "workers" / rank
            directory.mkdir(parents=True)
            (directory / "native.xml").write_text('<testsuite><testcase name="{}"><failure message="compile"/></testcase></testsuite>'.format(hashes[0]))
        (self.root / "workers/1/native.xml").write_text("<incomplete>")
        (self.root / "workers/1/install.log").write_text("[x] bbbbbbb dependency@1.0 failed: /tmp/log\n")
        outcomes, diagnostics = build.native_outcomes(self.root, hashes)
        self.assertEqual(set(outcomes), set(hashes))
        self.assertEqual(len(diagnostics), 1)

    def test_ambiguous_short_hash_is_not_assigned_to_wrong_spec(self):
        directory = self.root / "workers/0"
        directory.mkdir(parents=True)
        (directory / "install.log").write_text("[x] aaaaaaa pkg@1 failed\n")
        outcomes, _ = build.native_outcomes(self.root, ["a" * 32, "a" * 7 + "b" * 25])
        self.assertFalse(outcomes)

    def test_tree_shows_shared_dependency_once(self):
        graph = copy.deepcopy(self.graph)
        graph["nodes"]["second"] = node("second", [("shared", ["link"])])
        graph["roots"].append("second")
        states = build.classify(graph, graph, {}, True)
        tree = build.dependency_tree(graph["roots"], states)
        self.assertIn("(shown above)", tree)
        suite = build.junit(states, ["allocation failure"], 10).getroot()
        self.assertEqual(int(suite.get("tests")), len(states) + 1)

    def test_reconciliation_pushes_installed_specs_only_without_force(self):
        graph = copy.deepcopy(self.graph)
        graph["nodes"]["shared"]["installed"] = True
        graph["nodes"]["tool"].update(installed=True, external=True)
        build.write_json(self.root / "snapshot.json", graph)
        with patch.object(build, "command") as command:
            build.reconcile("spack", "env", self.root / "snapshot.json", self.root, "before", time.monotonic() + 5)
        push = command.call_args_list[0].args[0]
        self.assertEqual(push[-1], "/shared")
        self.assertNotIn("--force", push)
        self.assertIn("update-index", command.call_args_list[1].args[0])

    def test_worker_uses_filesystem_cache_and_allocation_cpu_budget(self):
        os.environ.update(RSC_ATTEMPT_ROOT=str(self.root), SLURM_PROCID="0", RSC_SPACK="spack",
                          RSC_CONCRETE_ENV="env", RSC_PARALLEL_PACKAGES="2",
                          RSC_PARALLEL_JOBS="4", RSC_STOP_EPOCH=str(time.time() + 60), MAKEFLAGS="--jobserver-auth=3,4")
        with patch.object(build.os, "sched_getaffinity", return_value=set(range(8)), create=True), patch.object(build, "command") as command:
            self.assertEqual(build.worker(), 0)
        argv = command.call_args.args[0]
        env = command.call_args.args[3]
        self.assertIn("-j4", argv)
        self.assertIn("-p2", argv)
        self.assertIn("--only-concrete", argv)
        self.assertNotIn("MAKEFLAGS", env)
        self.assertTrue(env["SPACK_USER_CACHE_PATH"].startswith(str(self.root)))
        self.assertEqual(build.load_json(self.root / "workers/0/status.json")["cpus"], 4)

    def test_worker_caps_affinity_to_slurm_step_cpu_assignment(self):
        os.environ.update(RSC_ATTEMPT_ROOT=str(self.root), SLURM_PROCID="0", RSC_SPACK="spack",
                          RSC_CONCRETE_ENV="env", RSC_PARALLEL_PACKAGES="2", SLURM_CPUS_PER_TASK="2",
                          RSC_STOP_EPOCH=str(time.time() + 60))
        with patch.object(build.os, "sched_getaffinity", return_value=set(range(8)), create=True), patch.object(build, "command") as command:
            self.assertEqual(build.worker(), 0)
        self.assertIn("-j2", command.call_args.args[0])

    def test_controller_retry_reuses_concrete_environment_and_install_store(self):
        calls = []
        installed = copy.deepcopy(self.graph)
        for value in installed["nodes"].values():
            value["installed"] = True

        def fake_command(argv, log, deadline, *args, **kwargs):
            argv = list(map(str, argv))
            calls.append(argv)
            if "snapshot" in argv:
                build.write_json(argv[-1], installed if argv[-1].endswith("after.json") else self.graph)
            if "concretize" in argv:
                (Path(argv[2]) / "spack.lock").write_text("{}")

        def fake_launch(launcher, attempt, deadline):
            for rank in ("0", "1"):
                build.write_json(attempt / "workers" / rank / "status.json", {"rank": rank, "host": "node" + rank, "cpus": 8, "returncode": 0})

        with patch.object(build, "command", side_effect=fake_command), patch.object(build, "launch_workers", side_effect=fake_launch), patch.object(build.subprocess, "check_output", return_value="testcommit\n"), self.quiet():
            self.assertEqual(build.run(), 0)
            original_paths = build.paths(build.settings())
            os.environ["CI_JOB_ID"] = "201"
            retry_start = len(calls)
            self.assertEqual(build.run(), 0)
        self.assertEqual(sum("concretize" in call for call in calls), 1)
        self.assertFalse(any("prepare" in call or "freeze" in call for call in calls[retry_start:]))
        self.assertEqual(original_paths["store"], build.paths(build.settings())["store"])
        result = build.load_json(original_paths["results"] / "results.json")
        self.assertEqual(result["counts"]["success"], 3)

    def test_collect_reports_missing_workers_and_final_snapshot(self):
        config = build.settings()
        paths = build.paths(config)
        build.write_json(paths["attempt"] / "before.json", self.graph)
        with self.quiet():
            self.assertEqual(build.collect(config, paths), 1)
        result = build.load_json(paths["results"] / "results.json")
        self.assertEqual(result["counts"]["interrupted"], 3)
        self.assertTrue(any("Expected 2 workers" in error for error in result["errors"]))
        self.assertTrue(ET.parse(paths["results"] / "junit.xml").getroot().findall("testcase"))

    @unittest.skipUnless(sy, "Run with spack python to validate Spack YAML")
    def test_gitlab_backend_selection_and_machine_inheritance(self):
        project = SCRIPT.parents[3]
        with (project / ".gitlab-ci.yml").open() as stream:
            root = sy.load(stream)
        legacy = next(item for item in root["include"] if "${MY_ENV_NAME}/pipeline.yml" in item.get("local", ""))
        optional = next(item for item in root["include"] if "parallel/pipeline.yml" in item.get("local", ""))
        self.assertIn('$RSC_BUILD_MODE != "parallel"', legacy["rules"][0]["if"])
        self.assertIn('$RSC_BUILD_MODE == "parallel"', optional["rules"][0]["if"])
        with (project / ".gitlab/spack/parallel/pipeline.yml").open() as stream:
            pipeline = sy.load(stream)
        with (project / ".gitlab/variables.yml").open() as stream:
            variables = sy.load(stream)
        for machine in build.MACHINES:
            job = pipeline["parallel-" + machine]
            self.assertEqual(job["tags"], ["batch", machine])
            self.assertIn("." + machine + "-variables", variables)
            self.assertEqual(job["variables"]["RSC_MACHINE"], machine)
            self.assertIn("SCHEDULER_PARAMETERS", job["variables"])
        self.assertEqual(pipeline[".parallel-build"]["needs"], ["parallel-configuration"])

    @unittest.skipUnless(sy, "Run with spack python to validate Spack YAML")
    def test_frozen_repository_paths_pass_spack_schema(self):
        destination = self.root / "environment"
        destination.mkdir()
        (destination / "spack.yaml").write_text("spack:\n  repos:\n    builtin:\n      git: https://example.invalid/repo.git\n      commit: pinned\n")
        repository = SimpleNamespace(namespace="builtin", root="/persistent/spack_repo/builtin")
        with patch("spack.environment.active_environment", return_value=SimpleNamespace(path=str(destination))), patch("spack.repo.PATH", SimpleNamespace(repos=[repository])):
            build.freeze()
        with (destination / "spack.yaml").open() as stream:
            data = sy.load_config(stream)
        spack.schema.Validator(spack.schema.env.schema).validate(data)
        self.assertEqual(data["spack"]["repos"]["builtin"], repository.root)

    @unittest.skipUnless(sy, "Run with spack python to validate Spack YAML")
    def test_real_environment_configuration_passes_spack_schema(self):
        project = SCRIPT.parents[3]
        for env_name in ("shared-ci", "cached-cmake"):
            destination = self.root / env_name
            shutil.copytree(project / ".gitlab/spack/envs" / env_name, destination, symlinks=False)
            build.prepare(argparse.Namespace(environment=str(destination), store=str(self.root / "install-root"), group="radiuss", cpus=1))
            with (destination / "spack.yaml").open() as stream:
                data = sy.load_config(stream)
            spack.schema.Validator(spack.schema.env.schema).validate(data)
            env = data["spack"]
            self.assertNotIn("ci.yaml", env["include"])
            self.assertTrue(env["repos"].get("builtin", {}).get("commit"))
            self.assertEqual(env["upstreams"], {})
            self.assertEqual(list(env["mirrors"]), ["parallel-pilot"])
            self.assertTrue(env["mirrors"]["parallel-pilot"]["autopush"])
            self.assertEqual(env["config"]["build_stage"], ["$user_cache_path/stage"])


if __name__ == "__main__":
    unittest.main()
