"""Tests for the rad-bat generic workflow."""

import json
import io
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from rad_bat import cli, logs
from rad_bat.config import load_project_config
from rad_bat.errors import RadBatError
from rad_bat.runner import expand_command
from rad_bat.workflows import _git_checkout, run_host_config, run_spack


SPACK_COMMIT = "2a4c87fd44bd303643c0b0e0d7ed6fe1d1a23937"


def write_config(root: Path, command=None) -> None:
    document = {
        "schema_version": 1,
        "project": {
            "package": "umpire",
            "command": command or ["project-driver", "{host_config}", "{jobs}"],
        },
        "spack": {
            "url": "https://example.invalid/spack.git",
            "commit": SPACK_COMMIT,
            "environment": "machine/{sys_type}/spack.yaml",
            "repositories": [{"path": "local-repo"}],
        },
    }
    (root / ".rad-bat.json").write_text(json.dumps(document), encoding="utf-8")


class ConfigTests(unittest.TestCase):
    def test_valid_config(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_config(root)
            config = load_project_config(root)
            self.assertEqual(config.package, "umpire")
            self.assertEqual(config.spack.commit, SPACK_COMMIT)

    def test_rejects_partial_placeholder(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_config(root, ["project-driver", "--prefix={dest}"])
            with self.assertRaisesRegex(RadBatError, "partial placeholder"):
                load_project_config(root)

    def test_rejects_moving_spack_reference(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_config(root)
            document = json.loads((root / ".rad-bat.json").read_text(encoding="utf-8"))
            document["spack"]["commit"] = "develop"
            (root / ".rad-bat.json").write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(RadBatError, "full 40-character"):
                load_project_config(root)


class RunnerTests(unittest.TestCase):
    def test_expands_whole_arguments(self):
        self.assertEqual(
            expand_command(["driver", "{dest}"], {"dest": "/tmp/build"}),
            ["driver", "/tmp/build"],
        )

    def test_rejects_partial_arguments(self):
        with self.assertRaisesRegex(RadBatError, "partial"):
            expand_command(["--dest={dest}"], {"dest": "/tmp/build"})


class LogTests(unittest.TestCase):
    def test_section_context_is_inherited_and_nested(self):
        environment = {key: value for key, value in os.environ.items() if key not in {
            logs.START_ENV, logs.DEPTH_ENV
        }}
        output = io.StringIO()
        with mock.patch.dict(os.environ, environment, clear=True), mock.patch(
            "rad_bat.logs.time.time", side_effect=[100, 101, 102, 103, 104, 105]
        ), redirect_stdout(output):
            parent = logs.SectionManager()
            with parent.section("parent", "Parent"):
                self.assertEqual(os.environ[logs.START_ENV], "100")
                self.assertEqual(os.environ[logs.DEPTH_ENV], "1")
                child = logs.SectionManager()
                self.assertEqual(child.start, 100)
                self.assertEqual(child.base_depth, 1)
                with child.section("child", "Child"):
                    self.assertEqual(os.environ[logs.DEPTH_ENV], "2")
                self.assertEqual(os.environ[logs.DEPTH_ENV], "1")
            self.assertNotIn(logs.DEPTH_ENV, os.environ)

        text = output.getvalue()
        self.assertIn("~ Parent", text)
        self.assertIn("  ~ Child", text)

    def test_command_uses_shell_safe_quoting(self):
        output = io.StringIO()
        with redirect_stdout(output):
            logs.command(["tool", "argument with spaces"])
        self.assertEqual(output.getvalue(), "+ tool 'argument with spaces'\n")


class WorkflowTests(unittest.TestCase):
    def test_pinned_checkout_preserves_isolation_changes_when_commit_matches(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            origin = root / "origin"
            origin.mkdir()
            subprocess.run(["git", "init", str(origin)], check=True, stdout=subprocess.DEVNULL)
            subprocess.run(
                ["git", "-C", str(origin), "config", "user.email", "rad-bat@example.invalid"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(origin), "config", "user.name", "rad-bat test"],
                check=True,
            )
            tracked = origin / "include.yaml"
            tracked.write_text("original\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(origin), "add", "include.yaml"], check=True)
            subprocess.run(
                ["git", "-C", str(origin), "commit", "-m", "initial"],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            commit = subprocess.check_output(
                ["git", "-C", str(origin), "rev-parse", "HEAD"], universal_newlines=True
            ).strip()
            checkout = root / "checkout"
            _git_checkout(str(origin), commit, checkout)
            (checkout / "include.yaml").write_text("isolated\n", encoding="utf-8")
            _git_checkout(str(origin), commit, checkout)
            self.assertEqual(
                (checkout / "include.yaml").read_text(encoding="utf-8"), "isolated\n"
            )

    def test_host_config_mode_only_runs_project_command(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_config(root)
            host_config = root / "existing.cmake"
            host_config.touch()
            config = load_project_config(root)
            with mock.patch("rad_bat.workflows.run_command") as command:
                run_host_config(config, str(host_config), None, 3, None)
            command.assert_called_once()
            self.assertEqual(command.call_args.args[0][0], "project-driver")
            self.assertIn(str(host_config.resolve()), command.call_args.args[0])

    def test_spack_mode_prepares_dependencies_and_retains_host_config(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_config(root)
            (root / "machine" / "test-system").mkdir(parents=True)
            (root / "machine" / "test-system" / "spack.yaml").write_text(
                "spack:\n  view: false\n", encoding="utf-8"
            )
            (root / "local-repo").mkdir()
            (root / "local-repo" / "repo.yaml").write_text(
                "repo:\n  namespace: test\n", encoding="utf-8"
            )
            config = load_project_config(root)
            commands = []

            def fake_checkout(url, commit, destination):
                del url, commit
                (destination / ".git").mkdir(parents=True)
                (destination / "bin").mkdir()
                (destination / "bin" / "spack").touch()

            def fake_command(command, cwd=None, env=None):
                del env
                commands.append(command)
                if "isolate" in command:
                    checkout = Path(command[0]).parents[1]
                    (checkout / "etc" / "spack" / "isolate").mkdir(parents=True)
                if "install" in command:
                    (Path(cwd) / "umpire-test.cmake").write_text(
                        "# generated\n", encoding="utf-8"
                    )

            destination = root / "destination"
            with mock.patch.dict(os.environ, {"SYS_TYPE": "test-system"}, clear=False), mock.patch(
                "rad_bat.workflows._git_checkout", side_effect=fake_checkout
            ), mock.patch("rad_bat.workflows.run_command", side_effect=fake_command):
                run_spack(
                    config,
                    "umpire@develop +tools",
                    str(destination),
                    None,
                    [],
                    None,
                    False,
                    "job.cmake",
                    4,
                    None,
                )

            retained = destination / "host-configs" / "job.cmake"
            self.assertTrue(retained.is_file())
            flattened = [argument for command in commands for argument in command]
            self.assertIn("concretize", flattened)
            self.assertIn("initconfig", flattened)
            self.assertNotIn("buildcache", flattened)
            self.assertEqual(commands[-1][0], "project-driver")

    def test_buildcache_push_requires_a_buildcache(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_config(root)
            config = load_project_config(root)
            with self.assertRaisesRegex(RadBatError, "requires --buildcache"):
                # Validate this before any external work by using a deliberately
                # missing destination setup.
                run_spack(
                    config,
                    "umpire@develop",
                    str(root / "destination"),
                    None,
                    [],
                    None,
                    True,
                    None,
                    1,
                    None,
                )


class CiTests(unittest.TestCase):
    def test_ci_host_config_maps_legacy_job_variable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_config(root)
            environment = {
                "RAD_BAT_MODE": "host-config",
                "RAD_BAT_SOURCE_DIR": str(root),
                "HOST_CONFIG": "job.cmake",
                "RAD_BAT_JOBS": "2",
            }
            with mock.patch.dict(os.environ, environment, clear=True), mock.patch(
                "rad_bat.cli.run_host_config"
            ) as workflow:
                self.assertEqual(cli.main(["ci"]), 0)
            self.assertEqual(workflow.call_args.args[1], "job.cmake")
            self.assertEqual(workflow.call_args.args[3], 2)


if __name__ == "__main__":
    unittest.main()
