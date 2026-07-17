#! /usr/bin/env python3
##############################################################################
# Copyright (c) 2019-2026, Lawrence Livermore National Security, LLC and
# RADIUSS project contributors. See the COPYRIGHT file for details.
#
# SPDX-License-Identifier: (MIT)
##############################################################################

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path


def require_env(var_name: str) -> str:
    value = os.environ.get(var_name)
    if not value:
        print(f"[Error] {var_name} must be set", file=sys.stderr)
        sys.exit(1)
    return value


def slugify_ref_name(ref_name: str) -> str:
    slug = re.sub(r"[^0-9a-z]+", "-", ref_name.lower()).strip("-")
    return slug[:63].rstrip("-")


def fetch_merged_mr_data(
    api_base_url: str, project_id: str, job_token: str, default_branch: str
) -> tuple[set[str], set[str]]:
    merged_mr_dirs: set[str] = set()
    source_branches: set[str] = set()
    page = 1

    while True:
        params = urllib.parse.urlencode(
            {
                "state": "merged",
                "target_branch": default_branch,
                "per_page": 100,
                "page": page,
            }
        )
        request = urllib.request.Request(
            f"{api_base_url}/projects/{project_id}/merge_requests?{params}",
            headers={"JOB-TOKEN": job_token},
        )

        with urllib.request.urlopen(request) as response:
            payload = json.load(response)

        if not payload:
            break

        for item in payload:
            iid = item.get("iid")
            if iid is not None:
                merged_mr_dirs.add(f"mr-{iid}")

            source_branch = item.get("source_branch")
            if source_branch:
                source_branches.add(source_branch)

        if len(payload) < 100:
            break

        page += 1

    return merged_mr_dirs, source_branches


def list_merged_remote_branches(default_branch: str) -> set[str]:
    subprocess.run(
        ["git", "--no-pager", "fetch", "--prune", "origin", "+refs/heads/*:refs/remotes/origin/*"],
        check=True,
    )
    output = subprocess.run(
        [
            "git",
            "--no-pager",
            "for-each-ref",
            f"--merged=refs/remotes/origin/{default_branch}",
            "--format=%(refname:short)",
            "refs/remotes/origin",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    merged_branches: set[str] = set()
    for line in output.splitlines():
        if not line.startswith("origin/"):
            continue
        branch_name = line.removeprefix("origin/")
        if branch_name in {"HEAD", default_branch}:
            continue
        merged_branches.add(branch_name)

    return merged_branches


def find_candidate_targets(storage_root: Path) -> list[Path]:
    candidates: list[Path] = []
    for pattern in ("*/*/*/mr-*", "*/*/*/ref-*"):
        for path in storage_root.glob(pattern):
            if path.is_dir() and not path.is_symlink():
                candidates.append(path)
    return sorted(candidates)


def main() -> int:
    api_base_url = require_env("CI_API_V4_URL")
    project_id = require_env("CI_PROJECT_ID")
    job_token = require_env("CI_JOB_TOKEN")
    default_branch = require_env("CI_DEFAULT_BRANCH")

    storage_root = Path(os.environ.get("SPACK_CI_STORAGE_ROOT", "/usr/workspace/radiuss/rsc-ci"))
    if not storage_root.is_dir():
        print(f"[Information] No persistent storage root found at {storage_root}; nothing to clean.")
        return 0

    print(f"[Information] Looking up merged merge requests targeting {default_branch}.")
    merged_mr_dirs, merged_mr_source_branches = fetch_merged_mr_data(
        api_base_url=api_base_url,
        project_id=project_id,
        job_token=job_token,
        default_branch=default_branch,
    )

    print(f"[Information] Looking up remote branches already merged into {default_branch}.")
    merged_branch_names = list_merged_remote_branches(default_branch)
    merged_branch_names.update(merged_mr_source_branches)

    merged_ref_dirs = {
        f"ref-{slug}"
        for slug in (slugify_ref_name(ref_name) for ref_name in merged_branch_names)
        if slug
    }

    candidates = find_candidate_targets(storage_root)
    if not candidates:
        print(f"[Information] No mr-* or ref-* storage targets found under {storage_root}.")
        return 0

    resolved_storage_root = storage_root.resolve()
    removed_count = 0
    for cache_target_dir in candidates:
        cache_target_name = cache_target_dir.name
        remove_dir = (
            cache_target_name.startswith("mr-")
            and cache_target_name in merged_mr_dirs
        ) or (
            cache_target_name.startswith("ref-")
            and cache_target_name in merged_ref_dirs
        )
        if not remove_dir:
            continue

        resolved_target_dir = cache_target_dir.resolve()
        try:
            resolved_target_dir.relative_to(resolved_storage_root)
        except ValueError:
            print(
                f"[Error] Refusing to remove unexpected path: {cache_target_dir}",
                file=sys.stderr,
            )
            return 1

        print(f"[Information] Removing stale cache target: {cache_target_dir}")
        shutil.rmtree(cache_target_dir)
        removed_count += 1

    noun = "directory" if removed_count == 1 else "directories"
    print(f"[Information] Removed {removed_count} stale cache target {noun}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
