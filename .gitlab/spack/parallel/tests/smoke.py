#!/usr/bin/env python3
"""Native offline fixtures: partial failure, persistent retry, publication, and concurrency.

Run with Spack 1.2.2's `spack python`. Creates a fresh directory and retains logs.
No scheduler, production storage or remote repository is used.
"""

import argparse
import contextlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import spack.paths
import spack.environment as ev
import spack.util.spack_yaml as sy
from spack.url_buildcache import URLBuildcacheEntry, BuildcacheComponent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    root = args.out.resolve()
    root.mkdir(parents=True, exist_ok=False)
    project = Path(__file__).resolve().parents[4]
    spack_source = Path(spack.paths.prefix)
    pin = subprocess.check_output(['git', '-C', str(spack_source), 'rev-parse', 'HEAD'], text=True).strip()
    fixture = root / 'repos/spack_repo/env_fixture'
    fixture.mkdir(parents=True)
    (fixture / 'repo.yaml').write_text('repo:\n  api: v2.1\n')
    marker = root / 'allow-success'
    for name in ('env_leaf', 'env_root', 'env_independent'):
        package = fixture / 'packages' / name
        package.mkdir(parents=True)
        cls = ''.join(p.capitalize() for p in name.split('_'))
        dependency = '    depends_on("env-leaf", type=("link", "run"))\n' if name == 'env_root' else ''
        failure = ('        if not Path({!r}).exists():\n'
                   '            raise RuntimeError("intentional smoke failure")\n').format(str(marker)) if name == 'env_root' else ''
        (package / 'package.py').write_text(
            'from pathlib import Path\nfrom spack.package import Package, version, depends_on\n\n'
            'class {}(Package):\n    has_code = False\n    version("1.0")\n{}\n'
            '    def install(self, spec, prefix):\n{}'
            '        Path(str(prefix)).mkdir(parents=True, exist_ok=True)\n'
            '        Path(str(prefix), "installed.txt").write_text("installed")\n'.format(cls, dependency, failure))
    source = root / 'source'
    source.mkdir()
    with (source / 'spack.yaml').open('w') as stream:
        sy.dump_config({'spack': {'repos': {'env_fixture': str(fixture), 'builtin_mock':
            str(spack_source / 'var/spack/test_repos/spack_repo/builtin_mock')},
            'specs': ['env-root', 'env-independent'], 'view': False,
            'concretizer': {'reuse': False, 'unify': False}}}, stream)
    # Short filesystem path for multiprocessing Unix sockets.
    temporary = tempfile.mkdtemp(prefix='rad-bat-smoke-', dir='/private/tmp' if sys.platform == 'darwin' else '/tmp')
    base = [sys.executable, str(project / 'bin/rad-bat'), 'env', '--environment', str(source),
            '--work-dir', str(root / 'work'), '--install-tree', str(root / 'install'),
            '--temp-dir', temporary, '--spack-url', str(spack_source), '--spack-commit', pin,
            '--buildcache', (root / 'buildcache').as_uri(), '--push-to-buildcache', '--jobs', '2',
            '--stop-after', '240', '--finish-after', '270']
    def run(number):
        with (root / ('attempt-{}.log'.format(number))).open('w') as output:
            return subprocess.run(base + ['--output-dir', str(root / ('attempt-' + str(number)))],
                                  stdout=output, stderr=subprocess.STDOUT, timeout=300).returncode
    assert run(1) != 0, 'Expected intentional installation failure'
    state = json.loads((root / 'attempt-1/status.json').read_text())
    concrete_dir = Path(state['environment'])
    assert (concrete_dir / 'spack.lock').exists(), 'Preparation failed; inspect attempt-1.log'
    concrete = ev.Environment(concrete_dir)
    specs = list(concrete.all_specs())
    cache = (root / 'buildcache').as_uri()
    def cached(spec):
        return URLBuildcacheEntry(cache, spec=spec, allow_unsigned=True).exists(
            [BuildcacheComponent.SPEC, BuildcacheComponent.TARBALL])
    assert not any(cached(s) for s in specs), 'Failed environment published packages'
    # Record completed packages before retry; these files must survive unchanged.
    successes = list((root / 'install').rglob('installed.txt'))
    assert len(successes) == 2, successes
    times = {p: p.stat().st_mtime_ns for p in successes}
    lock = (concrete_dir / 'spack.lock').read_bytes()
    marker.touch()
    assert run(2) == 0, 'Retry failed; inspect attempt-2.log'
    assert (concrete_dir / 'spack.lock').read_bytes() == lock
    assert all(p.stat().st_mtime_ns == stamp for p, stamp in times.items())
    assert all(cached(s) for s in specs), 'Successful environment not fully published'
    assert run(3) == 0, 'Warm retry failed'
    # Reuse an upstream without copying prefixes into the new local install tree.
    # Remove the success marker so a source rebuild would fail.
    marker.unlink()
    upstream_args = list(base)
    upstream_args[upstream_args.index('--work-dir') + 1] = str(root / 'upstream-work')
    upstream_args[upstream_args.index('--install-tree') + 1] = str(root / 'upstream-install')
    with (root / 'upstream.log').open('w') as output:
        status = subprocess.run(upstream_args + ['--output-dir', str(root / 'upstream-attempt'),
            '--upstream', str(root / 'install'), '--lockfile', str(concrete_dir / 'spack.lock')],
            stdout=output, stderr=subprocess.STDOUT, timeout=300).returncode
    assert status == 0, 'Upstream reuse failed; inspect upstream.log'
    assert not list((root / 'upstream-install').rglob('installed.txt')), 'Upstream prefixes were copied'
    # Two native installers restoring the same DAG into a fresh shared prefix.
    # This checks Spack coordination locally; LC placement/cancellation remain separate.
    restore = root / 'restore'
    restore.mkdir()
    with (concrete_dir / 'spack.yaml').open() as stream:
        manifest = sy.load_config(stream)
    manifest['spack']['config']['install_tree']['root'] = str(root / 'restored-install')
    with (restore / 'spack.yaml').open('w') as stream:
        sy.dump_config(manifest, stream)
    (restore / 'spack.lock').write_bytes(lock)
    executable = root / 'work/spack' / pin / 'checkout/bin/spack'
    processes = []
    with contextlib.ExitStack() as stack:
        for rank in range(2):
            output = stack.enter_context((root / ('restore-{}.log'.format(rank))).open('w'))
            env = dict(os.environ, TMPDIR=temporary, SPACK_USER_CACHE_PATH=str(root / ('restore-cache-' + str(rank))))
            processes.append(subprocess.Popen([str(executable), '-e', str(restore), 'install', '--only-concrete',
                '--use-buildcache', 'only', '-j2', '-p2'], env=env, stdout=output, stderr=subprocess.STDOUT))
        try:
            assert all(p.wait(timeout=120) == 0 for p in processes), 'Concurrent binary restore failed'
        finally:
            for process in processes:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=10)
    assert len(list((root / 'restored-install').rglob('installed.txt'))) == 3
    print('Native failure, no premature publication, persistent retry, warm retry, upstream reuse and concurrent binary restore passed:', root)


if __name__ == '__main__':
    main()
