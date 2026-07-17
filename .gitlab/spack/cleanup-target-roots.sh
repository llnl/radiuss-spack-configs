#! /bin/bash
##############################################################################
# Copyright (c) 2019-2026, Lawrence Livermore National Security, LLC and
# RADIUSS project contributors. See the COPYRIGHT file for details.
#
# SPDX-License-Identifier: (MIT)
##############################################################################

set -euo pipefail

slugify_ref_name() {
  python3 - "$1" <<'PY'
import re
import sys

ref = sys.argv[1].lower()
slug = re.sub(r"[^0-9a-z]+", "-", ref).strip("-")
slug = slug[:63].rstrip("-")
print(slug)
PY
}

require_var() {
  local var_name="$1"
  if [[ -z "${!var_name:-}" ]]
  then
    echo "[Error] ${var_name} must be set" >&2
    exit 1
  fi
}

require_var MY_ENV_NAME
require_var CI_API_V4_URL
require_var CI_PROJECT_ID
require_var CI_JOB_TOKEN
require_var CI_DEFAULT_BRANCH

: "${SPACK_CI_STORAGE_ROOT:=/usr/workspace/radiuss/rsc-ci}"
export SPACK_CI_STORAGE_ROOT

env_storage_root="${SPACK_CI_STORAGE_ROOT}/${MY_ENV_NAME}"
if [[ ! -d "${env_storage_root}" ]]
then
  echo "[Information] No persistent storage root found at ${env_storage_root}; nothing to clean."
  exit 0
fi

tmp_root="$(mktemp -d)"
trap 'rm -rf "${tmp_root}"' EXIT

merged_mr_dirs="${tmp_root}/merged-mr-dirs.txt"
merged_ref_dirs="${tmp_root}/merged-ref-dirs.txt"
merged_mr_source_branches="${tmp_root}/merged-mr-source-branches.txt"
merged_branch_names="${tmp_root}/merged-branch-names.txt"
candidates="${tmp_root}/candidates.txt"

touch "${merged_mr_dirs}" "${merged_ref_dirs}" "${merged_mr_source_branches}" "${merged_branch_names}" "${candidates}"

echo "[Information] Looking up merged merge requests targeting ${CI_DEFAULT_BRANCH}."
page=1
while true
do
  response_file="${tmp_root}/mrs-page-${page}.json"
  curl --silent --show-error --fail \
    -H "JOB-TOKEN: ${CI_JOB_TOKEN}" \
    --get "${CI_API_V4_URL}/projects/${CI_PROJECT_ID}/merge_requests" \
    --data-urlencode "state=merged" \
    --data-urlencode "target_branch=${CI_DEFAULT_BRANCH}" \
    --data-urlencode "per_page=100" \
    --data-urlencode "page=${page}" \
    > "${response_file}"

  item_count="$(
    python3 - "${response_file}" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as f:
    payload = json.load(f)
print(len(payload))
PY
  )"

  if [[ "${item_count}" == "0" ]]
  then
    break
  fi

  python3 - "${response_file}" "${merged_mr_dirs}" "${merged_mr_source_branches}" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as f:
    payload = json.load(f)

with open(sys.argv[2], "a", encoding="utf-8") as mr_out, open(sys.argv[3], "a", encoding="utf-8") as branch_out:
    for item in payload:
        iid = item.get("iid")
        source_branch = item.get("source_branch")
        if iid is not None:
            mr_out.write(f"mr-{iid}\n")
        if source_branch:
            branch_out.write(f"{source_branch}\n")
PY

  if [[ "${item_count}" -lt 100 ]]
  then
    break
  fi

  page=$((page + 1))
done

echo "[Information] Looking up remote branches already merged into ${CI_DEFAULT_BRANCH}."
git --no-pager fetch --prune origin "+refs/heads/*:refs/remotes/origin/*"
git --no-pager for-each-ref \
  --merged="refs/remotes/origin/${CI_DEFAULT_BRANCH}" \
  --format='%(refname:short)' \
  refs/remotes/origin \
  | sed -n 's|^origin/||p' \
  | grep -v -E "^(${CI_DEFAULT_BRANCH}|HEAD)$" \
  > "${merged_branch_names}" || true

if [[ -s "${merged_mr_source_branches}" ]]
then
  cat "${merged_mr_source_branches}" >> "${merged_branch_names}"
fi

if [[ -s "${merged_branch_names}" ]]
then
  sort -u "${merged_branch_names}" | while IFS= read -r ref_name
  do
    [[ -z "${ref_name}" ]] && continue
    ref_slug="$(slugify_ref_name "${ref_name}")"
    [[ -z "${ref_slug}" ]] && continue
    echo "ref-${ref_slug}" >> "${merged_ref_dirs}"
  done
fi

sort -u "${merged_mr_dirs}" -o "${merged_mr_dirs}"
sort -u "${merged_ref_dirs}" -o "${merged_ref_dirs}"

find "${env_storage_root}" -mindepth 3 -maxdepth 3 -type d \( -name 'mr-*' -o -name 'ref-*' \) | sort > "${candidates}"

if [[ ! -s "${candidates}" ]]
then
  echo "[Information] No mr-* or ref-* storage targets found under ${env_storage_root}."
  exit 0
fi

removed_count=0
while IFS= read -r cache_target_dir
do
  cache_target_name="$(basename "${cache_target_dir}")"
  remove_dir=false

  case "${cache_target_name}" in
    mr-*)
      if grep -Fxq "${cache_target_name}" "${merged_mr_dirs}"
      then
        remove_dir=true
      fi
      ;;
    ref-*)
      if grep -Fxq "${cache_target_name}" "${merged_ref_dirs}"
      then
        remove_dir=true
      fi
      ;;
  esac

  if [[ "${remove_dir}" == "true" ]]
  then
    case "${cache_target_dir}" in
      "${env_storage_root}"/*)
        echo "[Information] Removing stale cache target: ${cache_target_dir}"
        rm -rf "${cache_target_dir}"
        removed_count=$((removed_count + 1))
        ;;
      *)
        echo "[Error] Refusing to remove unexpected path: ${cache_target_dir}" >&2
        exit 1
        ;;
    esac
  fi
done < "${candidates}"

echo "[Information] Removed ${removed_count} stale cache target director$( [[ "${removed_count}" == "1" ]] && echo "y" || echo "ies" )."
