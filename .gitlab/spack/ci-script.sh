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
export SPACK_USER_CACHE_PATH="${MY_SPACK_USER_CACHE}"
: "${CACHE_TARGET:=manual}"
export CACHE_TARGET
BUILD_CACHE_MIRROR="oci://${CI_REGISTRY_IMAGE}/${CACHE_TARGET}/${SPACK_TARGET}"
MAIN_BUILD_CACHE_MIRROR="oci://${CI_REGISTRY_IMAGE}/main/${SPACK_TARGET}"
spack --version
spack ${MY_SPACK_DEBUG} env activate --without-view ${SPACK_CONCRETE_ENV_DIR}
spack ${MY_SPACK_DEBUG} config blame repos
spack ${MY_SPACK_DEBUG} repo update
spack ${MY_SPACK_DEBUG} config blame repos
spack ${MY_SPACK_DEBUG} config blame mirrors
spack ${MY_SPACK_DEBUG} mirror rm buildcache-destination || true
spack ${MY_SPACK_DEBUG} mirror rm buildcache-main || true
if [[ "${CACHE_TARGET}" != "main" ]]
then
  spack ${MY_SPACK_DEBUG} mirror add --oci-username-variable CI_REGISTRY_USER --oci-password-variable CI_REGISTRY_PASSWORD buildcache-main "${MAIN_BUILD_CACHE_MIRROR}"
fi
spack ${MY_SPACK_DEBUG} mirror add --oci-username-variable CI_REGISTRY_USER --oci-password-variable CI_REGISTRY_PASSWORD buildcache-destination "${BUILD_CACHE_MIRROR}"
spack ${MY_SPACK_DEBUG} config blame mirrors
spack ${MY_SPACK_DEBUG} spec "/${SPACK_JOB_SPEC_DAG_HASH}"
spack ${MY_SPACK_DEBUG} ci rebuild
