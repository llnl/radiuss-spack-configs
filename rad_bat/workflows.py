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
    _prepare_repositories, _run_spack, create_environment, workspace_lock, configure_storage, publish,
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
    value = config.spack.environment
    for placeholder, variable in (("sys_type", "SYS_TYPE"), ("machine", "LCSCHEDCLUSTER")):
        token = "{" + placeholder + "}"
        if token in value:
            if not os.environ.get(variable):
                raise RadBatError(variable + " is required; alternatively pass --spack-env")
            value = value.replace(token, os.environ[variable])
    if "{" in value or "}" in value:
        raise RadBatError("unsupported placeholder in spack.environment: {}".format(value))
    path = _resolve_from_root(config.root, value)
    if not path.is_file():
        raise RadBatError("Spack machine environment does not exist: {}".format(path))
    return path


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
    environment = managed_root / "spack-env"
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
    with workspace_lock(managed_root):
        with logs.sections.section("spack_setup", "Prepare or resume Spack environment"):
            _git_checkout(config.spack.url, config.spack.commit, checkout)
            spack = _spack_executable(checkout)
            _prepare_isolation(checkout, isolation, run=run_command)
            prepared = managed_root / "prepared"
            if not prepared.exists():
                template = (_resolve_from_root(config.root, spack_env) if spack_env
                            else _render_machine_environment(config))
                if not template.is_file():
                    raise RadBatError("Spack machine environment does not exist: {}".format(template))
                create_environment(spack, template, environment)
                _prepare_repositories(config, spack, environment, managed_root)
                configure_storage(
                    spack, environment, install_tree, buildcache,
                    buildcache_username_variable, buildcache_password_variable,
                    upstreams=[_resolve_from_root(config.root, path) for path in upstreams],
                )
                _run_spack(spack, ["-e", str(environment), "add", _project_spec(config, spec)])
                _run_spack(spack, ["-e", str(environment), "develop", "--no-clone", "--path",
                                  str(config.root), "{}@develop".format(config.package)])
                with logs.sections.section("concretize", "Concretize project dependencies"):
                    _run_spack(spack, ["-e", str(environment), "concretize"])
                    _run_spack(spack, ["-e", str(environment), "python", "-m",
                                      "rad_bat.spack_helpers", "freeze"])
                prepared.touch()
            else:
                logs.info("Resuming concrete environment: {}. Inputs are not refreshed; "
                          "use a new workspace for changes.".format(environment))

        # The durable copy, rather than an old file in the source checkout, marks
        # completion. Artifact collection directories can disappear between CI attempts.
        completed = managed_root / "host-config"
        with logs.sections.section("dependencies", "Prepare project host-config", collapsed=False):
            if completed.exists():
                retained = Path(completed.read_text().strip())
                if not retained.is_file():
                    raise RadBatError("Retained host-config is missing: {}".format(retained))
            else:
                before = _snapshot_host_configs(config.root)
                with _exclusive_install_tree(install_tree):
                    _run_spack(spack, ["-e", str(environment), "install", "--only-concrete",
                                      "--until", config.spack.until, "--jobs", str(jobs)],
                               cwd=config.root)
                generated = _find_generated_host_config(config.root, before)
                output_name = host_config_name or generated.name
                if Path(output_name).name != output_name or not output_name.endswith(".cmake"):
                    raise RadBatError("--host-config-name must be a .cmake filename without a directory")
                retained = managed_root / "host-configs" / output_name
                retained.parent.mkdir(exist_ok=True)
                shutil.copy2(str(generated), str(retained))
                pending = completed.with_suffix('.tmp')
                pending.write_text(str(retained) + "\n")
                pending.replace(completed)
            exported = host_configs / retained.name
            if exported != retained:
                shutil.copy2(str(retained), str(exported))
            logs.info("Retained generated host-config: {}".format(retained))

        if push_to_buildcache:
            with logs.sections.section("buildcache", "Publish completed dependencies"):
                publish(spack, environment, only="dependencies")
        with logs.sections.section("project", "Project build and test", collapsed=False):
            run_command(_project_command(config, command, exported, resolved_work_dir, jobs),
                        cwd=config.root)
