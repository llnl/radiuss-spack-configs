"""Persistent whole-environment installs using native Spack parallelism."""

from dataclasses import dataclass, field
from typing import Optional
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time

from . import allocation, execution, logs
from .errors import RadBatError
from .config import FULL_COMMIT
from .spack import (_git_checkout, _prepare_isolation, _spack_executable,
                    create_environment, workspace_lock, configure_storage, publish)
from .runner import load_modules

HELPER = Path(__file__).with_name('spack_helpers.py')


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


@dataclass
class EnvironmentOptions:
    environment: str
    work_dir: str
    install_tree: str
    output_dir: str
    temp_dir: str
    spack_url: str
    spack_commit: str
    scheduler: str = 'local'
    nodes: int = 1
    jobs: Optional[int] = None
    packages: int = 2
    stop_after: int = 3300
    finish_after: int = 3570
    lockfile: Optional[str] = None
    group: Optional[str] = None
    buildcache: Optional[str] = None
    buildcache_username_variable: Optional[str] = None
    buildcache_password_variable: Optional[str] = None
    push_to_buildcache: bool = False
    upstream: list = field(default_factory=list)
    read_buildcache: list = field(default_factory=list)


def run_environment(args):
    load_modules()
    if not FULL_COMMIT.fullmatch(args.spack_commit):
        raise RadBatError('--spack-commit must be a full Git commit')
    for name in ('nodes', 'packages', 'stop_after', 'finish_after', 'jobs'):
        value = getattr(args, name)
        if value is not None and value < 1:
            raise RadBatError('{} must be positive'.format(name))
    if args.push_to_buildcache and not args.buildcache:
        raise RadBatError('--push-to-buildcache requires --buildcache')
    if args.finish_after <= args.stop_after:
        raise RadBatError('--finish-after must exceed --stop-after')
    launcher = allocation.launcher_prefix(args.scheduler, args.nodes)
    work = Path(args.work_dir).resolve()
    with workspace_lock(work), execution.interruptible():
        return _run(args, work, launcher)


def prepare_environment(args, work, attempt, run):
    """Prepare once per workspace; later attempts use its concrete snapshot."""
    environment = work / 'environment'
    checkout = work / 'spack'
    _git_checkout(args.spack_url, args.spack_commit, checkout, run=run)
    spack = _spack_executable(checkout)
    _prepare_isolation(checkout, work / 'isolation', run=run)
    if not (work / 'prepared').exists():
        # A partial preparation can be repeated; workers start only after the prepared marker.
        source = Path(args.environment).absolute()
        source = source / 'spack.yaml' if source.is_dir() else source
        if not source.is_file():
            raise RadBatError('Environment file not found: {}'.format(source))
        create_environment(spack, source, environment, run=run)
        run([spack, 'python', '-m', 'rad_bat.spack_helpers', 'prepare', attempt / 'options.json'])
        configure_storage(spack, environment, str(Path(args.install_tree).resolve()), args.buildcache,
                          args.buildcache_username_variable, args.buildcache_password_variable,
                          upstreams=args.upstream, read_buildcaches=args.read_buildcache, run=run)
        if args.lockfile:
            shutil.copyfile(args.lockfile, environment / 'spack.lock')
        with logs.sections.section('concretize', 'Concretize environment'):
            if not args.lockfile:
                run([spack, '-e', environment, 'concretize', '--fresh'])
            run([spack, '-e', environment, 'python', '-m', 'rad_bat.spack_helpers', 'freeze'])
        (work / 'prepared').touch()
    else:
        logs.info('Resuming concrete environment: {}. Inputs are not refreshed; use a new workspace for changes.'.format(environment))
    return spack


def _run(args, work, launcher):
    environment = work / 'environment'
    attempt = Path(args.output_dir).resolve()
    if (attempt / 'status.json').exists():
        raise RadBatError('Choose a new --output-dir for each attempt')
    attempt.mkdir(parents=True, exist_ok=True)
    temporary = Path(args.temp_dir).resolve()
    temporary.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    stop, finish = started + args.stop_after, started + args.finish_after
    options = dict(vars(args), environment=str(environment), attempt=str(attempt), temp_dir=str(temporary),
                   source_cache=str(work / 'sources'), bootstrap=str(work / 'bootstrap'),
                   install_tree=str(Path(args.install_tree).resolve()),
                   spack=str(work / 'spack/bin/spack'),
                   stop_epoch=time.time() + args.stop_after)
    write_json(attempt / 'options.json', options)
    state = {'complete': False, 'installed': False, 'published': False, 'error': None,
             'environment': str(environment), 'nodes': args.nodes}
    write_json(attempt / 'status.json', state)

    def child_environment(base=None):
        env = dict(os.environ if base is None else base)
        env.update(SPACK_USER_CACHE_PATH=str(work / 'cache'), TMPDIR=str(temporary),
                   PYTHONPATH=str(HELPER.parent.parent) + os.pathsep + env.get('PYTHONPATH', ''))
        # Enable the user scope prepared by spack isolate.
        env.pop('SPACK_ENV', None)
        if base is None:
            env.pop('SPACK_DISABLE_LOCAL_CONFIG', None)
        return env

    def run(argv, cwd=None, env=None):
        execution.command(argv, attempt / 'prepare.log', stop,
                          env=child_environment(env), cwd=cwd)

    try:
        with logs.sections.section('prepare', 'Prepare pinned Spack and environment'):
            spack = prepare_environment(args, work, attempt, run)
        worker_command = [sys.executable, '-m', 'rad_bat.environment', str(attempt / 'options.json')]
        launcher = launcher + worker_command
        with logs.sections.section('install', 'Install environment on {} node(s)'.format(args.nodes), collapsed=False):
            if not (work / 'installed').exists():
                allocation.launch_workers(launcher, attempt, stop, env=child_environment())
                workers = [json.loads(p.read_text()) for p in attempt.glob('workers/*/status.json')]
                if len(workers) != args.nodes or any(w['returncode'] != 0 for w in workers):
                    raise RadBatError('One or more installation workers did not complete successfully')
                if len({w['host'] for w in workers}) != args.nodes:
                    raise RadBatError('Expected one installation worker per node')
            run([spack, '-e', environment, 'python', '-m', 'rad_bat.spack_helpers', 'verify', attempt / 'installed.json'])
            (work / 'installed').touch()
            state['installed'] = True
            write_json(attempt / 'status.json', state)
        if args.push_to_buildcache:
            with logs.sections.section('publish', 'Publish completed environment'):
                def upload(argv, cwd=None, env=None):
                    execution.command(argv, attempt / 'publish.log', finish,
                                      env=child_environment(env), cwd=cwd)
                publish(spack, environment, run=upload)
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
    env.pop('SPACK_DISABLE_LOCAL_CONFIG', None)
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
    try:
        with execution.interruptible():
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
