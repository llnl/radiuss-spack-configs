#! /bin/bash
##############################################################################
# Copyright (c) 2019-2026, Lawrence Livermore National Security, LLC and
# RADIUSS project contributors. See the COPYRIGHT file for details.
#
# SPDX-License-Identifier: (MIT)
##############################################################################

: "${MY_ENV_NAME:?MY_ENV_NAME must be set}"
: "${LCSCHEDCLUSTER:?LCSCHEDCLUSTER must be set}"
: "${SPACK_TARGET:?SPACK_TARGET must be set}"
: "${SPACK_CI_STORAGE_ROOT:=/usr/workspace/radiuss/rsc-ci}"
: "${SPACK_CI_STORAGE_GROUP:=radiuss}"
: "${SPACK_CI_STORAGE_UMASK:=0002}"
: "${CACHE_TARGET:=manual}"
: "${SPACK_CI_CONFIGURE_ENV:=true}"

export CACHE_TARGET
export SPACK_CI_STORAGE_ROOT
export SPACK_CI_STORAGE_GROUP

SPACK_CI_TARGET_ROOT="${SPACK_CI_STORAGE_ROOT}/${MY_ENV_NAME}/${LCSCHEDCLUSTER}/${SPACK_TARGET}/${CACHE_TARGET}"
SPACK_CI_MAIN_ROOT="${SPACK_CI_STORAGE_ROOT}/${MY_ENV_NAME}/${LCSCHEDCLUSTER}/${SPACK_TARGET}/main"

SPACK_CI_TARGET_INSTALL_ROOT="${SPACK_CI_TARGET_ROOT}/install"
SPACK_CI_TARGET_BUILDCACHE_ROOT="${SPACK_CI_TARGET_ROOT}/buildcache"
SPACK_CI_MAIN_INSTALL_ROOT="${SPACK_CI_MAIN_ROOT}/install"
SPACK_CI_MAIN_BUILDCACHE_ROOT="${SPACK_CI_MAIN_ROOT}/buildcache"

SPACK_CI_TARGET_BUILDCACHE_URL="file://${SPACK_CI_TARGET_BUILDCACHE_ROOT}"
SPACK_CI_MAIN_BUILDCACHE_URL="file://${SPACK_CI_MAIN_BUILDCACHE_ROOT}"

export SPACK_CI_TARGET_ROOT
export SPACK_CI_MAIN_ROOT
export SPACK_CI_TARGET_INSTALL_ROOT
export SPACK_CI_TARGET_BUILDCACHE_ROOT
export SPACK_CI_MAIN_INSTALL_ROOT
export SPACK_CI_MAIN_BUILDCACHE_ROOT
export SPACK_CI_TARGET_BUILDCACHE_URL
export SPACK_CI_MAIN_BUILDCACHE_URL

echo "[Information] SPACK_CI_TARGET_ROOT=${SPACK_CI_TARGET_ROOT}"
echo "[Information] SPACK_CI_MAIN_ROOT=${SPACK_CI_MAIN_ROOT}"
echo "[Information] SPACK_CI_STORAGE_GROUP=${SPACK_CI_STORAGE_GROUP}"

if ! umask "${SPACK_CI_STORAGE_UMASK}"
then
  echo "[Error] Unable to set SPACK_CI_STORAGE_UMASK=${SPACK_CI_STORAGE_UMASK}" >&2
  exit 1
fi

ensure_storage_dir()
{
  local storage_dir="$1"
  local storage_group
  local storage_mode

  if ! mkdir -p "${storage_dir}"
  then
    echo "[Error] Unable to create persistent CI storage directory ${storage_dir}" >&2
    exit 1
  fi

  storage_group="$(stat -c "%G" "${storage_dir}" 2>/dev/null || stat -f "%Sg" "${storage_dir}")"
  if [[ "${storage_group}" != "${SPACK_CI_STORAGE_GROUP}" ]] && ! chgrp "${SPACK_CI_STORAGE_GROUP}" "${storage_dir}"
  then
    echo "[Error] Unable to assign group ${SPACK_CI_STORAGE_GROUP} to ${storage_dir}" >&2
    exit 1
  fi

  storage_mode="$(stat -c "%A" "${storage_dir}" 2>/dev/null || stat -f "%Sp" "${storage_dir}")"
  if [[ "${storage_mode:4:3}" != "rws" ]] && ! chmod g+rwxs "${storage_dir}"
  then
    echo "[Error] Unable to make ${storage_dir} group-writable and setgid" >&2
    exit 1
  fi
}

ensure_storage_dir "${SPACK_CI_STORAGE_ROOT}"
ensure_storage_dir "${SPACK_CI_TARGET_ROOT}"
ensure_storage_dir "${SPACK_CI_TARGET_INSTALL_ROOT}"
ensure_storage_dir "${SPACK_CI_TARGET_BUILDCACHE_ROOT}"

spack ${MY_SPACK_DEBUG} mirror rm buildcache-destination || true
spack ${MY_SPACK_DEBUG} mirror rm buildcache-main || true

if [[ "${CACHE_TARGET}" != "main" ]]
then
  ensure_storage_dir "${SPACK_CI_MAIN_ROOT}"
  ensure_storage_dir "${SPACK_CI_MAIN_BUILDCACHE_ROOT}"
  spack ${MY_SPACK_DEBUG} mirror add --type binary --unsigned buildcache-main "${SPACK_CI_MAIN_BUILDCACHE_URL}"
fi

spack ${MY_SPACK_DEBUG} mirror add --type binary --unsigned buildcache-destination "${SPACK_CI_TARGET_BUILDCACHE_URL}"

if [[ "${SPACK_CI_CONFIGURE_ENV}" == "true" ]]
then
  spack ${MY_SPACK_DEBUG} config remove upstreams:radiuss-main || true

  if [[ "${CACHE_TARGET}" != "main" && -f "${SPACK_CI_MAIN_INSTALL_ROOT}/.spack-db/index.json" ]]
  then
    spack ${MY_SPACK_DEBUG} config add "upstreams:radiuss-main:install_tree:${SPACK_CI_MAIN_INSTALL_ROOT}"
  elif [[ "${CACHE_TARGET}" != "main" ]]
  then
    echo "[Information] Main install tree database not found; skipping radiuss-main upstream."
  fi

  spack ${MY_SPACK_DEBUG} config add "config:install_tree:root:${SPACK_CI_TARGET_INSTALL_ROOT}"
  spack ${MY_SPACK_DEBUG} config add "packages:all:permissions:read:world"
  spack ${MY_SPACK_DEBUG} config add "packages:all:permissions:write:group"
  spack ${MY_SPACK_DEBUG} config add "packages:all:permissions:group:${SPACK_CI_STORAGE_GROUP}"
fi
