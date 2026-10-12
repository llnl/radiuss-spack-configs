"""Host-config and native-Spack workflows."""

import hashlib
import json
import os
import shutil
import fcntl
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

from .config import ProjectConfig, RepositoryConfig
from .errors import RadBatError
from . import logs
from .runner import capture_command, expand_command, run_command


def _resolve_from_root(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def _project_command(
    config: ProjectConfig,
    override: Optional[List[str]],
    host_config: Path,
    dest: Path,
    jobs: int,
) -> List[str]:
    command = override if override else config.command
    if not command:
        raise RadBatError("the project command cannot be empty")
    return expand_command(
        command,
        {
            "host_config": str(host_config),
            "dest": str(dest),
            "source": str(config.root),
            "jobs": str(jobs),
        },
    )


def run_host_config(
    config: ProjectConfig,
    host_config: str,
    dest: Optional[str],
    jobs: int,
    command: Optional[List[str]],
) -> None:
    path = _resolve_from_root(config.root, host_config)
    if not path.is_file():
        raise RadBatError("host-config does not exist: {}".format(path))
    destination = (
        _resolve_from_root(config.root, dest) if dest else config.root / ".rad-bat-work"
    )
    destination.mkdir(parents=True, exist_ok=True)
    with logs.sections.section("project", "Project build and test", collapsed=False):
        run_command(
            _project_command(config, command, path, destination, jobs), cwd=config.root
        )


def _git_checkout(url: str, commit: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not (destination / ".git").is_dir():
        raise RadBatError(
            "managed checkout path exists but is not a Git repository: {}".format(destination)
        )
    if not destination.exists():
        run_command(["git", "init", str(destination)])
        run_command(["git", "-C", str(destination), "remote", "add", "origin", url])
    else:
        run_command(["git", "-C", str(destination), "remote", "set-url", "origin", url])
        current = capture_command(["git", "-C", str(destination), "rev-parse", "HEAD"])
        if current.lower() == commit.lower():
            return
    run_command(
        ["git", "-C", str(destination), "fetch", "--depth", "1", "origin", commit]
    )
    run_command(
        ["git", "-C", str(destination), "checkout", "--force", "--detach", "FETCH_HEAD"]
    )


def _spack_executable(checkout: Path) -> Path:
    executable = checkout / "bin" / "spack"
    if not executable.is_file():
        raise RadBatError("managed Spack executable was not found: {}".format(executable))
    return executable


def _run_spack(executable: Path, arguments: List[str], cwd: Optional[Path] = None) -> None:
    environment = os.environ.copy()
    # ``spack isolate`` makes its replacement user scope conditional on this
    # variable being absent. Do not let a caller's shell disable that scope.
    environment.pop("SPACK_DISABLE_LOCAL_CONFIG", None)
    run_command([str(executable)] + arguments, cwd=cwd, env=environment)


def _prepare_isolation(checkout: Path, isolation: Path, commit: str) -> None:
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
    )
    state_path.write_text(json.dumps(expected, sort_keys=True) + "\n", encoding="utf-8")


def _render_machine_environment(config: ProjectConfig) -> Path:
    assert config.spack is not None
    sys_type = os.environ.get("SYS_TYPE", "")
    value = config.spack.environment
    if "{sys_type}" in value:
        if not sys_type:
            raise RadBatError(
                "SYS_TYPE is required because spack.environment contains {sys_type}"
            )
        value = value.replace("{sys_type}", sys_type)
    if "{" in value or "}" in value:
        raise RadBatError("unsupported placeholder in spack.environment: {}".format(value))
    path = _resolve_from_root(config.root, value)
    if not path.is_file():
        raise RadBatError("Spack machine environment does not exist: {}".format(path))
    return path


def _reset_environment(template: Path, destination: Path) -> None:
    if destination.exists():
        if not (destination / "spack.yaml").is_file():
            raise RadBatError(
                "refusing to replace a non-Spack environment: {}".format(destination)
            )
        shutil.rmtree(str(destination))
    shutil.copytree(str(template.parent), str(destination))


@contextmanager
def _exclusive_install_tree(install_tree: Path) -> Iterator[None]:
    """Serialize writes to a persistent install tree across refresh jobs."""

    install_tree.mkdir(parents=True, exist_ok=True)
    lock_path = install_tree / ".rad-bat-write.lock"
    try:
        lock_stream = lock_path.open("a+", encoding="utf-8")
    except OSError as error:
        raise RadBatError("cannot open install-tree lock {}: {}".format(lock_path, error))
    with lock_stream:
        logs.info("Waiting for exclusive access to install tree: {}".format(install_tree))
        try:
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX)
        except OSError as error:
            raise RadBatError("cannot lock install tree {}: {}".format(install_tree, error))
        previous_umask = os.umask(0o002)
        try:
            yield
        finally:
            os.umask(previous_umask)
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_UN)


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
            ["repo", "add", "--scope", "env:{}".format(environment), str(path)],
        )


def _snapshot_host_configs(source: Path) -> Dict[Path, Tuple[int, int]]:
    return {
        path: (path.stat().st_mtime_ns, path.stat().st_size)
        for path in source.glob("*.cmake")
        if path.is_file()
    }


def _find_generated_host_config(
    source: Path, before: Dict[Path, Tuple[int, int]]
) -> Path:
    changed = []
    for path in source.glob("*.cmake"):
        if not path.is_file():
            continue
        state = (path.stat().st_mtime_ns, path.stat().st_size)
        if before.get(path) != state:
            changed.append(path)
    if len(changed) != 1:
        raise RadBatError(
            "expected exactly one generated top-level .cmake file in {}, found {}: {}".format(
                source, len(changed), ", ".join(str(path) for path in changed) or "none"
            )
        )
    return changed[0]


def run_spack(
    config: ProjectConfig,
    spec: str,
    dest: str,
    spack_env: Optional[str],
    install_tree_path: Optional[str],
    output_dir_path: Optional[str],
    upstreams: List[str],
    buildcache: Optional[str],
    push_to_buildcache: bool,
    host_config_name: Optional[str],
    jobs: int,
    command: Optional[List[str]],
) -> None:
    if config.spack is None:
        raise RadBatError("the project configuration has no spack section")
    if push_to_buildcache and not buildcache:
        raise RadBatError("--push-to-buildcache requires --buildcache")
    destination = _resolve_from_root(config.root, dest)
    destination.mkdir(parents=True, exist_ok=True)
    managed_root = destination / ".rad-bat"
    checkout = managed_root / "spack"
    isolation = managed_root / "isolation"
    environment = (
        _resolve_from_root(config.root, spack_env)
        if spack_env
        else managed_root / "spack-env"
    )
    install_tree = (
        _resolve_from_root(config.root, install_tree_path)
        if install_tree_path
        else destination / "install"
    )
    host_configs = (
        _resolve_from_root(config.root, output_dir_path)
        if output_dir_path
        else destination / "host-configs"
    )
    install_tree.mkdir(parents=True, exist_ok=True)
    host_configs.mkdir(parents=True, exist_ok=True)

    with logs.sections.section("spack_setup", "Preparing Spack environment"):
        _git_checkout(config.spack.url, config.spack.commit, checkout)
        spack = _spack_executable(checkout)
        _prepare_isolation(checkout, isolation, config.spack.commit)
        _reset_environment(_render_machine_environment(config), environment)
        _prepare_repositories(config, spack, environment, managed_root)

        _run_spack(
            spack,
            [
                "-e",
                str(environment),
                "config",
                "add",
                "config:install_tree:root:{}".format(install_tree),
            ],
        )
        for index, upstream in enumerate(upstreams):
            upstream_path = _resolve_from_root(config.root, upstream)
            _run_spack(
                spack,
                [
                    "-e",
                    str(environment),
                    "config",
                    "add",
                    "upstreams:rad_bat_{}:install_tree:{}".format(index, upstream_path),
                ],
            )
        if buildcache:
            _run_spack(
                spack,
                [
                    "-e",
                    str(environment),
                    "mirror",
                    "add",
                    "--scope",
                    "env:{}".format(environment),
                    "--type",
                    "binary",
                    "--unsigned",
                    "rad-bat",
                    buildcache,
                ],
            )

    with logs.sections.section(
        "dependencies", "Concretizing and installing dependencies", collapsed=False
    ):
        _run_spack(spack, ["-e", str(environment), "add", spec])
        _run_spack(
            spack,
            [
                "-e",
                str(environment),
                "develop",
                "--no-clone",
                "--path",
                str(config.root),
                "{}@develop".format(config.package),
            ],
        )
        _run_spack(spack, ["-e", str(environment), "concretize"])
        before = _snapshot_host_configs(config.root)
        with _exclusive_install_tree(install_tree):
            _run_spack(
                spack,
                ["-e", str(environment), "install", "--until", "initconfig", "--jobs", str(jobs)],
                cwd=config.root,
            )
            if push_to_buildcache:
                with logs.sections.section(
                    "buildcache", "Publishing dependencies to buildcache"
                ):
                    _run_spack(
                        spack,
                        [
                            "-e",
                            str(environment),
                            "buildcache",
                            "push",
                            "--only",
                            "dependencies",
                            "--unsigned",
                            "rad-bat",
                        ],
                    )
        generated = _find_generated_host_config(config.root, before)
        output_name = host_config_name or generated.name
        if Path(output_name).name != output_name or not output_name.endswith(".cmake"):
            raise RadBatError("--host-config-name must be a .cmake filename without a directory")
        retained = host_configs / output_name
        shutil.copy2(str(generated), str(retained))
        logs.info("Retained generated host-config: {}".format(retained))

    with logs.sections.section("project", "Project build and test", collapsed=False):
        run_command(
            _project_command(config, command, retained, destination, jobs), cwd=config.root
        )
