#! /bin/bash
##############################################################################
# Copyright (c) 2019-2025, Lawrence Livermore National Security, LLC and
# RADIUSS project contributors. See the COPYRIGHT file for details.
#
# SPDX-License-Identifier: (MIT)
##############################################################################

set -eo pipefail

hostname

# If the job is not running in a shared alloc (alloc expired or job manually triggered),
# then we need to get-spack again
[[ -z "${ALLOC_ID:-}" ]] && "${CI_PROJECT_DIR}/.gitlab/scripts/get-spack"

. ${MY_SPACK_PARENT_DIR}/spack/share/spack/setup-env.sh
export SPACK_DISABLE_LOCAL_CONFIG=""
. ${CI_PROJECT_DIR}/.gitlab/spack/configure-user-cache.sh
spack --version
SPACK_CI_CONFIGURE_ENV=false
. ${CI_PROJECT_DIR}/.gitlab/spack/configure-storage.sh
spack ${MY_SPACK_DEBUG} config blame mirrors
if ! spack buildcache update-index buildcache-destination
then
  if [[ -d "${SPACK_CI_TARGET_BUILDCACHE_ROOT}" ]] && ! find "${SPACK_CI_TARGET_BUILDCACHE_ROOT}" -mindepth 1 -print -quit | grep -q .
  then
    echo "[Information] Destination buildcache is empty; skipping index update."
  else
    echo "[Error] Unable to update buildcache-destination index." >&2
    exit 1
  fi
fi
