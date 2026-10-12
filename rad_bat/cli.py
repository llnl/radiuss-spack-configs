"""Command-line interface for rad-bat."""

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional

from .config import load_project_config
from .errors import RadBatError
from .workflows import run_host_config, run_spack


def _positive_integer(value: str) -> int:
    try:
        result = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("must be an integer")
    if result < 1:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return result


def _default_jobs() -> int:
    return os.cpu_count() or 1


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source", default=".", help="project source directory")
    parser.add_argument("--jobs", type=_positive_integer, default=_default_jobs())
    parser.add_argument("command", nargs=argparse.REMAINDER, help="project command after --")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rad-bat")
    subparsers = parser.add_subparsers(dest="mode", required=True)

    host_config = subparsers.add_parser(
        "host-config", help="build using an existing host-config without invoking Spack"
    )
    host_config.add_argument("--host-config", required=True)
    host_config.add_argument("--dest")
    _add_common(host_config)

    spack = subparsers.add_parser("spack", help="generate a host-config with native Spack")
    spack.add_argument("--spec", required=True)
    spack.add_argument("--dest", required=True)
    spack.add_argument("--spack-env")
    spack.add_argument("--install-tree")
    spack.add_argument("--output-dir")
    spack.add_argument("--upstream", action="append", default=[])
    spack.add_argument("--buildcache")
    spack.add_argument("--push-to-buildcache", action="store_true")
    spack.add_argument("--host-config-name")
    _add_common(spack)

    subparsers.add_parser("ci", help="translate CI environment variables to a workflow")
    return parser


def _command(value: List[str]) -> Optional[List[str]]:
    if value and value[0] == "--":
        value = value[1:]
    return value or None


def _truth(value: Optional[str]) -> bool:
    if value is None:
        return False
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off", ""}:
        return False
    raise RadBatError("invalid boolean value: {}".format(value))


def _ci_value(name: str, legacy: Optional[str] = None) -> Optional[str]:
    value = os.environ.get(name)
    if value is None and legacy:
        value = os.environ.get(legacy)
    return value


def _required_ci(name: str, legacy: Optional[str] = None) -> str:
    value = _ci_value(name, legacy)
    if not value:
        names = name if not legacy else "{} (or {})".format(name, legacy)
        raise RadBatError("{} is required in CI mode".format(names))
    return value


def _run_ci() -> None:
    mode = _required_ci("RAD_BAT_MODE")
    source = Path(_ci_value("RAD_BAT_SOURCE_DIR") or os.environ.get("CI_PROJECT_DIR", "."))
    config = load_project_config(source)
    try:
        jobs = _positive_integer(_ci_value("RAD_BAT_JOBS") or str(_default_jobs()))
    except argparse.ArgumentTypeError as error:
        raise RadBatError("RAD_BAT_JOBS {}".format(error))
    if mode == "host-config":
        run_host_config(
            config,
            _required_ci("RAD_BAT_HOST_CONFIG", "HOST_CONFIG"),
            _ci_value("RAD_BAT_DEST"),
            jobs,
            None,
        )
        return
    if mode != "spack":
        raise RadBatError("RAD_BAT_MODE must be host-config or spack")
    upstream_value = _ci_value("RAD_BAT_UPSTREAMS") or ""
    upstreams = [value for value in upstream_value.split(os.pathsep) if value]
    run_spack(
        config,
        _required_ci("RAD_BAT_SPEC", "SPEC"),
        _required_ci("RAD_BAT_DEST"),
        _ci_value("RAD_BAT_SPACK_ENV"),
        _required_ci("RAD_BAT_INSTALL_TREE"),
        _ci_value("RAD_BAT_OUTPUT_DIR"),
        upstreams,
        _ci_value("RAD_BAT_BUILDCACHE"),
        _truth(_ci_value("RAD_BAT_PUSH_TO_BUILDCACHE", "PUSH_TO_REGISTRY")),
        _ci_value("RAD_BAT_HOST_CONFIG_NAME"),
        jobs,
        None,
    )


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        if arguments.mode == "ci":
            _run_ci()
            return 0
        config = load_project_config(Path(arguments.source))
        if arguments.mode == "host-config":
            run_host_config(
                config,
                arguments.host_config,
                arguments.dest,
                arguments.jobs,
                _command(arguments.command),
            )
        else:
            run_spack(
                config,
                arguments.spec,
                arguments.dest,
                arguments.spack_env,
                arguments.install_tree,
                arguments.output_dir,
                arguments.upstream,
                arguments.buildcache,
                arguments.push_to_buildcache,
                arguments.host_config_name,
                arguments.jobs,
                _command(arguments.command),
            )
        return 0
    except RadBatError as error:
        print("rad-bat: error: {}".format(error), file=sys.stderr)
        return 2
