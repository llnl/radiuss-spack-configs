"""Regression checks for publication, retry identity, and allocation boundaries."""

import contextlib
import io
import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from rad_bat import allocation, cli, environment, execution


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        (self.source / 'spack.yaml').write_text('spack: {specs: [example]}\n')
        self.args = cli.build_parser().parse_args([
            'env', '--environment', str(self.source), '--work-dir', str(self.root / 'work'),
            '--install-tree', str(self.root / 'install'), '--output-dir', str(self.root / 'attempt-1'),
            '--temp-dir', str(self.root / 'tmp'), '--spack-url', 'file:///spack',
            '--spack-commit', 'a' * 40, '--buildcache', (self.root / 'cache').as_uri(),
            '--push-to-buildcache'])
        self.calls = []
        self.worker_failure = False
        self.upload_failure = False
        self.patchers = contextlib.ExitStack()
        self.addCleanup(self.patchers.close)
        self.patchers.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.patchers.enter_context(contextlib.redirect_stderr(io.StringIO()))
        self.patchers.enter_context(patch.object(environment, '_git_checkout', side_effect=self.checkout))
        self.patchers.enter_context(patch.object(execution, 'command', side_effect=self.command))
        self.patchers.enter_context(patch.object(allocation, 'launch_workers', side_effect=self.launch))
        self.patchers.enter_context(patch.dict(os.environ, {'SPACK_DISABLE_LOCAL_CONFIG': 'true'}))

    def checkout(self, url, commit, destination, run):
        (destination / 'bin').mkdir(parents=True, exist_ok=True)
        (destination / 'bin/spack').touch()

    def command(self, argv, *args, **kwargs):
        argv = list(map(str, argv))
        self.calls.append(argv)
        if 'concretize' in argv:
            (Path(argv[2]) / 'spack.lock').write_text('concrete-identity')
        if 'verify' in argv:
            Path(argv[-1]).write_text(json.dumps(['/installed-hash']))
        if 'push' in argv and self.upload_failure:
            raise subprocess.CalledProcessError(1, argv)

    def launch(self, launcher, attempt, deadline):
        self.calls.append(['workers'])
        worker = attempt / 'workers/0'
        worker.mkdir(parents=True)
        (worker / 'status.json').write_text(json.dumps({'host': 'node0', 'returncode': 0}))
        (self.root / 'install').mkdir(exist_ok=True)
        (self.root / 'install/partial-progress').touch()
        if self.worker_failure:
            raise subprocess.CalledProcessError(1, launcher)

    def retry(self):
        self.args.output_dir = str(self.root / 'attempt-2')
        self.calls.clear()
        return environment.run_environment(self.args)

    def test_success_publishes_only_after_workers_and_verification(self):
        self.assertEqual(environment.run_environment(self.args), 0)
        workers = self.calls.index(['workers'])
        verify = next(i for i, c in enumerate(self.calls) if 'verify' in c)
        push = next(i for i, c in enumerate(self.calls) if 'push' in c)
        self.assertLess(workers, verify)
        self.assertLess(verify, push)
        self.assertIn('/installed-hash', self.calls[push])
        self.assertNotIn('--force', self.calls[push])

    def test_failed_workers_keep_progress_and_never_publish(self):
        self.worker_failure = True
        self.assertEqual(environment.run_environment(self.args), 1)
        self.assertTrue((self.root / 'install/partial-progress').exists())
        self.assertFalse(any('push' in c for c in self.calls))
        self.worker_failure = False
        self.assertEqual(self.retry(), 0)
        self.assertFalse(any('concretize' in c for c in self.calls))
        self.assertTrue(any('push' in c for c in self.calls))

    def test_interrupted_workers_never_publish(self):
        with patch.object(allocation, 'launch_workers', side_effect=TimeoutError('allocation deadline')):
            self.assertEqual(environment.run_environment(self.args), 1)
        self.assertFalse(any('push' in c for c in self.calls))

    def test_changed_symlinked_machine_config_invalidates_preparation(self):
        machine = self.root / 'machine'
        machine.mkdir()
        (machine / 'packages.yaml').write_text('packages: {}')
        (self.source / 'machine').symlink_to(machine, target_is_directory=True)
        first = environment.input_identity(self.args)
        (machine / 'packages.yaml').write_text('packages: {all: {target: [zen3]}}')
        self.assertNotEqual(environment.input_identity(self.args), first)

    def test_failed_publication_retries_without_reconcretizing(self):
        self.upload_failure = True
        self.assertEqual(environment.run_environment(self.args), 1)
        state = json.loads((Path(self.args.output_dir) / 'status.json').read_text())
        self.assertTrue(state['installed'])
        self.assertFalse(state['published'])
        self.upload_failure = False
        self.assertEqual(self.retry(), 0)
        self.assertFalse(any('concretize' in c for c in self.calls))

    def test_publication_is_opt_in(self):
        self.args.push_to_buildcache = False
        self.assertEqual(environment.run_environment(self.args), 0)
        self.assertFalse(any('push' in c for c in self.calls))

    def test_configuration_change_creates_new_concrete_state(self):
        self.assertEqual(environment.run_environment(self.args), 0)
        (self.source / 'spack.yaml').write_text('spack: {specs: [different]}\n')
        self.assertEqual(self.retry(), 0)
        self.assertTrue(any('concretize' in c for c in self.calls))
        self.assertEqual(len(list((self.root / 'work/environments').iterdir())), 2)

    def test_node_count_and_attempt_do_not_change_concrete_identity(self):
        before = environment.input_identity(self.args)
        self.args.nodes = 2
        self.args.output_dir = 'another-attempt'
        self.assertEqual(environment.input_identity(self.args), before)

    def test_empty_verification_failure_prevents_publication(self):
        original = self.command
        def command(argv, *args, **kwargs):
            if 'verify' in argv:
                raise subprocess.CalledProcessError(1, argv)
            return original(argv, *args, **kwargs)
        with patch.object(execution, 'command', side_effect=command):
            self.assertEqual(environment.run_environment(self.args), 1)
        self.assertFalse(any('push' in c for c in self.calls))

    def test_workspace_lock_does_not_lock_install_tree(self):
        with environment.workspace_lock(self.root / 'first'):
            with environment.workspace_lock(self.root / 'second'):
                with self.assertRaisesRegex(Exception, 'already in use'):
                    with environment.workspace_lock(self.root / 'first'):
                        pass


class AllocationTests(unittest.TestCase):
    def test_existing_allocations_and_one_node_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(allocation.launch_command('local', 1, ['worker']), ['worker'])
            for scheduler in ('flux', 'slurm'):
                with self.assertRaises(ValueError):
                    allocation.launch_command(scheduler, 2, ['worker'])
            with self.assertRaises(ValueError):
                allocation.launch_command('local', 2, ['worker'])
        with patch.dict(os.environ, {'SLURM_JOB_ID': '1', 'SLURM_JOB_CPUS_PER_NODE': '8(x2)'}):
            command = allocation.launch_command('slurm', 2, ['worker'])
        self.assertIn('--cpus-per-task=8', command)
        self.assertIn('--ntasks-per-node=1', command)
        self.assertNotIn('sbatch', command)

    def test_flux_launch_waits_and_explicitly_signals_remote_tasks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def command(argv, log, deadline, **kwargs):
                if argv[:2] == ['flux', 'submit']:
                    Path(log).write_text('f123abc\n')
                else:
                    self.assertIn('--wait-event=clean', argv)
                    kwargs['on_interrupt']()
            with patch.dict(os.environ, {'FLUX_URI': 'local://test'}), patch.object(
                    allocation, 'command', side_effect=command), patch.object(allocation, 'stop_flux') as stop:
                allocation.launch_workers(allocation.launch_command('flux', 2, ['worker']), root, time.monotonic() + 5)
            stop.assert_called_once_with('f123abc')

    def test_worker_caps_cpu_budget_and_starts_its_own_jobserver(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            options = {'attempt': str(root), 'temp_dir': str(root / 'tmp'), 'scheduler': 'slurm',
                       'jobs': 4, 'spack': '/spack/bin/spack', 'environment': '/environment',
                       'packages': 2, 'stop_epoch': time.time() + 30}
            (root / 'options.json').write_text(json.dumps(options))
            handlers = {sig: signal.getsignal(sig) for sig in
                        (signal.SIGINT, signal.SIGTERM)}
            try:
                with patch.dict(os.environ, {'SLURM_PROCID': '0', 'SLURM_CPUS_PER_TASK': '8',
                                             'MAKEFLAGS': '--jobserver-auth=99,100'}), patch.object(
                        os, 'sched_getaffinity', create=True, return_value=set(range(16))), patch.object(
                        execution, 'command') as command:
                    self.assertEqual(environment.worker(root / 'options.json'), 0)
                self.assertIn('-j4', command.call_args.args[0])
                self.assertNotIn('MAKEFLAGS', command.call_args.kwargs['env'])
                self.assertEqual(json.loads((root / 'workers/0/status.json').read_text())['cpus'], 4)
            finally:
                for sig, handler in handlers.items():
                    signal.signal(sig, handler)

    def test_deadline_stops_child_and_calls_remote_cleanup(self):
        execution.STOP_REQUESTED = False
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            with patch.object(execution, 'terminate', wraps=execution.terminate), self.assertRaises(TimeoutError):
                callback = []
                execution.command([sys.executable, '-c', 'import time; time.sleep(20)'],
                                  Path(tmp) / 'log', time.monotonic() + 0.1,
                                  on_interrupt=lambda: callback.append('stopped'))
            self.assertEqual(callback, ['stopped'])


class ReportTests(unittest.TestCase):
    def test_missing_native_record_is_unreported_and_shared_deps_are_not_duplicated(self):
        from rad_bat.report import dependency_report
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'spack.lock').write_text(json.dumps({'roots': [{'hash': 'a'}, {'hash': 'b'}],
                'concrete_specs': {'a': {'name': 'root', 'dependencies': [{'hash': 'b'}]},
                                   'b': {'name': 'shared'}}}))
            worker = root / 'workers/0'
            worker.mkdir(parents=True)
            (worker / 'native.xml').write_text('<incomplete>')
            report = dependency_report(root)
            self.assertIn('[unreported] root', report)
            self.assertIn('(shown above)', report)
            self.assertIn('Incomplete native report', report)
            self.assertNotIn('[failed]', report)


if __name__ == '__main__':
    unittest.main()
