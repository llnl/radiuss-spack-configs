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
from rad_bat.workflows import _git_checkout, run_spack


SPACK_COMMIT = "2a4c87fd44bd303643c0b0e0d7ed6fe1d1a23937"


def write_config(root: Path, command=None) -> None:
    document = {
        "schema_version": 1,
        "project": {
            "package": "umpire",
            "command": command or ["project-driver", "{host_config}", "{work_dir}", "{jobs}"],
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
            write_config(root, ["project-driver", "--prefix={work_dir}"])
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
            expand_command(["driver", "{work_dir}"], {"work_dir": "/tmp/build"}),
            ["driver", "/tmp/build"],
        )

    def test_rejects_partial_arguments(self):
        with self.assertRaisesRegex(RadBatError, "partial"):
            expand_command(["--work-dir={work_dir}"], {"work_dir": "/tmp/build"})


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
            with mock.patch("rad_bat.workflows.run_command") as command:
                self.assertEqual(cli.main([
                    "host-config", "--source", str(root),
                    "--host-config", str(host_config),
                    "--work-dir", "work with spaces", "--jobs", "3",
                ]), 0)
            command.assert_called_once()
            self.assertEqual(command.call_args.args[0][0], "project-driver")
            self.assertIn(str(host_config.resolve()), command.call_args.args[0])
            self.assertIn(str((root / "work with spaces").resolve()), command.call_args.args[0])
            self.assertTrue((root / "work with spaces").is_dir())

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
            install_tree = root / "persistent-install"
            output_dir = root / "artifacts"
            with mock.patch.dict(os.environ, {"SYS_TYPE": "test-system"}, clear=False), mock.patch(
                "rad_bat.workflows._git_checkout", side_effect=fake_checkout
            ), mock.patch("rad_bat.workflows.run_command", side_effect=fake_command):
                run_spack(
                    config,
                    "+tools",
                    str(destination),
                    None,
                    str(install_tree),
                    str(output_dir),
                    [],
                    "oci://registry.invalid/project",
                    "CI_REGISTRY_USER",
                    "CI_JOB_TOKEN",
                    False,
                    "job.cmake",
                    4,
                    None,
                )

            retained = output_dir / "job.cmake"
            self.assertTrue(retained.is_file())
            flattened = [argument for command in commands for argument in command]
            self.assertIn("concretize", flattened)
            self.assertIn("initconfig", flattened)
            self.assertIn(
                "config:install_tree:root:{}".format(install_tree.resolve()), flattened
            )
            add_command = next(
                command for command in commands
                if len(command) == 5 and command[-2] == "add"
            )
            self.assertIn("umpire@develop +tools", add_command)
            mirror_command = next(command for command in commands if "mirror" in command)
            self.assertIn("--oci-username-variable", mirror_command)
            self.assertIn("CI_REGISTRY_USER", mirror_command)
            self.assertIn("--oci-password-variable", mirror_command)
            self.assertIn("CI_JOB_TOKEN", mirror_command)
            repo_command = next(command for command in commands if "repo" in command)
            self.assertEqual(
                repo_command[1:3],
                ["-e", str(destination.resolve() / ".rad-bat" / "spack-env")],
            )
            self.assertEqual(repo_command[3:5], ["repo", "add"])
            self.assertIn("oci://registry.invalid/project", mirror_command)
            self.assertEqual(commands[-1][0], "project-driver")
            self.assertIn(str(destination.resolve()), commands[-1])

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
                    None,
                    None,
                    [],
                    None,
                    None,
                    None,
                    True,
                    None,
                    1,
                    None,
                )


class EnvironmentTests(unittest.TestCase):
    def test_bare_command_maps_host_config_name_and_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_config(root)
            environment = {
                "RAD_BAT_MODE": "host-config",
                "RAD_BAT_SOURCE_DIR": str(root),
                "RAD_BAT_HOST_CONFIG_DIR": "maintained-host-configs",
                "RAD_BAT_HOST_CONFIG_NAME": "job.cmake",
                "RAD_BAT_WORK_DIR": str(root / "work"),
                "RAD_BAT_JOBS": "2",
            }
            with mock.patch.dict(os.environ, environment, clear=True), mock.patch(
                "rad_bat.cli.run_host_config"
            ) as workflow:
                self.assertEqual(cli.main([]), 0)
            self.assertEqual(
                workflow.call_args.args[1],
                str(Path("maintained-host-configs") / "job.cmake"),
            )
            self.assertEqual(workflow.call_args.args[2], str(root / "work"))
            self.assertEqual(workflow.call_args.args[3], 2)

    def test_missing_host_config_does_not_fall_back_to_spack(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_config(root)
            environment = {
                "RAD_BAT_MODE": "host-config",
                "RAD_BAT_SOURCE_DIR": str(root),
                "RAD_BAT_HOST_CONFIG_DIR": "host-configs",
                "RAD_BAT_HOST_CONFIG_NAME": "missing.cmake",
            }
            with mock.patch.dict(os.environ, environment, clear=True), mock.patch(
                "rad_bat.cli.run_spack"
            ) as spack_workflow:
                self.assertEqual(cli.main([]), 2)
            spack_workflow.assert_not_called()

    def test_ci_spack_requires_persistent_install_tree(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_config(root)
            environment = {
                "RAD_BAT_MODE": "spack",
                "RAD_BAT_SOURCE_DIR": str(root),
                "RAD_BAT_SPEC": "umpire@develop",
                "RAD_BAT_WORK_DIR": str(root / "work"),
            }
            with mock.patch.dict(os.environ, environment, clear=True):
                self.assertEqual(cli.main([]), 2)

    def test_ci_spack_maps_install_tree_and_output_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_config(root)
            environment = {
                "RAD_BAT_MODE": "spack",
                "RAD_BAT_SOURCE_DIR": str(root),
                "RAD_BAT_SPEC": "umpire@develop",
                "RAD_BAT_WORK_DIR": str(root / "work"),
                "RAD_BAT_INSTALL_TREE": str(root / "persistent"),
                "RAD_BAT_OUTPUT_DIR": str(root / "artifacts"),
                "RAD_BAT_BUILDCACHE": "oci://registry.invalid/project",
                "RAD_BAT_BUILDCACHE_USERNAME_VARIABLE": "CI_REGISTRY_USER",
                "RAD_BAT_BUILDCACHE_PASSWORD_VARIABLE": "CI_JOB_TOKEN",
            }
            with mock.patch.dict(os.environ, environment, clear=True), mock.patch(
                "rad_bat.cli.run_spack"
            ) as workflow:
                self.assertEqual(cli.main([]), 0)
            self.assertEqual(workflow.call_args.args[4], str(root / "persistent"))
            self.assertEqual(workflow.call_args.args[2], str(root / "work"))
            self.assertEqual(workflow.call_args.args[5], str(root / "artifacts"))
            self.assertEqual(workflow.call_args.args[7], "oci://registry.invalid/project")
            self.assertEqual(workflow.call_args.args[8], "CI_REGISTRY_USER")
            self.assertEqual(workflow.call_args.args[9], "CI_JOB_TOKEN")


if __name__ == "__main__":
    unittest.main()
