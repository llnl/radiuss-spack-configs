"""Observable design contracts: replay, machine selection and project handoff."""

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from rad_bat import cli, runner, spack, spack_helpers, workflows
from rad_bat.config import load_project_config
from rad_bat.errors import RadBatError


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / 'configs/system/cluster'
        self.source.mkdir(parents=True)
        self.template = self.source / 'spack.yaml'
        self.template.write_text('spack: {specs: [], view: false}\n')
        (self.root / '.rad-bat.json').write_text(json.dumps({
            'schema_version': 1, 'project': {'package': 'example', 'command': ['project', '{host_config}']},
            'spack': {'url': 'file:///spack', 'commit': 'a' * 40,
                      'environment': 'configs/{sys_type}/{machine}/spack.yaml'}}))
        self.config = load_project_config(self.root)
        self.calls = []
        self.failure = None
        self.generate = True
        self.context = contextlib.ExitStack()
        self.addCleanup(self.context.close)
        self.context.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.context.enter_context(patch.dict(os.environ, {'SYS_TYPE': 'system', 'LCSCHEDCLUSTER': 'cluster'}))
        self.context.enter_context(patch.object(workflows, '_git_checkout', side_effect=self.checkout))
        self.context.enter_context(patch.object(workflows, 'run_command', side_effect=self.command))
        self.context.enter_context(patch.object(spack, 'run_command', side_effect=self.command))

    def checkout(self, url, commit, destination):
        (destination / 'bin').mkdir(parents=True, exist_ok=True)
        (destination / 'bin/spack').touch()

    def command(self, argv, cwd=None, env=None):
        argv = list(map(str, argv))
        self.calls.append(argv)
        if self.failure in argv:
            raise RadBatError('intentional ' + self.failure + ' failure')
        if 'create' in argv:
            target = Path(argv[-1])
            target.mkdir(parents=True, exist_ok=True)
            (target / 'spack.yaml').write_text(Path(argv[-2]).read_text())
        if 'concretize' in argv:
            (Path(argv[2]) / 'spack.lock').write_text('fixed resolution')
        if 'install' in argv and self.generate:
            (Path(cwd) / 'generated.cmake').write_text('new host-config')
        if 'push' in argv:
            self.assertTrue((self.root / 'work/.rad-bat/host-configs/job.cmake').is_file())
            self.assertTrue((self.root / 'artifacts/job.cmake').is_file())

    def run_project(self, **overrides):
        options = dict(config=self.config, spec='+feature', work_dir=str(self.root / 'work'),
                       spack_env=None, install_tree_path=str(self.root / 'install'),
                       output_dir_path=str(self.root / 'artifacts'), upstreams=[],
                       buildcache='file:///cache', buildcache_username_variable=None,
                       buildcache_password_variable=None, push_to_buildcache=True,
                       host_config_name='job.cmake', jobs=2, command=None)
        options.update(overrides)
        workflows.run_spack(**options)

    def test_failed_upload_keeps_artifact_and_retry_skips_install_and_concretize(self):
        self.failure = 'push'
        with self.assertRaisesRegex(RadBatError, 'push failure'):
            self.run_project()
        self.assertTrue((self.root / 'artifacts/job.cmake').exists())
        self.assertFalse(any(c[0] == 'project' for c in self.calls))
        (self.root / 'artifacts/job.cmake').unlink()  # GitLab's checkout may be disposable.
        self.template.unlink()  # The prepared environment is authoritative on retries.
        self.calls.clear()
        self.failure = None
        self.run_project()
        self.assertFalse(any('install' in c or 'concretize' in c or 'create' in c for c in self.calls))
        self.assertTrue(any('push' in c for c in self.calls))
        self.assertEqual(self.calls[-1], ['project', str(self.root / 'artifacts/job.cmake')])

    def test_failed_install_retries_same_lock_and_does_not_accept_stale_host_config(self):
        self.failure = 'install'
        with self.assertRaises(RadBatError):
            self.run_project()
        lock = self.root / 'work/.rad-bat/spack-env/spack.lock'
        self.assertEqual(lock.read_text(), 'fixed resolution')
        (self.root / 'stale.cmake').write_text('old run')
        self.calls.clear()
        self.failure = None
        self.generate = False
        with self.assertRaisesRegex(RadBatError, 'exactly one generated'):
            self.run_project()
        self.assertTrue(any('install' in c for c in self.calls))
        self.assertFalse(any('concretize' in c or 'push' in c for c in self.calls))
        self.assertEqual(lock.read_text(), 'fixed resolution')

    def test_custom_phase_still_requires_host_config(self):
        from dataclasses import replace
        config = replace(self.config, spack=replace(self.config.spack, until='configure'))
        self.generate = False
        with self.assertRaisesRegex(RadBatError, 'exactly one generated'):
            self.run_project(config=config)
        self.assertTrue(any('configure' in c for c in self.calls))
        self.assertFalse(any('push' in c for c in self.calls))

    def test_machine_selection_and_explicit_override(self):
        self.assertEqual(workflows._render_machine_environment(self.config), self.template)
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RadBatError, 'SYS_TYPE'):
                workflows._render_machine_environment(self.config)
            self.run_project(spack_env=str(self.template))

    def test_env_spack_reference_falls_back_to_ci_variables(self):
        arguments = ['env', '--environment', 'env.yaml', '--work-dir', 'work', '--install-tree', 'install',
                     '--output-dir', 'out', '--temp-dir', 'tmp']
        with patch.dict(os.environ, {'MY_SPACK_REPO': 'file:///spack', 'MY_SPACK_COMMIT': 'a' * 40}):
            options = cli.build_parser().parse_args(arguments)
            self.assertEqual(options.spack_url, 'file:///spack')
            self.assertEqual(options.spack_commit, 'a' * 40)
            options = cli.build_parser().parse_args(arguments + ['--spack-commit', 'b' * 40])
            self.assertEqual(options.spack_commit, 'b' * 40)

    def test_machine_entry_points_keep_one_packages_file(self):
        repo = Path(__file__).resolve().parents[1]
        for system in ('toss_4_x86_64_ib', 'toss_4_x86_64_ib_cray'):
            self.assertFalse((repo / system / 'packages.yaml').exists())
            for package in (repo / system).glob('*/packages.yaml'):
                entry = package.with_name('spack.yaml')
                self.assertFalse(entry.is_symlink())
                self.assertIn('- packages.yaml', entry.read_text())
                self.assertTrue(package.with_name('config.yaml').is_file())


class BootstrapTests(unittest.TestCase):
    def test_spack_version_boundary(self):
        with patch.dict('sys.modules', {'spack': SimpleNamespace(spack_version_info=(1, 1, 1), __version__='1.1.1')}):
            with self.assertRaisesRegex(ValueError, 'requires Spack 1.2'):
                spack_helpers.check()
        with patch.dict('sys.modules', {'spack': SimpleNamespace(spack_version_info=(1, 2, 0), __version__='1.2.0')}):
            spack_helpers.check()

    def test_interrupted_isolation_is_retried(self):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            checkout = work / 'spack'
            (checkout / 'bin').mkdir(parents=True)
            (checkout / 'bin/spack').touch()
            (checkout / 'etc/spack/isolate').mkdir(parents=True)  # Partial native setup.
            def fail(argv, **kwargs):
                if 'isolate' in argv:
                    raise RadBatError('interrupted')
            with self.assertRaisesRegex(RadBatError, 'interrupted'):
                spack._prepare_isolation(checkout, work / 'isolation', run=fail)
            self.assertFalse((work / 'isolated').exists())
            with patch.object(spack, 'run_command') as run:
                spack._prepare_isolation(checkout, work / 'isolation')
                self.assertTrue(any('isolate' in call.args[0] for call in run.call_args_list))
                self.assertTrue((work / 'isolated').exists())


class ModuleTests(unittest.TestCase):
    def test_invalid_module_quoting_is_an_error(self):
        with patch.dict(os.environ, {'MODULE_LIST': "'unclosed"}):
            with self.assertRaisesRegex(RadBatError, 'Invalid quoting'):
                runner.load_modules()

    def test_modules_reach_child_process_without_shell_interpolation(self):
        with tempfile.TemporaryDirectory() as temp:
            init = Path(temp) / 'bash-init'
            init.write_text('module() { test "$1" = load || return 1; export FROM_MODULE="$2"; }\n')
            with patch.dict(os.environ, {'BASH_ENV': str(init), 'MODULE_LIST': "'compiler;not-a-command'"}):
                runner.load_modules()
                self.assertEqual(os.environ['FROM_MODULE'], 'compiler;not-a-command')
                result = subprocess.check_output([os.sys.executable, '-c',
                    'import os; print(os.environ["FROM_MODULE"])'], text=True)
                self.assertEqual(result.strip(), 'compiler;not-a-command')

    def test_module_failure_is_an_error(self):
        with tempfile.TemporaryDirectory() as temp:
            init = Path(temp) / 'bash-init'
            init.write_text('module() { return 1; }\n')
            with patch.dict(os.environ, {'BASH_ENV': str(init), 'MODULE_LIST': 'missing'}):
                with self.assertRaisesRegex(RadBatError, 'MODULE_LIST'):
                    runner.load_modules()


if __name__ == '__main__':
    unittest.main()
