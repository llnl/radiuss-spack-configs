#! /bin/bash
##############################################################################
# Copyright (c) 2019-2025, Lawrence Livermore National Security, LLC and
# RADIUSS project contributors. See the COPYRIGHT file for details.
#
# SPDX-License-Identifier: (MIT)
##############################################################################

hostname

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"

# If the job is not running in a shared alloc (alloc expired or job manually triggered),
# then we need to get-spack again
[[ -z "${JOBID:-}" ]] && "${project_dir}/.gitlab/scripts/get-spack"

. ${MY_SPACK_PARENT_DIR}/spack/share/spack/setup-env.sh
export SPACK_DISABLE_LOCAL_CONFIG=""
. ${CI_PROJECT_DIR}/.gitlab/spack/configure-user-cache.sh
spack --version
SPACK_CI_CONFIGURE_ENV=false
. ${CI_PROJECT_DIR}/.gitlab/spack/configure-storage.sh
spack ${MY_SPACK_DEBUG} config blame mirrors
spack buildcache update-index --keys buildcache-destination
