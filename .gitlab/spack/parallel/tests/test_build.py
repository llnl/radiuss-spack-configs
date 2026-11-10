"""CI adapter and real Spack schema checks."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'build.py'
loader = importlib.util.spec_from_file_location('parallel_build', SCRIPT)
build = importlib.util.module_from_spec(loader)
loader.loader.exec_module(build)
from rad_bat import spack_helpers
try:
    import spack.util.spack_yaml as sy
    import spack.schema
    import spack.schema.env
except ImportError:
    sy = None


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        env = {'CI_PROJECT_DIR': str(SCRIPT.parents[3]), 'MY_ENV_NAME': 'shared-ci',
               'RSC_MACHINE': 'dane', 'SPACK_TARGET': 'testcpu', 'CI_PIPELINE_ID': '100',
               'CI_JOB_ID': '200', 'RSC_PARALLEL_STORAGE_ROOT': str(self.root), 'ON_CORONA': 'OFF'}
        self.patcher = patch.dict(os.environ, env, clear=True)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_default_one_node_and_persistent_retry_paths(self):
        settings = build.settings()
        self.assertEqual(settings['nodes'], 1)
        first = build.paths(settings)
        os.environ['CI_JOB_ID'] = '201'
        second = build.paths(settings)
        self.assertEqual(first['pipeline'], second['pipeline'])
        self.assertEqual(first['store'], second['store'])
        self.assertNotEqual(first['attempt'], second['attempt'])

    def test_corona_requires_confirmed_queue(self):
        os.environ.pop('ON_CORONA')
        with self.assertRaisesRegex(ValueError, 'confirmed CI queue'):
            build.check()

    def test_collect_after_hard_failure_only_copies_diagnostics(self):
        paths = build.paths(build.settings())
        paths['attempt'].mkdir(parents=True)
        (paths['attempt'] / 'status.json').write_text(json.dumps({'complete': False, 'error': 'interrupted'}))
        # Redirect checkout artifacts into temporary storage.
        paths['results'] = self.root / 'results'
        with patch.object(build, 'paths', return_value=paths), patch.object(build, 'rad_bat') as run:
            build.collect()
        run.assert_not_called()
        self.assertIn('interrupted', (paths['results'] / 'junit.xml').read_text())

    @unittest.skipUnless(sy, 'Run with spack python for schema validation')
    def test_pipeline_uses_jacamar_and_defaults_to_one_node(self):
        with (SCRIPT.parent / 'pipeline.yml').open() as stream:
            pipeline = sy.load_config(stream)
        self.assertEqual(pipeline['variables']['RSC_PARALLEL_NODES'], '1')
        for machine in build.MACHINES:
            job = pipeline['parallel-' + machine]
            self.assertEqual(job['tags'], ['batch', machine])
            self.assertIn('SCHEDULER_PARAMETERS', job['variables'])

    @unittest.skipUnless(sy, 'Run with spack python for schema validation')
    def test_real_environments_disable_autopush_and_production_storage(self):
        for name in ('shared-ci', 'cached-cmake'):
            destination = self.root / name
            shutil.copytree(SCRIPT.parents[3] / '.gitlab/spack/envs' / name, destination)
            spack_helpers.prepare({'environment': str(destination),
                'install_tree': str(self.root / 'install'), 'source_cache': str(self.root / 'sources'),
                'bootstrap': str(self.root / 'bootstrap'), 'group': 'radiuss'})
            with (destination / 'spack.yaml').open() as stream:
                data = sy.load_config(stream)
            spack.schema.Validator(spack.schema.env.schema).validate(data)
            self.assertEqual(data['spack']['mirrors'], {})
            self.assertEqual(data['spack']['upstreams'], {})
            self.assertNotIn('ci.yaml', data['spack']['include'])
            self.assertEqual(data['spack']['config']['build_stage'], ['$user_cache_path/stage'])

    @unittest.skipUnless(sy, 'Run with spack python for schema validation')
    def test_inherited_autopush_is_disabled_without_losing_read_mirrors(self):
        destination = self.root / 'project-env'
        destination.mkdir()
        (destination / 'spack.yaml').write_text('spack: {specs: []}\n')
        mirrors = {'inherited': {'url': 'file:///cache', 'autopush': True},
                   'source': 'https://example.invalid/source'}
        with patch('spack.environment.active_environment', return_value=SimpleNamespace(path=str(destination))), patch(
                'spack.config.get', return_value=mirrors):
            spack_helpers.disable_autopush()
        with (destination / 'spack.yaml').open() as stream:
            data = sy.load_config(stream)
        spack.schema.Validator(spack.schema.env.schema).validate(data)
        self.assertTrue(all(not m['autopush'] for m in data['spack']['mirrors'].values()))
        self.assertEqual(data['spack']['mirrors']['source']['url'], 'https://example.invalid/source')

    @unittest.skipUnless(sy, 'Run with spack python for schema validation')
    def test_freeze_uses_shared_repository_paths(self):
        destination = self.root / 'env'
        destination.mkdir()
        (destination / 'spack.yaml').write_text('spack: {repos: {}}\n')
        repo = SimpleNamespace(namespace='builtin', root='/persistent/spack_repo/builtin')
        with patch('spack.environment.active_environment', return_value=SimpleNamespace(path=str(destination))), patch(
                'spack.repo.PATH', SimpleNamespace(repos=[repo])):
            spack_helpers.freeze()
        with (destination / 'spack.yaml').open() as stream:
            data = sy.load_config(stream)
        spack.schema.Validator(spack.schema.env.schema).validate(data)
        self.assertEqual(data['spack']['repos']['builtin'], repo.root)


if __name__ == '__main__':
    unittest.main()
