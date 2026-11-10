.. Copyright (c) 2026, Lawrence Livermore National Security, LLC and
.. RADIUSS project contributors. SPDX-License-Identifier: (MIT)

Experimental environment builds with rad-bat
============================================

Select ``RSC_BUILD_MODE=parallel`` to build each machine's whole environment
in one GitLab job. The generated Spack CI backend remains the default.
The pilot uses the repository's ``bin/rad-bat env`` workflow and pinned Spack
1.2.2. Project workflows use the same checkout, isolation, storage, publication
and timed-section helpers.

Jacamar batch runners obtain the allocations using ``[batch, <machine>]``
tags and ``SCHEDULER_PARAMETERS``. GitLab waits through queueing and execution.
Inside that allocation, rad-bat launches one native Spack installer per node
and waits for all workers. It never obtains a top-level allocation.

The default is **one node**. Optional multi-node builds use Spack's existing
prefix locks and installation database to coordinate work on a shared filesystem.
Each node has its own jobserver CPU budget and two concurrent packages by
default. An individual package's compilation stays on one node.

Configuration
-------------

Start with these variables in GitLab's Run pipeline form:

.. code-block:: text

   MY_ENV_NAME=shared-ci
   RSC_BUILD_MODE=parallel
   ON_CORONA=OFF
   RSC_PARALLEL_CASE=first-filesystem

Corona requires ``RSC_CORONA_PARALLEL_ALLOC`` with confirmed CI queue arguments,
or ``ON_CORONA=OFF``. Dane uses ``--reservation=ci``; Tioga and Tuolumne use
``--queue=pci``. Full allocation arguments may be overridden through
``RSC_<MACHINE>_PARALLEL_ALLOC``. Keep node counts and time limits consistent
with the controls below. The GitLab timeout is four hours to allow queue waiting.

.. list-table:: Pilot controls
   :header-rows: 1
   :widths: 40 20 40

   * - Variable
     - Default
     - Purpose
   * - ``RSC_PARALLEL_NODES``
     - ``1``
     - Nodes and installer workers per machine.
   * - ``RSC_PARALLEL_TIME_MINUTES``
     - ``60``
     - Allocation wall time.
   * - ``RSC_PARALLEL_STOP_MINUTES``
     - ``55``
     - Installation deadline from script start, including preparation.
   * - ``RSC_PARALLEL_PACKAGES``
     - ``2``
     - Concurrent packages per node.
   * - ``RSC_PARALLEL_JOBS``
     - Assigned CPUs
     - Optional cap on each node's jobserver budget.
   * - ``RSC_PARALLEL_CASE``
     - ``pilot``
     - Experiment/storage namespace.
   * - ``RSC_PARALLEL_LOCKFILE``
     - Unset
     - Explicit previous lock file for matching cold comparisons.
   * - ``RSC_PARALLEL_REPORT``
     - ``ON``
     - Best-effort dependency tree; use ``OFF`` to omit it.
   * - ``RSC_PARALLEL_STORAGE_ROOT``
     - ``/usr/workspace/radiuss/rsc-ci-parallel-pilot``
     - Filesystem storage independent of production installs and caches.

Reserve at least five minutes between the installation deadline and allocation
expiry. Successful builds may use this interval for publication. Interrupted
builds stop without publishing. Flux tasks are explicitly signalled and awaited;
terminating their attach process alone could leave them running.

Persistence and cache publication
---------------------------------

All initial storage is on the filesystem: Spack, package repositories,
bootstrap assets, archives, stages, logs and installed packages. Temporary
socket paths use the shorter ``<storage-root>/tmp/<CI_JOB_ID>/<rank>``.

.. code-block:: text

   <storage-root>/<environment>/<machine>/<target>/<CACHE_TARGET>/<case>/nodes-<N>/
     install/                     # incomplete and completed installations
     buildcache/                  # publication after environment success
     pipelines/<CI_PIPELINE_ID>/
       spack/<commit>/checkout/
       spack/<commit>/isolation/
       sources/
       bootstrap/
       cache/                     # package repository checkouts
       environments/<input-digest>/environment/
       attempts/<CI_JOB_ID>/workers/<rank>/

A retry reuses the prepared concrete environment and completed installations.
The preparation identity includes input YAML/recipe files (following machine
symlinks), selected revisions, storage configuration, explicit lock file, and
``LCSCHEDCLUSTER``, ``SYS_TYPE`` and ``SPACK_TARGET``. Changed inputs create a new
prepared environment; installed packages remain available to Spack. Additional
site-specific environment-variable inputs require a new work directory or case.
Package repositories are frozen to shared paths before workers start.

There is **no autopush**. Failed and interrupted environments retain progress
in the install tree, with no publication. After every worker succeeds, rad-bat
verifies the roots and runtime dependency closure, then publishes installed,
non-external packages from the environment. Cached packages need not have
local build-only dependencies. Production mirrors and upstreams are replaced
by the pilot mirror.

Publication failures fail the job. A retry reuses the completed installation
and retries publication, skipping complete cache entries. A multi-package push
can fail partway through; publication is success-gated, not a mirror transaction.

GitLab's resource group serializes jobs sharing a pilot namespace. rad-bat also
protects each preparation workspace against simultaneous coordinators. Neither
lock is taken by individual installation workers. The existing project-mode
install-tree lock is retained for a separate future review.

Logs and optional reporting
---------------------------

Preparation, concretization, installation and publication have timed collapsible
sections. Persistent attempts retain worker placement, CPU budgets, exit status,
native Spack logs/JUnit and the concrete manifest/lock. The GitLab ``after_script``
collects these artifacts after failures too, without running Spack or publishing.
GitLab receives an environment-level JUnit result, including publication failures.

The optional dependency tree is an independent artifact reader:

.. code-block:: console

   python3 -m rad_bat.report /path/to/attempt-or-collected-artifacts

It reads the saved lock and native reports without importing Spack. Missing or
truncated reports yield ``unreported`` entries; they do not prove failure.
It does not infer dependency-blocked states or distinguish every source/binary
reuse case. Report availability never controls build success or publication.

Validation
----------

Run the project/environment unit tests and CI adapter tests locally:

.. code-block:: console

   python3 -m unittest discover -s tests -v
   spack python -m unittest discover -s .gitlab/spack/parallel/tests -v
   spack python .gitlab/spack/parallel/tests/smoke.py --out /absolute/path/to/new-smoke-directory

The native smoke uses local fixture recipes and a local Spack checkout. It
checks intentional partial failure with no cache publication, persistent retry,
successful publication, warm retry, and two concurrent installers restoring
binaries into a fresh shared install tree. It retains diagnostics.

LC validation must still check Jacamar placement, CPU budgets and cancellation:
start with ``shared-ci`` on one node, then compare two nodes using the same lock
and separate cold case namespaces. Retry failed/interrupted jobs and confirm
cache publication waits for success. After that baseline works, compare shared
memory for disposable work while keeping installs persistent. Apply PR 210's
cached-cmake changes as the final scenario. No shared-memory mode is enabled yet.
