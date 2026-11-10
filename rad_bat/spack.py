"""Shared pinned Spack setup for project and environment workflows."""

import hashlib
import json
import os
from pathlib import Path
from typing import List, Optional

from .config import ProjectConfig, RepositoryConfig
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
        run(["git", "-C", str(destination), "remote", "set-url", "origin", url])
        current = capture_command(["git", "-C", str(destination), "rev-parse", "HEAD"])
        if current.lower() == commit.lower():
            return
    run(
        ["git", "-C", str(destination), "fetch", "--depth", "1", "origin", commit]
    )
    run(
        ["git", "-C", str(destination), "checkout", "--force", "--detach", "FETCH_HEAD"]
    )


def _spack_executable(checkout: Path) -> Path:
    executable = checkout / "bin" / "spack"
    if not executable.is_file():
        raise RadBatError("managed Spack executable was not found: {}".format(executable))
    return executable


def _run_spack(executable: Path, arguments: List[str], cwd: Optional[Path] = None, run=None) -> None:
    run = run or run_command
    environment = os.environ.copy()
    # ``spack isolate`` makes its replacement user scope conditional on this
    # variable being absent. Do not let a caller's shell disable that scope.
    environment.pop("SPACK_DISABLE_LOCAL_CONFIG", None)
    run([str(executable)] + arguments, cwd=cwd, env=environment)


def _prepare_isolation(checkout: Path, isolation: Path, commit: str, run=None) -> None:
    state_path = checkout.parent / "isolation-state.json"
    expected = {"commit": commit, "path": str(isolation)}
    current = None
    try:
        current = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    if current == expected and (checkout / "etc" / "spack" / "isolate").is_dir():
        return
    _run_spack(
        _spack_executable(checkout),
        ["isolate", "--overwrite", "--path", str(isolation)],
        run=run,
    )
    state_path.write_text(json.dumps(expected, sort_keys=True) + "\n", encoding="utf-8")


def _repository_checkout_name(repository: RepositoryConfig) -> str:
    assert repository.url is not None and repository.commit is not None
    identity = repository.url + "\0" + repository.commit
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]


def _prepare_repositories(
    config: ProjectConfig, spack: Path, environment: Path, managed_root: Path
) -> None:
    assert config.spack is not None
    # Add in reverse because ``spack repo add`` gives the newly added repository
    # highest precedence.
    for repository in reversed(config.spack.repositories):
        if repository.path:
            path = _resolve_from_root(config.root, repository.path)
            if not path.is_dir():
                raise RadBatError("local Spack repository does not exist: {}".format(path))
        else:
            assert repository.url is not None and repository.commit is not None
            checkout = managed_root / "repositories" / _repository_checkout_name(repository)
            _git_checkout(repository.url, repository.commit, checkout)
            path = checkout / repository.subdirectory if repository.subdirectory else checkout
            if not path.is_dir():
                raise RadBatError("remote Spack repository path does not exist: {}".format(path))
        _run_spack(
            spack,
            [
                "-e",
                str(environment),
                "repo",
                "add",
                "--scope",
                "env:{}".format(environment),
                str(path),
            ],
        )



def configure_storage(spack, environment, install_tree, buildcache=None,
                      username=None, password=None, run=None):
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
    _run_spack(spack, ['-e', str(environment), 'python',
                      str(Path(__file__).with_name('spack_helpers.py')), 'disable-autopush'], run=run)


def publish(spack, environment, only='dependencies', specs=(), run=None):
    """Publish after the calling workflow has confirmed installation success."""
    _run_spack(spack, ['-e', str(environment), 'buildcache', 'push', '--only', only,
                      '--unsigned', 'rad-bat'] + list(specs), run=run)
