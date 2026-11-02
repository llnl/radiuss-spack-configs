.. Copyright (c) 2026, Lawrence Livermore National Security, LLC and
.. other RADIUSS Project Developers. See the top-level COPYRIGHT file.
.. SPDX-License-Identifier: (MIT)

.. _CI Implementation:

Validation environments and storage
===================================

This repository uses `Spack pipelines
<https://spack.readthedocs.io/en/latest/pipelines.html>`_ to validate Spack
environments on LC machines. These pipelines are separate from the
:doc:`consumer build/test workflow <../user_guide/ci>`.

Choose a validation environment
-------------------------------

Each run selects one environment using ``MY_ENV_NAME``. Its value must name a
directory under ``.gitlab/spack/envs``.

.. list-table:: Environment purposes
   :header-rows: 1
   :widths: 25 75

   * - Environment
     - Purpose
   * - ``shared-ci``
     - Validate the RADIUSS shared stack. This is the configured GitLab default.
   * - ``cached-cmake``
     - Validate behavior involving CachedCMake packages. Its implementation is
       currently being revised.
   * - Additional environments
     - Support other validation goals with their own specifications, recipe
       baseline, engine selection, and machine coverage.

The GitLab project configuration supplies the ``shared-ci`` default; the
repository consumes the selected value through ``MY_ENV_NAME``. An unset or
empty value takes the no-environment path, rather than assigning a default in
``.gitlab-ci.yml``.

.. important::

   Pushing changes to ``cached-cmake`` still starts the default pipeline.
   Cancel that pipeline and manually run a pipeline for the same branch or
   commit with ``MY_ENV_NAME=cached-cmake`` in GitLab's pipeline variables.
   Confirm the selected environment in the resulting pipeline. Automatic
   selection based on changed files is a separate engineering follow-up.

For shared-file changes, validate every affected environment explicitly. The
``shared-ci`` specifications and ``gitlab/radiuss-jobs/<machine>.yml`` are
maintained separately; check their consistency when editing either one.

.. _ci-file-structure:
.. _main-ci-pipeline:
.. _machine-pipelines:
.. _scripts:
.. _spack-pipeline-feature:

CI file structure
-----------------

``.gitlab-ci.yml`` defines stages, storage namespace selection, and conditional
includes. Each environment supplies:

* ``spack.yaml`` with specifications, configuration includes, and the
  ``spack.repos.builtin.commit`` recipe pin.
* ``pipeline.yml`` with ``MY_SPACK_REPO``, ``MY_SPACK_BRANCH`` or
  ``MY_SPACK_COMMIT``, and includes for the machines to validate.

``.gitlab/variables.yml`` provides machine variables. Machine pipeline files
allocate resources, generate a Spack pipeline, and trigger its build jobs.
``.gitlab/spack/ci.yaml`` configures generation. General scripts live in
``.gitlab/scripts``; Spack-specific scripts live in ``.gitlab/spack``.

When adding an environment, review its configuration links, generation scripts,
and artifacts as well as its YAML. The current generation script still copies
some configuration inputs from ``shared-ci``; do not assume a new environment
is fully independent simply because it has a new directory.

Storage lifetimes and reuse
---------------------------

.. graphviz:: /figures/repository-storage.dot
   :align: center
   :caption: Repository CI separates temporary work from persistent installations and buildcaches.
   :alt: The selected environment uses a checkout shared per machine and pipeline and a cache isolated per job. Default-branch jobs write main storage; branch jobs write their own namespace and can read main binaries.

Persistent storage is rooted at:

.. code-block:: text

   ${SPACK_CI_STORAGE_ROOT}/
     ${MY_ENV_NAME}/
       ${LCSCHEDCLUSTER}/
         ${SPACK_TARGET}/
           ${CACHE_TARGET}/
             install/
             buildcache/

``SPACK_CI_STORAGE_ROOT`` defaults to ``/usr/workspace/radiuss/rsc-ci``.
The default branch uses ``CACHE_TARGET=main``; other branch pipelines normally
use ``ref-${CI_COMMIT_REF_SLUG}``. An explicit ``CACHE_TARGET`` overrides that
selection, and the fallback for other contexts is ``manual``.

The install tree is the reuse path for installed packages. The filesystem
buildcache provides binaries and mirror metadata that Spack CI uses to prune
already-built specifications during pipeline generation. A non-main pipeline
writes its own namespace and reads the ``main`` buildcache; it also uses the
``main`` install tree as an upstream when that tree has a Spack database.
Experimental binaries therefore stay in the branch namespace under the normal
selection rules.

Two temporary layers have shorter lifetimes:

* The Spack checkout under ``MY_SPACK_PARENT_DIR`` on ``/dev/shm`` is shared by
  jobs for the same machine and pipeline, avoiding per-job clones.
* ``SPACK_USER_CACHE_PATH`` is computed at job runtime as
  ``/dev/shm/llnl-stack-${CI_PIPELINE_ID}-${CI_JOB_ID}/spack-cache``. Staging,
  test, and miscellaneous caches are isolated per job.

The storage setup uses ``SPACK_CI_STORAGE_GROUP`` (default ``radiuss``),
world-readable/group-writable package permissions, setgid directories, and a
normally ``0002`` umask. Keep these settings consistent so service jobs and
maintainers can share the persistent data.

Cleanup
-------

The cleanup job scans all environments under the persistent storage root and
removes stale ``ref-*`` targets associated with branches already merged into
``main`` or no longer present remotely. It is opt-in: both ``MY_ENV_NAME=""``
and ``RSC_CLEANUP="ON"`` are required, normally on a scheduled pipeline.
Regular branch pipelines, including ``develop``, do not request cleanup by
default. Review the cleanup script and selected storage root before scheduling
it; this procedure deletes persistent build data.
