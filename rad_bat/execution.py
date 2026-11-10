"""Bounded subprocess execution for allocation-owned environment builds."""

import contextlib
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time

from . import logs
from .runner import scheduler_pass_fds

STOP_REQUESTED = False


def request_stop(signum, frame):
    global STOP_REQUESTED
    STOP_REQUESTED = True


def terminate(process):
    # SIGINT lets Spack stop its own build process groups and release prefix locks.
    for sig, grace in ((signal.SIGINT, 30), (signal.SIGTERM, 10), (signal.SIGKILL, 5)):
        if process.poll() is not None:
            return
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, sig)
        try:
            process.wait(timeout=grace)
            return
        except subprocess.TimeoutExpired:
            pass
    raise RuntimeError("Worker launcher did not terminate")


def command(argv, log, deadline, env=None, honor_stop=True, on_interrupt=None, cwd=None):
    """Tee output without a blocking read; all subprocesses have bounded lifetimes."""
    if time.monotonic() >= deadline or (honor_stop and STOP_REQUESTED):
        raise TimeoutError("No remaining time for {}".format(argv[0]))
    Path(log).parent.mkdir(parents=True, exist_ok=True)
    logs.command(list(map(str, argv)))
    interrupted = False
    with open(log, "ab", buffering=0) as output:
        process = subprocess.Popen(list(map(str, argv)), stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, env=env, cwd=cwd, start_new_session=True,
                                   pass_fds=scheduler_pass_fds(env))
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while selector.get_map():
                    if time.monotonic() >= deadline or (honor_stop and STOP_REQUESTED):
                        interrupted = True
                        if on_interrupt:
                            on_interrupt()
                            on_interrupt = None
                        terminate(process)
                    for key, _ in selector.select(timeout=0.5):
                        data = os.read(key.fileobj.fileno(), 65536)
                        if data:
                            output.write(data)
                            sys.stdout.write(data.decode("utf-8", errors="replace"))
                            sys.stdout.flush()
                        else:
                            selector.unregister(key.fileobj)
                    # A launcher can exit while a descendant retains its stdout.
                    if interrupted and process.poll() is not None:
                        break
            code = process.wait(timeout=max(1, deadline - time.monotonic()))
        finally:
            terminate(process)
            process.stdout.close()
    if interrupted:
        raise TimeoutError("Interrupted {}".format(argv[0]))
    if code:
        raise subprocess.CalledProcessError(code, argv)
