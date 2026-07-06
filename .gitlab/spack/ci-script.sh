#! /bin/bash
##############################################################################
# Copyright (c) 2019-2025, Lawrence Livermore National Security, LLC and
# RADIUSS project contributors. See the COPYRIGHT file for details.
#
# SPDX-License-Identifier: (MIT)
##############################################################################

set -eo pipefail

hostname

. ${MY_SPACK_PARENT_DIR}/spack/share/spack/setup-env.sh
export SPACK_DISABLE_LOCAL_CONFIG=""
. ${CI_PROJECT_DIR}/.gitlab/spack/configure-user-cache.sh
spack --version
spack ${MY_SPACK_DEBUG} env activate --without-view ${SPACK_CONCRETE_ENV_DIR}
spack ${MY_SPACK_DEBUG} config blame repos
spack ${MY_SPACK_DEBUG} repo update
spack ${MY_SPACK_DEBUG} config blame repos
. ${CI_PROJECT_DIR}/.gitlab/spack/configure-storage.sh
spack ${MY_SPACK_DEBUG} config blame mirrors
spack ${MY_SPACK_DEBUG} config blame upstreams
spack ${MY_SPACK_DEBUG} config blame config
spack ${MY_SPACK_DEBUG} spec "/${SPACK_JOB_SPEC_DAG_HASH}"
spack ${MY_SPACK_DEBUG} ci rebuild
