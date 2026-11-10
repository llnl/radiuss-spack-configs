"""Launch and await workers inside an existing allocation. Never allocate nodes."""

import json
import os
import re
import subprocess

from .execution import command


def launch_command(scheduler, nodes, worker):
    if scheduler == "local":
        if nodes != 1:
            raise ValueError("Multiple nodes require a Slurm or Flux allocation")
        return worker
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
    (attempt / "worker-job.json").write_text(json.dumps({"scheduler": "flux", "jobid": jobid}))
    stopped = False

    def cleanup():
        nonlocal stopped
        if not stopped:
            stopped = True
            stop_flux(jobid)

    try:
        return command(["flux", "job", "attach", "--label-io", "--wait-event=clean", jobid],
                       attempt / "workers.log", deadline, on_interrupt=cleanup)
    except BaseException:
        cleanup()
        raise
