"""Command expansion and execution."""

import os
import json
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .errors import RadBatError
from . import logs


def load_modules() -> None:
    """Apply the documented MODULE_LIST to rad-bat and all its children."""
    try:
        modules = shlex.split(os.environ.get('MODULE_LIST', ''))
    except ValueError as error:
        raise RadBatError('Invalid quoting in MODULE_LIST: {}'.format(error))
    if not modules:
        return
    script = r'''
set -e
if ! type module >/dev/null 2>&1; then
    for init in /etc/profile.d/modules.sh /etc/profile.d/lmod.sh /usr/share/Modules/init/bash; do
        if test -f "$init"; then source "$init" >&2; break; fi
    done
fi
python_executable=$1
shift
module load "$@" >&2
exec "$python_executable" -c 'import json, os; print(json.dumps(dict(os.environ)))'
'''
    with logs.sections.section('modules', 'Load requested modules'):
        try:
            result = subprocess.run(['bash', '-c', script, 'rad-bat-modules', sys.executable] + modules,
                                    stdout=subprocess.PIPE, text=True, check=True,
                                    pass_fds=scheduler_pass_fds())
            updated = json.loads(result.stdout)
        except (OSError, subprocess.CalledProcessError, ValueError) as error:
            raise RadBatError('Could not load MODULE_LIST: {}'.format(error))
        os.environ.clear()
        os.environ.update(updated)


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
