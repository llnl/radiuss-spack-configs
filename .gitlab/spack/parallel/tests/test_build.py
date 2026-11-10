"""CI adapter and real Spack schema checks."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import subprocess
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
        env = {'PATH': os.environ['PATH'], 'CI_PROJECT_DIR': str(SCRIPT.parents[3]), 'MY_ENV_NAME': 'shared-ci',
               'RSC_MACHINE': 'dane', 'SPACK_TARGET': 'testcpu', 'CI_PIPELINE_ID': '100',
               'CI_JOB_ID': '200', 'CI_JOB_NAME': 'parallel-dane', 'RSC_PARALLEL_STORAGE_ROOT': str(self.root), 'ON_CORONA': 'OFF'}
        self.patcher = patch.dict(os.environ, env, clear=True)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_default_one_node_and_persistent_retry_paths(self):
        settings = build.settings()
        self.assertEqual(settings['nodes'], 1)
        first = build.paths(settings)
        os.environ['CI_JOB_ID'] = '201'
        second = build.paths(settings)
        self.assertEqual(first['workspace'], second['workspace'])
        self.assertEqual(first['workspace'].name, 'parallel-dane')
        self.assertEqual(first['store'], second['store'])
        self.assertNotEqual(first['attempt'], second['attempt'])

    def test_node_count_does_not_split_storage_and_new_pipeline_does_not_resume(self):
        first = build.paths(build.settings())
        os.environ['RSC_PARALLEL_NODES'] = '2'
        second = build.paths(build.settings())
        self.assertEqual(first, second)
        os.environ['CI_PIPELINE_ID'] = '101'
        third = build.paths(build.settings())
        self.assertEqual(first['store'], third['store'])
        self.assertNotEqual(first['workspace'], third['workspace'])

    def test_job_names_are_distinct_safe_components(self):
        first = build.paths(build.settings())
        os.environ['CI_JOB_NAME'] = 'parallel-dane: [gcc, a/b]'
        second = build.paths(build.settings())
        self.assertNotEqual(first['workspace'], second['workspace'])
        self.assertEqual(second['workspace'].parent, first['workspace'].parent)

    def test_adapter_adds_main_reuse_without_collecting_twice(self):
        main = self.root / 'production/shared-ci/dane/testcpu/main'
        (main / 'install/.spack-db').mkdir(parents=True)
        (main / 'install/.spack-db/index.json').write_text('{}')
        os.environ.update(SPACK_CI_STORAGE_ROOT=str(self.root / 'production'),
                          MY_SPACK_REPO='file:///spack', MY_SPACK_COMMIT='a' * 40,
                          RSC_SCHEDULER='slurm')
        with patch.object(build, 'ensure_directory'), patch.object(build, 'collect') as collect, patch.object(
                build, 'run_environment', return_value=0) as run:
            self.assertEqual(build.run(), 0)
        options = run.call_args.args[0]
        self.assertEqual(options.upstream, [str(main / 'install')])
        self.assertEqual(options.read_buildcache, [(main / 'buildcache').as_uri()])
        collect.assert_not_called()

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
        with patch.object(build, 'paths', return_value=paths), patch.object(build, 'run_environment') as run:
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
    def test_real_environments_preserve_upstreams_and_read_mirrors(self):
        for name in ('shared-ci', 'cached-cmake'):
            destination = self.root / name
            shutil.copytree(SCRIPT.parents[3] / '.gitlab/spack/envs' / name, destination)
            with (destination / 'spack.yaml').open() as stream:
                original = sy.load_config(stream)['spack']
            spack_helpers.prepare({'environment': str(destination),
                'install_tree': str(self.root / 'install'), 'source_cache': str(self.root / 'sources'),
                'bootstrap': str(self.root / 'bootstrap'), 'group': 'radiuss'})
            with (destination / 'spack.yaml').open() as stream:
                data = sy.load_config(stream)
            spack.schema.Validator(spack.schema.env.schema).validate(data)
            self.assertEqual(data['spack'].get('mirrors'), original.get('mirrors'))
            self.assertEqual(data['spack'].get('upstreams'), original.get('upstreams'))
            self.assertNotIn('ci.yaml', data['spack']['include'])
            self.assertEqual(data['spack']['config']['build_stage'], ['$user_cache_path/stage'])

    @unittest.skipUnless(sy, 'Run with spack python for schema validation')
    def test_inherited_autopush_is_disabled_without_losing_read_mirrors(self):
        destination = self.root / 'project-env'
        destination.mkdir()
        (destination / 'spack.yaml').write_text(
            'spack: {specs: [], upstreams: {existing: {install_tree: /persistent/upstream}}}\n')
        mirrors = {'inherited': {'url': 'file:///cache', 'autopush': True},
                   'source': 'https://example.invalid/source'}
        with patch('spack.environment.active_environment', return_value=SimpleNamespace(path=str(destination))), patch(
                'spack.config.get', return_value=mirrors):
            spack_helpers.disable_autopush()
        with (destination / 'spack.yaml').open() as stream:
            data = sy.load_config(stream)
        spack.schema.Validator(spack.schema.env.schema).validate(data)
        self.assertEqual(data['spack']['upstreams']['existing']['install_tree'], '/persistent/upstream')
        self.assertTrue(all(not m['autopush'] for m in data['spack']['mirrors'].values()))
        self.assertEqual(data['spack']['mirrors']['source']['url'], 'https://example.invalid/source')

    @unittest.skipUnless(sy, 'Run with spack python for native repository validation')
    def test_spack_clones_json_repository_at_pin_and_preserves_precedence(self):
        import spack.paths
        import spack.repo
        from rad_bat.config import ProjectConfig, SpackConfig, RepositoryConfig
        from rad_bat.spack import _prepare_repositories

        origin = self.root / 'origin'
        remote, _ = spack.repo.create_repo(str(origin), namespace='remote_fixture')
        local, _ = spack.repo.create_repo(str(self.root / 'local'), namespace='local_fixture')
        # The same package in two repositories exercises precedence without a build.
        for repository in (remote, local):
            package = Path(repository) / 'packages/example'
            package.mkdir()
            (package / 'package.py').write_text('# fixture')
        def git(*args):
            return subprocess.check_output(['git', '-C', str(origin), *args], text=True).strip()
        git('init', '-q')
        git('add', '.')
        git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
            'commit', '-qm', 'pinned version')
        pin = git('rev-parse', 'HEAD')
        (origin / 'not-in-pin').touch()
        git('add', '.')
        git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
            'commit', '-qm', 'later version')
        destination = self.root / 'project-env'
        destination.mkdir()
        (destination / 'spack.yaml').write_text('spack: {specs: [], repos:: {}}')
        config = ProjectConfig(self.root, 'example', [], SpackConfig(
            'unused', 'a' * 40, 'unused', [RepositoryConfig(path=local),
            RepositoryConfig(url=str(origin), commit=pin,
                             subdirectory=str(Path(remote).relative_to(origin)))], []))
        executable = Path(spack.paths.prefix) / 'bin/spack'
        with patch.dict(os.environ, {'SPACK_USER_CACHE_PATH': str(self.root / 'cache')}):
            _prepare_repositories(config, executable, destination, self.root / 'managed')
            result = subprocess.check_output([str(executable), '-e', str(destination), 'python', '-c',
                'import json, spack.repo; print(json.dumps([r.root for r in spack.repo.PATH.repos]))'], text=True)
        with (destination / 'spack.yaml').open() as stream:
            data = sy.load_config(stream)
        spack.schema.Validator(spack.schema.env.schema).validate(data)
        entry = data['spack']['repos']['rad_bat_1']
        checkout = Path(entry['destination'])
        self.assertEqual(subprocess.check_output(['git', '-C', str(checkout), 'rev-parse', 'HEAD'],
                                                text=True).strip(), pin)
        self.assertFalse((checkout / 'not-in-pin').exists())
        self.assertEqual(json.loads(result.splitlines()[-1]),
                         [str(Path(local).resolve()), str(checkout / entry['paths'][0])])

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
