"""Shared console and GitLab collapsible-section logging."""

import datetime
import os
import re
import shlex
import time
from contextlib import contextmanager
from typing import Iterator, List, Tuple


START_ENV = "RAD_BAT_LOG_START_TIME"
DEPTH_ENV = "RAD_BAT_LOG_DEPTH"


def _elapsed(seconds: int) -> str:
    return "{:02d}:{:02d}:{:02d}".format(
        seconds // 3600, (seconds % 3600) // 60, seconds % 60
    )


def _timestamp(value: int) -> str:
    return datetime.datetime.utcfromtimestamp(value).strftime("%Y-%m-%d %H:%M:%S UTC")


def command(arguments: List[str]) -> None:
    """Print a command with shell-safe quoting for diagnostics."""

    print("+ {}".format(" ".join(shlex.quote(argument) for argument in arguments)), flush=True)


def info(message: str) -> None:
    print("[Information]: {}".format(message), flush=True)


def warning(message: str) -> None:
    print("\033[1;30m[Warning]: {}\033[0m".format(message), flush=True)


def error(message: str) -> None:
    print("\033[31m[Error]: {}\033[0m".format(message), flush=True)


class SectionManager:
    """Create nested sections that also nest across child processes."""

    def __init__(self) -> None:
        self.start = int(os.environ.get(START_ENV, str(int(time.time()))))
        self.base_depth = int(os.environ.get(DEPTH_ENV, "0"))
        self.counter = 0
        self.stack = []  # type: List[Tuple[str, int]]
        os.environ.setdefault(START_ENV, str(self.start))

    @contextmanager
    def section(
        self, name: str, title: str, collapsed: bool = True
    ) -> Iterator[None]:
        self.counter += 1
        started = int(time.time())
        safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", name)
        identifier = "{}_{}_{}".format(safe_name, os.getpid(), self.counter)
        depth = self.base_depth + len(self.stack)
        indent = "  " * depth
        print("\033[1;30m{}~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~\033[0m".format(indent))
        print("\033[1;30m{}~ TIME                    | TOTAL    | SECTION\033[0m".format(indent))
        print(
            "\033[1;30m{}~ {} | {} | {}\033[0m".format(
                indent, _timestamp(started), _elapsed(started - self.start), title
            )
        )
        print(
            "\033[0Ksection_start:{}:{}[collapsed={}]\r\033[0K{}~ {}".format(
                started, identifier, str(collapsed).lower(), indent, title
            ),
            flush=True,
        )
        previous_depth = os.environ.get(DEPTH_ENV)
        os.environ[DEPTH_ENV] = str(depth + 1)
        self.stack.append((identifier, started))
        try:
            yield
        finally:
            self.stack.pop()
            if previous_depth is None:
                os.environ.pop(DEPTH_ENV, None)
            else:
                os.environ[DEPTH_ENV] = previous_depth
            finished = int(time.time())
            print(
                "\033[0Ksection_end:{}:{}\r\033[0K\033[0m".format(
                    finished, identifier
                )
            )
            print(
                "\033[1;30m{}~ {} | {} | {}\033[0m".format(
                    indent,
                    _timestamp(finished),
                    _elapsed(finished - self.start),
                    _elapsed(finished - started),
                )
            )
            print("\033[1;30m{}~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~\033[0m".format(indent), flush=True)


sections = SectionManager()
