"""Shared pinned Spack setup for project and environment workflows."""

import json
import os
import fcntl
from contextlib import contextmanager
from pathlib import Path
from typing import List, Optional

from .config import ProjectConfig
from .errors import RadBatError
from .runner import capture_command, run_command


def _resolve_from_root(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def _git_checkout(url: str, commit: str, destination: Path, run=None) -> None:
    run = run or run_command
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not (destination / ".git").is_dir():
        raise RadBatError(
            "managed checkout path exists but is not a Git repository: {}".format(destination)
        )
    if not destination.exists():
        run(["git", "init", str(destination)])
        run(["git", "-C", str(destination), "remote", "add", "origin", url])
    else:
        current = capture_command(["git", "-C", str(destination), "rev-parse", "HEAD"])
        if current.lower() == commit.lower():
            return
        if current:
            raise RadBatError("Spack checkout has a different commit; use a new workspace")
    run(
        ["git", "-C", str(destination), "fetch", "--depth", "1", "origin", commit]
    )
    run(
        ["git", "-C", str(destination), "checkout", "--detach", "FETCH_HEAD"]
    )


def _spack_executable(checkout: Path) -> Path:
    executable = checkout / "bin" / "spack"
    if not executable.is_file():
        raise RadBatError("managed Spack executable was not found: {}".format(executable))
    return executable


def _run_spack(executable: Path, arguments: List[str], cwd: Optional[Path] = None, run=None,
               initial=False) -> None:
    run = run or run_command
    environment = os.environ.copy()
    # ``spack isolate`` makes its replacement user scope conditional on this
    # variable being absent. Do not let a caller's shell disable that scope.
    environment.pop("SPACK_DISABLE_LOCAL_CONFIG", None)
    environment.pop("SPACK_ENV", None)
    environment['PYTHONPATH'] = str(Path(__file__).resolve().parent.parent)
    environment['SPACK_USER_CACHE_PATH'] = str(executable.parent.parent.parent / 'cache')
    if initial:
        environment['SPACK_DISABLE_LOCAL_CONFIG'] = '1'
    run([str(executable)] + arguments, cwd=cwd, env=environment)


def _prepare_isolation(checkout: Path, isolation: Path, run=None) -> None:
    _run_spack(_spack_executable(checkout),
               ['python', '-m', 'rad_bat.spack_helpers', 'check'], run=run, initial=True)
    ready = checkout.parent / 'isolated'
    if ready.is_file():
        return
    _run_spack(
        _spack_executable(checkout),
        ["isolate", "--overwrite", "--path", str(isolation)],
        run=run,
        initial=True,
    )
    ready.touch()


@contextmanager
def workspace_lock(work):
    """One coordinator per scenario; Spack workers use their native prefix locks."""
    work.mkdir(parents=True, exist_ok=True)
    with (work / '.rad-bat.lock').open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RadBatError('Workspace is already in use: {}'.format(work))
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def create_environment(spack, source, destination, run=None):
    """Spack owns environment creation, include copying and path relocation."""
    _run_spack(spack, ['python', '-m', 'rad_bat.spack_helpers', 'create',
                      str(source), str(destination)], run=run)


def _prepare_repositories(
    config: ProjectConfig, spack: Path, environment: Path, managed_root: Path
) -> None:
    """Translate developer JSON pins into native Spack repository configuration."""
    assert config.spack is not None
    repositories = {}
    for index, repository in enumerate(config.spack.repositories):
        name = "rad_bat_{}".format(index)
        if repository.path:
            path = _resolve_from_root(config.root, repository.path)
            if not path.is_dir():
                raise RadBatError("local Spack repository does not exist: {}".format(path))
            repositories[name] = str(path)
        else:
            entry = {
                "git": repository.url,
                "commit": repository.commit,
                "destination": str(managed_root / "repositories" / name / repository.commit),
            }
            if repository.subdirectory:
                entry["paths"] = [repository.subdirectory]
            repositories[name] = entry
    if repositories:
        options = json.dumps({"environment": str(environment), "repos": repositories})
        _run_spack(spack, ["python", '-m', 'rad_bat.spack_helpers',
                          "repositories", options])


def configure_storage(spack, environment, install_tree, buildcache=None,
                      username=None, password=None, upstreams=(), read_buildcaches=(), run=None):
    """Configure a durable install tree and an optional binary mirror without autopush."""
    _run_spack(spack, ['-e', str(environment), 'config', 'add',
                      'config:install_tree:root:{}'.format(install_tree)], run=run)
    if buildcache:
        arguments = ['-e', str(environment), 'mirror', 'add', '--scope',
                     'env:{}'.format(environment), '--type', 'binary', '--unsigned']
        if username:
            arguments += ['--oci-username-variable', username]
        if password:
            arguments += ['--oci-password-variable', password]
        _run_spack(spack, arguments + ['rad-bat', buildcache], run=run)
    for index, upstream in enumerate(upstreams):
        _run_spack(spack, ['-e', str(environment), 'config', 'add',
                          'upstreams:rad_bat_{}:install_tree:{}'.format(index, upstream)], run=run)
    for index, url in enumerate(read_buildcaches):
        _run_spack(spack, ['-e', str(environment), 'mirror', 'add', '--scope',
                          'env:{}'.format(environment), '--type', 'binary', '--unsigned',
                          'rad-bat-read-{}'.format(index), url], run=run)
    _run_spack(spack, ['-e', str(environment), 'python',
                      '-m', 'rad_bat.spack_helpers', 'disable-autopush'], run=run)


def publish(spack, environment, only=None, run=None):
    """Let Spack select packages and skip existing entries after workflow success."""
    arguments = ['-e', str(environment), 'buildcache', 'push', '--unsigned',
                 '--allow-missing', '--update-index']
    if only:
        arguments += ['--only', only]
    _run_spack(spack, arguments + ['rad-bat'], run=run)
