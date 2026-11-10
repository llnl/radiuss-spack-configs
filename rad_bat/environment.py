"""Persistent whole-environment installs using native Spack parallelism."""

import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import shutil
import socket
import subprocess
import sys
import time

from . import allocation, execution, logs
from .errors import RadBatError
from .spack import (_git_checkout, _prepare_isolation, _spack_executable,
                    configure_storage, publish)

HELPER = Path(__file__).with_name('spack_helpers.py')


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def input_identity(args):
    """Key prepared state by its input files, pins, storage and machine context."""
    source = Path(args.environment).resolve()
    source = source.parent if source.is_file() else source
    if not (source / 'spack.yaml').is_file():
        raise RadBatError('No spack.yaml in {}'.format(source))
    inputs = {name: getattr(args, name) for name in (
        'spack_url', 'spack_commit', 'install_tree', 'buildcache',
        'buildcache_username_variable', 'buildcache_password_variable', 'group')}
    inputs['machine'] = {name: os.environ.get(name) for name in
                         ('LCSCHEDCLUSTER', 'SYS_TYPE', 'SPACK_TARGET')}
    inputs['source'] = str(source)
    inputs['install_tree'] = str(Path(args.install_tree).resolve())
    digest = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode())
    for directory, names, files in os.walk(source, followlinks=True):
        names[:] = sorted(n for n in names if n not in ('.spack-env', '.git', '__pycache__'))
        for name in sorted(files):
            path = Path(directory) / name
            if path.suffix in ('.yaml', '.yml', '.py'):
                digest.update(str(path.relative_to(source)).encode() + b'\0' + path.read_bytes())
    if args.lockfile:
        digest.update(Path(args.lockfile).read_bytes())
    return source, digest.hexdigest()[:20]


@contextlib.contextmanager
def workspace_lock(work):
    """Protect preparation of one workspace, not the shared installation tree."""
    work.mkdir(parents=True, exist_ok=True)
    with (work / '.rad-bat-env.lock').open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RadBatError('Environment workspace is already in use: {}'.format(work))
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def run_environment(args):
    if args.push_to_buildcache and not args.buildcache:
        raise RadBatError('--push-to-buildcache requires --buildcache')
    if args.finish_after <= args.stop_after:
        raise RadBatError('--finish-after must exceed --stop-after')
    if args.scheduler == 'local' and args.nodes != 1:
        raise RadBatError('Multiple nodes require an existing Slurm or Flux allocation')
    allocation.launch_command(args.scheduler, args.nodes, ['spack'])
    work = Path(args.work_dir).resolve()
    with workspace_lock(work):
        return _run(args, work)


def _run(args, work):
    source, identity = input_identity(args)
    state_dir = work / 'environments' / identity
    state_dir.mkdir(parents=True, exist_ok=True)
    environment = state_dir / 'environment'
    attempt = Path(args.output_dir).resolve()
    if (attempt / 'status.json').exists():
        raise RadBatError('Choose a new --output-dir for each attempt')
    attempt.mkdir(parents=True, exist_ok=True)
    temporary = Path(args.temp_dir).resolve()
    temporary.mkdir(parents=True, exist_ok=True)
    options = dict(vars(args), environment=str(environment), attempt=str(attempt), temp_dir=str(temporary),
                   source_cache=str(work / 'sources'), bootstrap=str(work / 'bootstrap'),
                   install_tree=str(Path(args.install_tree).resolve()))
    write_json(attempt / 'options.json', options)
    started = time.monotonic()
    stop, finish = started + args.stop_after, started + args.finish_after
    state = {'complete': False, 'installed': False, 'published': False, 'error': None,
             'environment': str(environment), 'identity': identity, 'nodes': args.nodes}
    write_json(attempt / 'status.json', state)
    old_environment = os.environ.copy()
    handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    execution.STOP_REQUESTED = False
    for sig in handlers:
        signal.signal(sig, execution.request_stop)
    os.environ.update(SPACK_USER_CACHE_PATH=str(work / 'cache'),
                      TMPDIR=str(temporary), PYTHONPATH=str(HELPER.parent.parent) +
                      os.pathsep + os.environ.get('PYTHONPATH', ''))
    # The prepared checkout has its own user scope from spack isolate.
    os.environ.pop('SPACK_DISABLE_LOCAL_CONFIG', None)
    log = attempt / 'prepare.log'

    def run(argv, cwd=None, env=None):
        execution.command(argv, log, stop, env=env, cwd=cwd)

    try:
        with logs.sections.section('prepare', 'Prepare pinned Spack and environment'):
            checkout = work / 'spack' / args.spack_commit / 'checkout'
            _git_checkout(args.spack_url, args.spack_commit, checkout, run=run)
            spack = _spack_executable(checkout)
            _prepare_isolation(checkout, checkout.parent / 'isolation',
                               args.spack_commit, run=run)
            if not (state_dir / 'ready.json').exists():
                # A partial preparation can be repeated; workers start only after ready.json.
                shutil.copytree(source, environment, symlinks=False, dirs_exist_ok=True,
                                ignore=shutil.ignore_patterns('spack.lock', '.spack-env'))
                bootstrap_scope = state_dir / 'prepare-config'
                bootstrap_scope.mkdir(exist_ok=True)
                (bootstrap_scope / 'repos.yaml').write_text('repos:: {}\n')
                run([spack, '-C', bootstrap_scope, 'python', HELPER, 'prepare', attempt / 'options.json'])
                configure_storage(spack, environment, options['install_tree'], args.buildcache,
                                  args.buildcache_username_variable, args.buildcache_password_variable, run=run)
                if args.lockfile:
                    shutil.copyfile(args.lockfile, environment / 'spack.lock')
                with logs.sections.section('concretize', 'Concretize environment'):
                    if not args.lockfile:
                        run([spack, '-e', environment, 'concretize', '--fresh'])
                    run([spack, '-e', environment, 'python', HELPER, 'freeze'])
                write_json(state_dir / 'ready.json', {'identity': identity})
            else:
                logs.info('Reusing concrete environment: {}'.format(environment))
        options.update(spack=str(spack), stop_epoch=time.time() + max(0, stop - time.monotonic()))
        write_json(attempt / 'options.json', options)
        worker_command = [sys.executable, '-m', 'rad_bat.environment', str(attempt / 'options.json')]
        launcher = allocation.launch_command(args.scheduler, args.nodes, worker_command)
        with logs.sections.section('install', 'Install environment on {} node(s)'.format(args.nodes), collapsed=False):
            allocation.launch_workers(launcher, attempt, stop)
            workers = [json.loads(p.read_text()) for p in attempt.glob('workers/*/status.json')]
            if len(workers) != args.nodes or any(w['returncode'] != 0 for w in workers):
                raise RadBatError('One or more installation workers did not complete successfully')
            if len({w['host'] for w in workers}) != args.nodes:
                raise RadBatError('Expected one installation worker per node')
            run([spack, '-e', environment, 'python', HELPER, 'verify', attempt / 'installed.json'])
            state['installed'] = True
            write_json(attempt / 'status.json', state)
        if args.push_to_buildcache:
            with logs.sections.section('publish', 'Publish completed environment'):
                installed = json.loads((attempt / 'installed.json').read_text())
                def upload(argv, **kwargs):
                    execution.command(argv, attempt / 'publish.log', finish, **kwargs)
                for offset in range(0, len(installed), 64):
                    publish(spack, environment, only='package', specs=installed[offset:offset + 64], run=upload)
                if installed:
                    upload([spack, '-e', environment, 'buildcache', 'update-index', 'rad-bat'])
                state['published'] = True
        state['complete'] = True
        return 0
    except (Exception, KeyboardInterrupt) as error:
        state['error'] = str(error) or 'Interrupted'
        logs.error(state['error'])
        return 1
    finally:
        state['elapsed_seconds'] = time.monotonic() - started
        write_json(attempt / 'status.json', state)
        # Collect the concrete inputs even after failure. Reporting never publishes.
        for name in ('spack.yaml', 'spack.lock'):
            if (environment / name).exists():
                shutil.copyfile(environment / name, attempt / name)
        for sig, handler in handlers.items():
            signal.signal(sig, handler)
        os.environ.clear()
        os.environ.update(old_environment)


def worker(options_path):
    options = json.loads(Path(options_path).read_text())
    rank = os.environ.get('FLUX_TASK_RANK', os.environ.get('SLURM_PROCID', '0'))
    if not rank.isdigit():
        raise ValueError('Invalid worker rank')
    directory = Path(options['attempt']) / 'workers' / rank
    directory.mkdir(parents=True, exist_ok=True)
    cpus = len(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else os.cpu_count() or 1
    if options['scheduler'] == 'slurm':
        cpus = min(cpus, int(os.environ.get('SLURM_CPUS_PER_TASK', cpus)))
    if options['jobs']:
        cpus = min(cpus, options['jobs'])
    env = os.environ.copy()
    env.update(SPACK_USER_CACHE_PATH=str(directory / 'cache'),
               TMPDIR=str(Path(options['temp_dir']) / rank))
    Path(env['TMPDIR']).mkdir(parents=True, exist_ok=True)
    env.pop('MAKEFLAGS', None)  # Each node owns a separate POSIX jobserver.
    state = {'rank': rank, 'host': socket.gethostname(), 'cpus': cpus, 'returncode': None}
    write_json(directory / 'status.json', state)
    argv = [options['spack'], '-e', options['environment'], 'install', '--only-concrete',
            '-j{}'.format(cpus), '-p{}'.format(options['packages']),
            '--log-format', 'junit', '--log-file', str(directory / 'native.xml')]
    deadline = time.monotonic() + max(0, options['stop_epoch'] - time.time())
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, execution.request_stop)
    try:
        execution.command(argv, directory / 'install.log', deadline, env=env)
        state['returncode'] = 0
    except TimeoutError:
        state['returncode'] = 124
    except subprocess.CalledProcessError as error:
        state['returncode'] = error.returncode
    except Exception as error:
        state.update(returncode=1, error=str(error))
    finally:
        write_json(directory / 'status.json', state)
    return state['returncode']


if __name__ == '__main__':
    sys.exit(worker(sys.argv[1]))
