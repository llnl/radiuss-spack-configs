"""Load and validate ``.rad-bat.json``."""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .errors import RadBatError


FULL_COMMIT = re.compile(r"^[0-9a-fA-F]{40}$")
PLACEHOLDERS = {"{host_config}", "{dest}", "{source}", "{jobs}"}


@dataclass(frozen=True)
class RepositoryConfig:
    path: Optional[str] = None
    url: Optional[str] = None
    commit: Optional[str] = None
    subdirectory: Optional[str] = None


@dataclass(frozen=True)
class SpackConfig:
    url: str
    commit: str
    environment: str
    repositories: List[RepositoryConfig]


@dataclass(frozen=True)
class ProjectConfig:
    root: Path
    package: str
    command: List[str]
    spack: Optional[SpackConfig]


def _object(value: Any, location: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise RadBatError("{} must be a JSON object".format(location))
    return value


def _string(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RadBatError("{} must be a non-empty string".format(location))
    return value


def _only_keys(value: Dict[str, Any], allowed: set, location: str) -> None:
    unexpected = sorted(set(value) - allowed)
    if unexpected:
        raise RadBatError(
            "{} contains unsupported key(s): {}".format(location, ", ".join(unexpected))
        )


def _validate_command(value: Any) -> List[str]:
    if not isinstance(value, list) or not value:
        raise RadBatError("project.command must be a non-empty JSON array")
    command = []
    for index, argument in enumerate(value):
        argument = _string(argument, "project.command[{}]".format(index))
        if ("{" in argument or "}" in argument) and argument not in PLACEHOLDERS:
            raise RadBatError(
                "project.command[{}] uses an unsupported or partial placeholder: {}".format(
                    index, argument
                )
            )
        command.append(argument)
    return command


def _validate_repository(value: Any, index: int) -> RepositoryConfig:
    location = "spack.repositories[{}]".format(index)
    repository = _object(value, location)
    _only_keys(repository, {"path", "url", "commit", "subdirectory"}, location)
    has_path = "path" in repository
    has_remote = "url" in repository or "commit" in repository
    if has_path == has_remote:
        raise RadBatError(
            "{} must contain either path, or both url and commit".format(location)
        )
    if has_path:
        if "subdirectory" in repository:
            raise RadBatError("{}.subdirectory is only valid for a remote repository".format(location))
        return RepositoryConfig(path=_string(repository["path"], location + ".path"))
    url = _string(repository.get("url"), location + ".url")
    commit = _string(repository.get("commit"), location + ".commit")
    if not FULL_COMMIT.match(commit):
        raise RadBatError("{}.commit must be a full 40-character Git commit".format(location))
    subdirectory = repository.get("subdirectory")
    if subdirectory is not None:
        subdirectory = _string(subdirectory, location + ".subdirectory")
        subdirectory_path = Path(subdirectory)
        if subdirectory_path.is_absolute() or ".." in subdirectory_path.parts:
            raise RadBatError("{}.subdirectory must be a safe relative path".format(location))
    return RepositoryConfig(url=url, commit=commit.lower(), subdirectory=subdirectory)


def _validate_spack(value: Any) -> SpackConfig:
    spack = _object(value, "spack")
    _only_keys(spack, {"url", "commit", "environment", "repositories"}, "spack")
    url = _string(spack.get("url"), "spack.url")
    commit = _string(spack.get("commit"), "spack.commit")
    if not FULL_COMMIT.match(commit):
        raise RadBatError("spack.commit must be a full 40-character Git commit")
    environment = _string(spack.get("environment"), "spack.environment")
    repositories_value = spack.get("repositories", [])
    if not isinstance(repositories_value, list):
        raise RadBatError("spack.repositories must be a JSON array")
    repositories = [
        _validate_repository(repository, index)
        for index, repository in enumerate(repositories_value)
    ]
    return SpackConfig(url, commit.lower(), environment, repositories)


def load_project_config(source: Path) -> ProjectConfig:
    """Load the project configuration rooted at *source*."""

    root = source.expanduser().resolve()
    path = root / ".rad-bat.json"
    try:
        with path.open("r", encoding="utf-8") as stream:
            document = json.load(stream)
    except FileNotFoundError:
        raise RadBatError("project configuration not found: {}".format(path))
    except json.JSONDecodeError as error:
        raise RadBatError("invalid JSON in {}: {}".format(path, error))
    except OSError as error:
        raise RadBatError("cannot read {}: {}".format(path, error))

    document = _object(document, str(path))
    _only_keys(document, {"schema_version", "project", "spack"}, str(path))
    if document.get("schema_version") != 1:
        raise RadBatError("schema_version must be 1")

    project = _object(document.get("project"), "project")
    _only_keys(project, {"package", "command"}, "project")
    package = _string(project.get("package"), "project.package")
    command = _validate_command(project.get("command"))
    spack = _validate_spack(document["spack"]) if "spack" in document else None
    return ProjectConfig(root, package, command, spack)
