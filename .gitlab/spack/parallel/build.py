#!/usr/bin/env python3
"""Run native Spack installers inside one Jacamar-owned allocation.

The coordinator uses the standard library. Only prepare/snapshot execute via
``spack python`` and import Spack's pinned YAML and database APIs.
"""
# Copyright (c) 2026, Lawrence Livermore National Security, LLC and
# RADIUSS project contributors. SPDX-License-Identifier: (MIT)

import argparse
import contextlib
import grp
import json
import os
from pathlib import Path
import re
import selectors
import shlex
import shutil
import signal
import socket
import stat
import subprocess
import sys
import time
import traceback
import xml.etree.ElementTree as ET

SCRIPT = Path(__file__).resolve()
MACHINES = ("corona", "dane", "tioga", "tuolumne")
STOP_REQUESTED = False
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n")
    temporary.replace(path)


def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return default


def write_manifest(path, data, yaml):
    path = Path(path)
    temporary = path.with_suffix(".yaml.tmp")
    with temporary.open("w") as stream:
        yaml.dump_config(data, stream)
    temporary.replace(path)


def segment(value, name):
    if not value or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value) or value in (".", ".."):
        raise ValueError("{} must be a single safe path component".format(name))
    return value


def positive(name, default):
    value = int(os.environ.get(name, default))
    if value < 1:
        raise ValueError("{} must be positive".format(name))
    return value


def ensure_directory(path, group):
    path.mkdir(exist_ok=True)
    gid = grp.getgrnam(group).gr_gid
    if path.stat().st_gid != gid:
        os.chown(path, -1, gid)
    path.chmod(stat.S_IMODE(path.stat().st_mode) | stat.S_ISGID | 0o070)


def settings():
    project = Path(os.environ.get("CI_PROJECT_DIR", os.getcwd())).resolve()
    env_name = segment(os.environ["MY_ENV_NAME"], "MY_ENV_NAME")
    source = project / ".gitlab/spack/envs" / env_name
    if not (source / "spack.yaml").is_file():
        raise ValueError("No environment manifest at {}".format(source))
    nodes = positive("RSC_PARALLEL_NODES", "2")
    wall = positive("RSC_PARALLEL_TIME_MINUTES", "60")
    stop = positive("RSC_PARALLEL_STOP_MINUTES", "55")
    if wall - stop < 5:
        raise ValueError("Reserve at least five minutes between soft stop and allocation expiry")
    return {
        "project": project, "source": source, "environment": env_name,
        "nodes": nodes, "wall_minutes": wall, "stop_minutes": stop,
        "packages": positive("RSC_PARALLEL_PACKAGES", "2"),
    }


def check():
    settings()
    if os.environ.get("ON_CORONA") != "OFF" and not os.environ.get("RSC_CORONA_PARALLEL_ALLOC", "").strip():
        raise ValueError("Set ON_CORONA=OFF or supply RSC_CORONA_PARALLEL_ALLOC with confirmed CI queue parameters")
    print("Parallel backend configuration accepted; Jacamar owns each allocation.")


def paths(config):
    machine = segment(os.environ["RSC_MACHINE"], "RSC_MACHINE")
    if machine not in MACHINES:
        raise ValueError("Unsupported machine: {}".format(machine))
    root = Path(os.environ.get("RSC_PARALLEL_STORAGE_ROOT", "/usr/workspace/radiuss/rsc-ci-parallel-pilot"))
    if not root.is_absolute() or root == Path("/") or str(root).startswith("/dev/shm"):
        raise ValueError("RSC_PARALLEL_STORAGE_ROOT must be a persistent absolute filesystem path")
    store = root / config["environment"] / machine
    for name, default in (("SPACK_TARGET", None), ("CACHE_TARGET", "manual"), ("RSC_PARALLEL_CASE", "pilot")):
        store /= segment(os.environ.get(name, default), name)
    store /= "nodes-{}".format(config["nodes"])
    pipeline = store / "pipelines" / segment(os.environ["CI_PIPELINE_ID"], "CI_PIPELINE_ID")
    attempt = pipeline / "attempts" / segment(os.environ["CI_JOB_ID"], "CI_JOB_ID")
    return {"machine": machine, "store": store, "pipeline": pipeline,
            "attempt": attempt, "environment": pipeline / "environment",
            "spack": pipeline / "spack", "temporary": root / "tmp" / os.environ["CI_JOB_ID"],
            "results": config["project"] / "parallel-results" / machine}


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


def command(argv, log, deadline, env=None, honor_stop=True, on_interrupt=None):
    """Tee output without a blocking read; all subprocesses have bounded lifetimes."""
    if time.monotonic() >= deadline or (honor_stop and STOP_REQUESTED):
        raise TimeoutError("No remaining time for {}".format(argv[0]))
    Path(log).parent.mkdir(parents=True, exist_ok=True)
    print("$ {}".format(shlex.join(map(str, argv))), flush=True)
    interrupted = False
    with open(log, "ab", buffering=0) as output:
        process = subprocess.Popen(list(map(str, argv)), stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, env=env, start_new_session=True)
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


def launch_command(scheduler, nodes, script=SCRIPT):
    worker = [sys.executable, str(script), "worker"]
    if scheduler == "flux":
        if not os.environ.get("FLUX_URI"):
            raise ValueError("Flux workers require Jacamar's active Flux allocation")
        # Exclusive nodes belong to this job; disabling per-task affinity lets a
        # single installer use every CPU permitted by the allocation's cpuset.
        return ["flux", "run", "--nodes={}".format(nodes), "--ntasks={}".format(nodes),
                "--exclusive", "--label-io", "-o", "cpu-affinity=off"] + worker
    if scheduler == "slurm":
        if not os.environ.get("SLURM_JOB_ID"):
            raise ValueError("Slurm workers require Jacamar's active Slurm allocation")
        counts = os.environ.get("SLURM_JOB_CPUS_PER_NODE", "")
        parts = counts.split(",")
        if not all(re.fullmatch(r"\d+(?:\(x\d+\))?", part) for part in parts):
            raise ValueError("Cannot determine allocated CPUs from SLURM_JOB_CPUS_PER_NODE")
        cpus = min(int(part.split("(")[0]) for part in parts)
        return ["srun", "--nodes={}".format(nodes), "--ntasks={}".format(nodes),
                "--ntasks-per-node=1", "--cpus-per-task={}".format(cpus),
                "--cpu-bind=cores", "--kill-on-bad-exit=0", "--export=ALL"] + worker
    raise ValueError("Unsupported scheduler: {}".format(scheduler))


def stop_flux(jobid):
    # Killing an attach process can merely detach it. Signal the allocation's
    # worker job explicitly and wait for its clean event before taking a snapshot.
    for sig, grace in (("SIGINT", 30), ("SIGTERM", 10)):
        subprocess.run(["flux", "job", "kill", "--signal=" + sig, jobid], timeout=10, check=False)
        try:
            subprocess.run(["flux", "job", "attach", "--wait-event=clean", jobid],
                           stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=grace, check=False)
            return
        except subprocess.TimeoutExpired:
            pass
    subprocess.run(["flux", "cancel", jobid], timeout=10, check=False)
    subprocess.run(["flux", "job", "attach", "--wait-event=clean", jobid],
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=10, check=False)


def launch_workers(launcher, attempt, deadline):
    if launcher[0] != "flux":
        return command(launcher, attempt / "workers.log", deadline)
    submit = ["flux", "submit"] + [arg for arg in launcher[2:] if arg != "--label-io"]
    submission_log = attempt / "submit.log"
    command(submit, submission_log, deadline)
    jobid = submission_log.read_text().strip().splitlines()[-1]
    if not re.fullmatch(r"(?:[fƒ][1-9A-HJ-NP-Za-km-z]+|[0-9]+)", jobid):
        raise ValueError("Flux submission returned an invalid job id: {}".format(jobid))
    write_json(attempt / "worker-job.json", {"scheduler": "flux", "jobid": jobid})
    return command(["flux", "job", "attach", "--label-io", "--wait-event=clean", jobid],
                   attempt / "workers.log", deadline, on_interrupt=lambda: stop_flux(jobid))


def prepare(args):
    """Configure the copied manifest before any installer starts."""
    import spack.util.spack_yaml as sy

    env_path = Path(args.environment)
    manifest = env_path / "spack.yaml"
    with manifest.open() as stream:
        data = sy.load_config(stream)
    config = data["spack"]

    def override(mapping, name, value):
        mapping.pop(name, None)
        key = sy.syaml_str(name)
        key.override = True
        mapping[key] = value

    # Generation-only configuration is irrelevant to this backend. All other
    # includes were copied with symlinks dereferenced from the selected env.
    config["include"] = [item for item in config.get("include", []) if item != "ci.yaml"]
    config.pop("ci", None)
    config["view"] = False
    store = Path(args.store)
    override(config, "upstreams", {})
    override(config, "mirrors", {"parallel-pilot": {
        "url": (store / "buildcache").as_uri(), "binary": True,
        "source": False, "signed": False, "autopush": True,
    }})
    # Override defaults too: worker user caches must not fetch a second builtin
    # repository or accidentally resolve a moving default package branch.
    override(config, "repos", config.get("repos", {}))
    if not config["repos"]:
        raise ValueError("The environment must supply a pinned package repository")
    for name, descriptor in config["repos"].items():
        if isinstance(descriptor, dict) and "git" in descriptor and not descriptor.get("commit"):
            raise ValueError("Repository {} must be pinned by commit".format(name))
    cfg = config.setdefault("config", {})
    cfg.setdefault("install_tree", {})["root"] = str(store / "install")
    # Cache/stage locations follow each worker's filesystem user cache.
    override(cfg, "build_stage", ["$user_cache_path/stage"])
    cfg["test_stage"] = "$user_cache_path/test"
    cfg["misc_cache"] = "$user_cache_path/misc"
    cfg["source_cache"] = str(store / "sources")
    override(config, "bootstrap", {"root": str(store / "bootstrap")})
    cfg["build_jobs"] = args.cpus
    all_packages = config.setdefault("packages", {}).setdefault("all", {})
    all_packages["permissions"] = {"read": "world", "write": "group", "group": args.group}
    write_manifest(manifest, data, sy)


def freeze():
    """Replace git descriptors with shared, already-resolved repository paths."""
    import spack.environment as ev
    import spack.repo
    import spack.util.spack_yaml as sy

    environment = ev.active_environment()
    repositories = {repo.namespace: repo.root for repo in spack.repo.PATH.repos}
    if not repositories:
        raise ValueError("No package repositories resolved")
    manifest = Path(environment.path) / "spack.yaml"
    with manifest.open() as stream:
        data = sy.load_config(stream)
    data["spack"].pop("repos")
    key = sy.syaml_str("repos")
    key.override = True
    data["spack"][key] = repositories
    write_manifest(manifest, data, sy)


def snapshot(args):
    import spack.deptypes as dt
    import spack.environment as ev
    import spack.store

    environment = ev.active_environment()
    if environment is None:
        raise ValueError("snapshot requires an active concrete environment")
    if sorted(str(s) for s in environment.user_specs) != sorted(str(s) for s, _ in environment.concretized_specs()):
        raise ValueError("The concrete lock does not match the selected environment's root specs")
    nodes = {}
    with spack.store.STORE.db.read_transaction():
        for spec in environment.all_specs():
            nodes[spec.dag_hash()] = {
                "name": spec.name, "version": str(spec.version), "spec": str(spec),
                "compiler": str(getattr(spec, "compiler", "")),
                "external": bool(spec.external), "installed": bool(spec.installed),
                "prefix": str(spec.prefix),
                "dependencies": [{"hash": edge.spec.dag_hash(), "types": list(dt.flag_to_tuple(edge.depflag))}
                                 for edge in spec.edges_to_dependencies()],
            }
    write_json(args.out, {"roots": [s.dag_hash() for s in environment.concrete_roots()], "nodes": nodes})


def worker():
    attempt = Path(os.environ["RSC_ATTEMPT_ROOT"])
    rank = os.environ.get("FLUX_TASK_RANK", os.environ.get("SLURM_PROCID"))
    if rank is None:
        raise ValueError("worker must be launched as an allocation task")
    rank = segment(rank, "worker rank")
    directory = attempt / "workers" / rank
    directory.mkdir(parents=True, exist_ok=True)
    cpus = len(os.sched_getaffinity(0))
    if os.environ.get("RSC_SCHEDULER") == "slurm" and os.environ.get("SLURM_CPUS_PER_TASK"):
        cpus = min(cpus, positive("SLURM_CPUS_PER_TASK", "1"))
    override = os.environ.get("RSC_PARALLEL_JOBS")
    if override:
        cpus = min(cpus, positive("RSC_PARALLEL_JOBS", override))
    state = {"rank": rank, "host": socket.gethostname(), "cpus": cpus,
             "started": time.time(), "returncode": None, "interrupted": False}
    write_json(directory / "status.json", state)
    env = os.environ.copy()
    env["SPACK_USER_CACHE_PATH"] = str(directory / "cache")
    env["TMPDIR"] = str(Path(env.get("RSC_TMP_ROOT", directory)) / rank)
    Path(env["TMPDIR"]).mkdir(exist_ok=True)
    # POSIX jobserver descriptors cannot be inherited across allocation nodes.
    env.pop("MAKEFLAGS", None)
    deadline = time.monotonic() + max(0, float(env["RSC_STOP_EPOCH"]) - time.time())
    argv = [env["RSC_SPACK"], "-e", env["RSC_CONCRETE_ENV"], "install", "--only-concrete",
            "-j{}".format(cpus), "-p{}".format(env["RSC_PARALLEL_PACKAGES"]),
            "--log-format", "junit", "--log-file", str(directory / "native.xml")]
    try:
        command(argv, directory / "install.log", deadline, env)
        state["returncode"] = 0
    except TimeoutError:
        state.update(returncode=124, interrupted=True)
    except subprocess.CalledProcessError as error:
        state["returncode"] = error.returncode
    except Exception as error:
        state.update(returncode=1, error=str(error))
        traceback.print_exc()
    finally:
        state["finished"] = time.time()
        write_json(directory / "status.json", state)
    return state["returncode"]


def reconcile(spack, environment, snapshot_path, attempt, phase, deadline):
    state = load_json(snapshot_path, {"nodes": {}})
    installed = ["/" + h for h, node in state["nodes"].items() if node["installed"] and not node["external"]]
    for offset in range(0, len(installed), 64):
        command([spack, "-e", environment, "buildcache", "push", "--unsigned", "--only", "package",
                 "parallel-pilot"] + installed[offset:offset + 64],
                attempt / ("cache-{}.log".format(phase)), deadline, honor_stop=phase == "before")
    if installed:
        command([spack, "-e", environment, "buildcache", "update-index", "parallel-pilot"],
                attempt / ("cache-{}.log".format(phase)), deadline, honor_stop=phase == "before")


def run():
    started = time.monotonic()
    started_epoch = time.time()
    config = settings()
    p = paths(config)
    os.umask(0o002)
    storage_root = Path(os.environ.get("RSC_PARALLEL_STORAGE_ROOT", "/usr/workspace/radiuss/rsc-ci-parallel-pilot"))
    storage_root.parent.mkdir(parents=True, exist_ok=True)
    group = os.environ.get("SPACK_CI_STORAGE_GROUP", "radiuss")
    for path in [storage_root] + [storage_root / Path(*p["attempt"].relative_to(storage_root).parts[:i])
                                 for i in range(1, len(p["attempt"].relative_to(storage_root).parts) + 1)]:
        ensure_directory(path, group)
    for name in ("install", "buildcache", "sources", "bootstrap"):
        ensure_directory(p["store"] / name, group)
    ensure_directory(storage_root / "tmp", group)
    ensure_directory(p["temporary"], group)
    state = {"machine": p["machine"], "nodes": config["nodes"], "started": started_epoch,
             "repository_commit": os.environ.get("CI_COMMIT_SHA"),
             "case": os.environ.get("RSC_PARALLEL_CASE", "pilot"), "target": os.environ["SPACK_TARGET"],
             "errors": [], "interrupted": False, "complete": False}
    status_path = p["attempt"] / "status.json"
    write_json(status_path, state)
    stop = started + 60 * config["stop_minutes"]
    finish = started + 60 * config["wall_minutes"] - 30
    os.environ.update({"SPACK_DISABLE_LOCAL_CONFIG": "true",
                       "SPACK_USER_CACHE_PATH": str(p["pipeline"] / "cache"),
                       "MY_SPACK_PARENT_DIR": str(p["pipeline"]),
                       "RSC_ATTEMPT_ROOT": str(p["attempt"]),
                       "RSC_CONCRETE_ENV": str(p["environment"]), "RSC_SPACK": str(p["spack"] / "bin/spack"),
                       "RSC_STOP_EPOCH": str(started_epoch + 60 * config["stop_minutes"]),
                       "RSC_PARALLEL_PACKAGES": str(config["packages"]),
                       # Keep multiprocessing Unix-socket names below AF_UNIX's
                       # path limit while still using the shared filesystem.
                       "RSC_TMP_ROOT": str(p["temporary"]),
                       "TMPDIR": str(p["temporary"] / "coordinator")})
    Path(os.environ["TMPDIR"]).mkdir(exist_ok=True)
    spack = p["spack"] / "bin/spack"
    try:
        if os.environ.get("LCSCHEDCLUSTER", p["machine"]) != p["machine"]:
            raise ValueError("Runner machine does not match RSC_MACHINE")
        os.environ["LCSCHEDCLUSTER"] = p["machine"]
        launcher = launch_command(os.environ["RSC_SCHEDULER"], config["nodes"])
        # Prevent two pipelines from racing over the same install/cache namespace.
        # GitLab resource_group provides the scheduling-side serialization.
        command([config["project"] / ".gitlab/scripts/get-spack"], p["attempt"] / "bootstrap.log", stop)
        state["spack_commit"] = subprocess.check_output(["git", "-C", p["spack"], "rev-parse", "HEAD"], text=True).strip()
        if not p["environment"].exists():
            if (config["source"] / "spack.lock").exists() and not os.environ.get("RSC_PARALLEL_LOCKFILE"):
                raise ValueError("Use RSC_PARALLEL_LOCKFILE explicitly rather than an inherited source lock")
            staging_env = p["pipeline"] / ("preparing-" + os.environ["CI_JOB_ID"])
            shutil.copytree(config["source"], staging_env, symlinks=False, ignore=shutil.ignore_patterns("spack.lock", ".spack-env"))
            # Disable default repositories during manifest preparation; this
            # command only needs YAML and must not fetch an unpinned default repo.
            bootstrap_config = p["pipeline"] / "prepare-config"
            bootstrap_config.mkdir(exist_ok=True)
            (bootstrap_config / "repos.yaml").write_text("repos:: {}\n")
            command([spack, "-C", bootstrap_config, "python", SCRIPT, "prepare", "--environment", staging_env,
                     "--store", p["store"], "--group", group,
                     "--cpus", "1"], p["attempt"] / "configure.log", stop)
            if os.environ.get("RSC_PARALLEL_LOCKFILE"):
                shutil.copyfile(os.environ["RSC_PARALLEL_LOCKFILE"], staging_env / "spack.lock")
            staging_env.rename(p["environment"])
        concrete_marker = p["pipeline"] / "concrete-ready.json"
        if not concrete_marker.exists():
            if not os.environ.get("RSC_PARALLEL_LOCKFILE"):
                command([spack, "-e", p["environment"], "concretize", "--fresh"], p["attempt"] / "concretize.log", stop)
            command([spack, "-e", p["environment"], "python", SCRIPT, "freeze"], p["attempt"] / "configure.log", stop)
        command([spack, "-e", p["environment"], "python", SCRIPT, "snapshot", "--out", p["attempt"] / "before.json"],
                p["attempt"] / "snapshot.log", stop)
        before = load_json(p["attempt"] / "before.json")
        if not before["roots"]:
            raise ValueError("The selected environment has no concrete roots on this machine")
        write_json(concrete_marker, {"spack_commit": state["spack_commit"]})
        reconcile(spack, p["environment"], p["attempt"] / "before.json", p["attempt"], "before", stop)
        launch_workers(launcher, p["attempt"], stop)
    except TimeoutError as error:
        state["interrupted"] = True
        state["errors"].append(str(error))
    except Exception as error:
        state["errors"].append(str(error))
        traceback.print_exc()
    finally:
        write_json(status_path, state)
        if (p["attempt"] / "before.json").exists():
            try:
                command([spack, "-e", p["environment"], "python", SCRIPT, "snapshot", "--out", p["attempt"] / "after.json"],
                        p["attempt"] / "snapshot.log", finish, honor_stop=False)
                reconcile(spack, p["environment"], p["attempt"] / "after.json", p["attempt"], "after", finish)
            except Exception as error:
                state["errors"].append("Final snapshot/cache publication: {}".format(error))
        state.update(complete=True, finished=time.time(), elapsed_seconds=time.monotonic() - started)
        write_json(status_path, state)
        return collect(config, p)


def native_outcomes(directory, hashes):
    """Read native JUnit, with status-line fallback when interruption truncates it."""
    outcomes = {}
    short_hashes = {}
    for h in hashes:
        short_hashes.setdefault(h[:7], []).append(h)
    diagnostics = []
    for worker_dir in sorted(directory.glob("workers/*")):
        native = worker_dir / "native.xml"
        if native.exists():
            try:
                for case in ET.parse(native).iter("testcase"):
                    h = case.get("name")
                    if h not in hashes:
                        continue
                    error = case.find("failure")
                    if error is None:
                        error = case.find("error")
                    if error is not None:
                        outcomes[h] = {"state": "failed", "message": error.get("message", error.text or "Installation failed")}
            except ET.ParseError as error:
                diagnostics.append("Incomplete native report {}: {}".format(native, error))
        log = worker_dir / "install.log"
        if log.exists():
            for match in re.finditer(r"\[x\]\s+([a-z0-9]{7})\s+[^\n]*", ANSI.sub("", log.read_text(errors="replace"))):
                candidates = short_hashes.get(match[1], [])
                if len(candidates) == 1:
                    record = outcomes.setdefault(candidates[0], {"state": "failed", "message": match[0]})
                    log_path = re.search(r"failed:\s+(\S+)", match[0])
                    if log_path:
                        record["log_path"] = log_path[1]
    return outcomes, diagnostics


def classify(before, after, failures, interrupted):
    nodes = after["nodes"]
    required = set()

    def require(h):
        if h in required:
            return
        required.add(h)
        node = nodes[h]
        if node["external"]:
            return
        for edge in node["dependencies"]:
            types = {"link", "run"} if node["installed"] else {"build", "link", "run"}
            if types.intersection(edge["types"]):
                require(edge["hash"])

    for root in after["roots"]:
        require(root)
    states = {}

    def outcome(h):
        if h in states:
            return states[h]
        node = nodes[h]
        message = ""
        if node["external"]:
            state = "external"
        elif node["installed"]:
            state = "reused" if before["nodes"].get(h, {}).get("installed") else "success"
        elif h in failures:
            state, message = "failed", failures[h]["message"]
        elif h not in required:
            state = "not-needed"
        else:
            blockers = [edge["hash"] for edge in node["dependencies"] if edge["hash"] in required
                        and outcome(edge["hash"])["state"] in ("failed", "blocked")]
            state = "blocked" if blockers else "interrupted" if interrupted else "failed"
            message = "Dependency failed" if blockers else "Allocation interrupted" if interrupted else "Required installation missing"
        states[h] = dict(node, state=state, message=message)
        return states[h]

    for h in nodes:
        outcome(h)
    return states


def dependency_tree(roots, nodes):
    lines, seen = [], set()

    def visit(h, prefix="", connector=""):
        node = nodes[h]
        repeated = h in seen
        compiler = " %" + node["compiler"] if node.get("compiler") else ""
        lines.append("{}{}[{}] {}@{}{} /{}{}".format(prefix, connector, node["state"], node["name"],
                     node["version"], compiler, h[:7], " (shown above)" if repeated else ""))
        if repeated:
            return
        seen.add(h)
        children = sorted(node["dependencies"], key=lambda e: (nodes[e["hash"]]["name"], e["hash"]))
        continuation = prefix + ("    " if connector == "`-- " else "|   " if connector else "")
        for index, edge in enumerate(children):
            visit(edge["hash"], continuation, "`-- " if index == len(children) - 1 else "|-- ")

    for root in roots:
        visit(root)
    return "\n".join(lines) + "\n"


def junit(nodes, errors, duration):
    suite = ET.Element("testsuite", name="parallel-environment", time=str(duration))
    for h, node in sorted(nodes.items()):
        case = ET.SubElement(suite, "testcase", name="{}@{}/{}".format(node["name"], node["version"], h), classname="spack")
        if node["state"] in ("failed", "blocked", "interrupted"):
            ET.SubElement(case, "failure", message=node["message"]).text = node["spec"]
        elif node["state"] in ("external", "reused", "not-needed"):
            ET.SubElement(case, "skipped", message=node["state"])
    for index, error in enumerate(errors):
        case = ET.SubElement(suite, "testcase", name="infrastructure-{}".format(index), classname="parallel-backend")
        ET.SubElement(case, "failure", message=str(error))
    cases = suite.findall("testcase")
    suite.set("tests", str(len(cases)))
    suite.set("failures", str(sum(case.find("failure") is not None for case in cases)))
    suite.set("skipped", str(sum(case.find("skipped") is not None for case in cases)))
    return ET.ElementTree(suite)


def collect(config=None, p=None):
    config = config or settings()
    p = p or paths(config)
    directory = p["attempt"]
    state = load_json(directory / "status.json", {"complete": False, "errors": []})
    errors = list(state["errors"])
    interrupted = bool(state.get("interrupted") or not state.get("complete"))
    if not state.get("complete"):
        errors.append("Build script did not finalize; allocation or job interrupted")
    before = load_json(directory / "before.json", {"roots": [], "nodes": {}})
    if not state.get("complete") and before["nodes"] and (p["spack"] / "bin/spack").is_file():
        try:
            env = os.environ.copy()
            env.update(SPACK_DISABLE_LOCAL_CONFIG="true", LCSCHEDCLUSTER=p["machine"],
                       SPACK_USER_CACHE_PATH=str(p["pipeline"] / "cache"), TMPDIR=str(p["temporary"] / "coordinator"))
            command([p["spack"] / "bin/spack", "-e", p["environment"], "python", SCRIPT,
                     "snapshot", "--out", directory / "after.json"],
                    directory / "recovery.log", time.monotonic() + 45, env, honor_stop=False)
        except Exception as error:
            errors.append("Recovery snapshot: {}".format(error))
    after = load_json(directory / "after.json", before)
    if not (directory / "after.json").exists() and before["nodes"]:
        interrupted = True
        errors.append("Final installation snapshot unavailable; results may omit completed packages")
    failures, diagnostics = native_outcomes(directory, after["nodes"])
    workers = [load_json(path) for path in sorted(directory.glob("workers/*/status.json"))]
    if len(workers) != config["nodes"]:
        errors.append("Expected {} workers, found {}".format(config["nodes"], len(workers)))
    if len({worker["host"] for worker in workers}) != len(workers):
        errors.append("Multiple workers ran on the same node")
    for worker_state in workers:
        if worker_state["returncode"] != 0:
            errors.append("Worker {} on {} exited with {}".format(worker_state["rank"], worker_state["host"], worker_state["returncode"]))
            interrupted |= bool(worker_state.get("interrupted") or worker_state["returncode"] is None)
    nodes = classify(before, after, failures, interrupted)
    tree = dependency_tree(after["roots"], nodes)
    results = p["results"]
    results.mkdir(parents=True, exist_ok=True)
    # Preserve native diagnostics without copying large staging or user caches.
    for filename in directory.glob("*.log"):
        shutil.copyfile(filename, results / filename.name)
    for filename in directory.glob("workers/*/*"):
        if filename.is_file() and filename.suffix in (".log", ".xml", ".json"):
            destination = results / "workers" / filename.parent.name / filename.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(filename, destination)
    for h, node in nodes.items():
        # Successful source builds retain their logs under the install prefix.
        # Failed build logs remain in the isolated worker stages on the filesystem.
        logs = list((Path(node["prefix"]) / ".spack").glob("spack-build-*"))
        log_path = failures.get(h, {}).get("log_path")
        if log_path:
            logs.append(Path(log_path))
        for log in logs:
            if log.is_file():
                destination = results / "build-logs" / h / log.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(log, destination)
    if p["environment"].exists():
        shutil.copytree(p["environment"], results / "environment", dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns(".spack-env"))
    counts = {s: sum(n["state"] == s for n in nodes.values()) for s in
              ("success", "reused", "external", "failed", "blocked", "interrupted", "not-needed")}
    duration = state.get("elapsed_seconds", max(0, time.time() - state.get("started", time.time())))
    write_json(results / "results.json", {"roots": after["roots"], "nodes": nodes, "counts": counts,
               "workers": workers, "run": state, "errors": errors, "diagnostics": diagnostics,
               "elapsed_seconds": duration, "node_hours": config["nodes"] * duration / 3600})
    (results / "tree.txt").write_text(tree)
    junit(nodes, errors, duration).write(results / "junit.xml", encoding="utf-8", xml_declaration=True)
    print(tree, end="")
    print("Results: {}".format(json.dumps(counts, sort_keys=True)))
    for error in errors:
        print("[Error] {}".format(error), file=sys.stderr)
    return int(bool(errors or any(counts[s] for s in ("failed", "blocked", "interrupted"))))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "run", "worker", "collect", "freeze"):
        commands.add_parser(name)
    preparation = commands.add_parser("prepare")
    for name in ("environment", "store", "group"):
        preparation.add_argument("--" + name, required=True)
    preparation.add_argument("--cpus", type=int, required=True)
    snap = commands.add_parser("snapshot")
    snap.add_argument("--out", required=True)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    try:
        if args.command == "prepare":
            prepare(args)
        elif args.command == "snapshot":
            snapshot(args)
        else:
            return globals()[args.command]() or 0
        return 0
    except Exception as error:
        print("[Error] {}".format(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
