"""Host-config and native-Spack workflows."""

import os
import shutil
import fcntl
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

from .config import ProjectConfig
from .errors import RadBatError
from . import logs
from .runner import expand_command, run_command
from .spack import (
    _resolve_from_root, _git_checkout, _spack_executable, _prepare_isolation,
    _prepare_repositories, _run_spack, configure_storage, publish,
)


def _project_command(
    config: ProjectConfig,
    override: Optional[List[str]],
    host_config: Path,
    work_dir: Path,
    jobs: int,
) -> List[str]:
    command = override if override else config.command
    if not command:
        raise RadBatError("the project command cannot be empty")
    return expand_command(
        command,
        {
            "host_config": str(host_config),
            "work_dir": str(work_dir),
            "source": str(config.root),
            "jobs": str(jobs),
        },
    )


def _project_spec(
    config: ProjectConfig,
    spec: str,
    environment: Optional[Dict[str, str]] = None,
) -> str:
    values = os.environ if environment is None else environment
    parts = ["{}@develop".format(config.package), spec]
    assert config.spack is not None
    for fragment in config.spack.spec_fragments:
        reference = values.get(fragment.if_env, "")
        if reference:
            parts.append(
                fragment.value.replace("{{{}}}".format(fragment.if_env), reference)
            )
    return " ".join(part.strip() for part in parts if part.strip())


def run_host_config(
    config: ProjectConfig,
    host_config: str,
    work_dir: Optional[str],
    jobs: int,
    command: Optional[List[str]],
) -> None:
    path = _resolve_from_root(config.root, host_config)
    if not path.is_file():
        raise RadBatError("host-config does not exist: {}".format(path))
    resolved_work_dir = (
        _resolve_from_root(config.root, work_dir)
        if work_dir
        else config.root / ".rad-bat-work"
    )
    resolved_work_dir.mkdir(parents=True, exist_ok=True)
    with logs.sections.section("project", "Project build and test", collapsed=False):
        run_command(
            _project_command(config, command, path, resolved_work_dir, jobs),
            cwd=config.root,
        )


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
    work_dir: str,
    spack_env: Optional[str],
    install_tree_path: Optional[str],
    output_dir_path: Optional[str],
    upstreams: List[str],
    buildcache: Optional[str],
    buildcache_username_variable: Optional[str],
    buildcache_password_variable: Optional[str],
    push_to_buildcache: bool,
    host_config_name: Optional[str],
    jobs: int,
    command: Optional[List[str]],
) -> None:
    if config.spack is None:
        raise RadBatError("the project configuration has no spack section")
    if push_to_buildcache and not buildcache:
        raise RadBatError("--push-to-buildcache requires --buildcache")
    resolved_work_dir = _resolve_from_root(config.root, work_dir)
    resolved_work_dir.mkdir(parents=True, exist_ok=True)
    managed_root = resolved_work_dir / ".rad-bat"
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
        else resolved_work_dir / "install"
    )
    host_configs = (
        _resolve_from_root(config.root, output_dir_path)
        if output_dir_path
        else resolved_work_dir / "host-configs"
    )
    install_tree.mkdir(parents=True, exist_ok=True)
    host_configs.mkdir(parents=True, exist_ok=True)
    project_spec = _project_spec(config, spec)

    with logs.sections.section("spack_setup", "Preparing Spack environment"):
        _git_checkout(config.spack.url, config.spack.commit, checkout)
        spack = _spack_executable(checkout)
        _prepare_isolation(checkout, isolation, config.spack.commit, run=run_command)
        _reset_environment(_render_machine_environment(config), environment)
        _prepare_repositories(config, spack, environment, managed_root)

        configure_storage(spack, environment, install_tree, buildcache,
                          buildcache_username_variable, buildcache_password_variable)
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

    with logs.sections.section(
        "dependencies", "Concretizing and installing dependencies", collapsed=False
    ):
        # RADIUSS CI jobs traditionally provide the variants, compiler, and
        # dependency constraints only.  Give Spack the project root explicitly;
        # anonymous specs cannot be added to an environment.
        _run_spack(spack, ["-e", str(environment), "add", project_spec])
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
                    publish(spack, environment)
        generated = _find_generated_host_config(config.root, before)
        output_name = host_config_name or generated.name
        if Path(output_name).name != output_name or not output_name.endswith(".cmake"):
            raise RadBatError("--host-config-name must be a .cmake filename without a directory")
        retained = host_configs / output_name
        shutil.copy2(str(generated), str(retained))
        logs.info("Retained generated host-config: {}".format(retained))

    with logs.sections.section("project", "Project build and test", collapsed=False):
        run_command(
            _project_command(config, command, retained, resolved_work_dir, jobs),
            cwd=config.root,
        )
