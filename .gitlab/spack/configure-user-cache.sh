#! /bin/bash
##############################################################################
# Copyright (c) 2019-2026, Lawrence Livermore National Security, LLC and
# RADIUSS project contributors. See the COPYRIGHT file for details.
#
# SPDX-License-Identifier: (MIT)
##############################################################################

: "${CI_PIPELINE_ID:=manual}"
: "${CI_JOB_ID:=local-$$}"

MY_SPACK_USER_CACHE="/dev/shm/llnl-stack-${CI_PIPELINE_ID}-${CI_JOB_ID}/spack-cache"
export MY_SPACK_USER_CACHE
export SPACK_USER_CACHE_PATH="${MY_SPACK_USER_CACHE}"

mkdir -p "${SPACK_USER_CACHE_PATH}"

echo "[Information] SPACK_USER_CACHE_PATH=${SPACK_USER_CACHE_PATH}"
