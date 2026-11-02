"""Command expansion and execution."""

import os
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .errors import RadBatError
from . import logs


def scheduler_pass_fds(environment: Optional[Dict[str, str]] = None) -> Tuple[int, ...]:
    """Return scheduler communication descriptors that children must inherit."""

    values = environment if environment is not None else os.environ
    value = values.get("PMI_FD")
    if value is None:
        return ()
    try:
        descriptor = int(value)
        if descriptor < 0:
            return ()
        os.fstat(descriptor)
    except (OSError, ValueError):
        return ()
    return (descriptor,)


def expand_command(command: List[str], values: Dict[str, str]) -> List[str]:
    """Replace supported whole-argument placeholders in *command*."""

    expanded = []
    for argument in command:
        if argument.startswith("{") and argument.endswith("}"):
            name = argument[1:-1]
            if name not in values:
                raise RadBatError("no value is available for placeholder {}".format(argument))
            expanded.append(values[name])
        elif "{" in argument or "}" in argument:
            raise RadBatError("partial command placeholder is not allowed: {}".format(argument))
        else:
            expanded.append(argument)
    return expanded


def run_command(
    command: List[str],
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
) -> None:
    """Run a command and turn process failures into concise diagnostics."""

    display = " ".join(command)
    logs.command(command)
    environment = env if env is not None else os.environ.copy()
    try:
        subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            env=environment,
            pass_fds=scheduler_pass_fds(environment),
            check=True,
        )
    except FileNotFoundError:
        raise RadBatError("command not found: {}".format(command[0]))
    except subprocess.CalledProcessError as error:
        raise RadBatError("command failed with exit code {}: {}".format(error.returncode, display))


def capture_command(command: List[str], cwd: Optional[Path] = None) -> str:
    """Run a command and return its standard output without logging it."""

    try:
        result = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            pass_fds=scheduler_pass_fds(),
            universal_newlines=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return ""
    return result.stdout.strip()
