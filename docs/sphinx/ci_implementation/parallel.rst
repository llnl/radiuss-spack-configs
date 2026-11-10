.. Copyright (c) 2026, Lawrence Livermore National Security, LLC and
.. RADIUSS project contributors. SPDX-License-Identifier: (MIT)

Experimental parallel environment builds
========================================

Select ``RSC_BUILD_MODE=parallel`` to build each machine's entire environment
in one GitLab job. The existing generated Spack CI backend remains the default.
Begin with ``MY_ENV_NAME=shared-ci`` on the experimental branch.

Jacamar batch runners own the allocations. Jobs use ``[batch, <machine>]``
tags and ``SCHEDULER_PARAMETERS``; GitLab waits through queueing and execution.
There are no separate allocation, generated package-build, or release jobs.
Inside the allocation, the script starts one native Spack installer per node.
Spack's prefix locks prevent duplicate installations. Each node has its own
jobserver budget and defaults to two concurrent packages. The jobserver does
not distribute one package's compilation across multiple nodes.

Configuration
-------------

Supply these variables in GitLab's Run pipeline form:

.. code-block:: text

   MY_ENV_NAME=shared-ci
   RSC_BUILD_MODE=parallel
   ON_CORONA=OFF
   RSC_PARALLEL_CASE=first-filesystem

``ON_CORONA=OFF`` is required until Corona's CI queue is confirmed. To enable
Corona, instead supply ``RSC_CORONA_PARALLEL_ALLOC`` with the full Flux
allocation arguments for that queue. The setup job fails if Corona is enabled
without these arguments, preventing a misleading partial validation.

.. list-table:: Experimental controls
   :header-rows: 1
   :widths: 40 20 40

   * - Variable
     - Default
     - Purpose
   * - ``RSC_PARALLEL_NODES``
     - ``2``
     - Nodes and installer workers per machine.
   * - ``RSC_PARALLEL_TIME_MINUTES``
     - ``60``
     - Allocation wall time.
   * - ``RSC_PARALLEL_STOP_MINUTES``
     - ``55``
     - Soft stop measured from build-script start, including bootstrap.
   * - ``RSC_PARALLEL_PACKAGES``
     - ``2``
     - Concurrent packages per installer.
   * - ``RSC_PARALLEL_JOBS``
     - Assigned CPU affinity
     - Optional per-node CPU budget cap.
   * - ``RSC_PARALLEL_CASE``
     - ``pilot``
     - Isolated experiment or benchmark label.
   * - ``RSC_PARALLEL_LOCKFILE``
     - Unset
     - Persistent absolute path to a previously produced lock file, for matching cold comparisons.
   * - ``RSC_PARALLEL_STORAGE_ROOT``
     - ``/usr/workspace/radiuss/rsc-ci-parallel-pilot``
     - Persistent storage independent of production installs and caches.

Dane uses ``--reservation=ci``; Tioga and Tuolumne use ``--queue=pci``.
Override full machine arguments through ``RSC_DANE_PARALLEL_ALLOC``,
``RSC_TIOGA_PARALLEL_ALLOC`` or ``RSC_TUOLUMNE_PARALLEL_ALLOC`` when needed.
Keep their exclusive node count and time limit consistent with the controls
above; changing only the scheduler arguments does not change the worker count
or soft deadline. Reserve at least five minutes for finalization.

The GitLab timeout is four hours, allowing queue waiting before the allocation
starts. The allocation itself remains limited to the configured wall time.
Existing ``ON_<MACHINE>=OFF`` controls select machines. There is a resource
group per storage namespace, serializing jobs that could share installations
or cache metadata.

Filesystem storage and retry
----------------------------

Everything starts on the filesystem: Spack, pinned repositories, bootstrap
assets, source archives, stages, temporary files, logs, and installed prefixes.
``TMPDIR`` uses a shorter ``<storage-root>/tmp/<CI_JOB_ID>/<rank>`` path to
accommodate Python's multiprocessing Unix sockets. This is also filesystem
storage; long experiment paths do not become socket filenames.

.. code-block:: text

   <storage-root>/<environment>/<machine>/<target>/<CACHE_TARGET>/<case>/nodes-<N>/
     install/
     buildcache/
     sources/
     bootstrap/
     pipelines/<CI_PIPELINE_ID>/
       spack/
       cache/                     # prepared package repositories
       environment/               # frozen manifest and concrete lock
       attempts/<CI_JOB_ID>/
         workers/<rank>/          # filesystem stage/cache/logs

The package repositories are resolved during bootstrap and frozen to shared
filesystem paths before workers start. Retries retain the same concrete lock,
Spack checkout and install tree. A retry receives a new attempt directory and
fresh worker stages; completed packages are skipped by the native installer.
Missing installations can be restored from the pilot binary cache. Production
upstreams and binary mirrors are overridden, so a new case and node count
provide isolated cold runs. Source archives are reused within a namespace.

Successful source installations use native buildcache autopush immediately.
Before and after installation, native buildcache push reconciles completed
prefixes whose uploads may have been interrupted. Existing complete entries
are skipped; indexes are rebuilt after reconciliation. Upload failures fail
the job even when the installation itself completed.

Results and interruption
------------------------

The job prints a final dependency tree and package-state counts. GitLab
artifacts contain ``tree.txt``, ``results.json``, normalized JUnit, the concrete
environment, worker logs, available package build logs, and cache diagnostics.
The JSON also records elapsed time, estimated node-hours and worker placement.

Results distinguish successful, reused, external, failed, dependency-blocked,
interrupted and unnecessary packages. A build-only dependency omitted because
its parent was restored from cache is unnecessary, rather than a failure.
Shared dependencies appear once in the full tree and are referenced thereafter.

Native reports are combined by full DAG hash with installation database
snapshots and status lines. Soft stops signal workers and allow Spack to release
its locks, then take a final snapshot and reconcile uploads. Flux workers are
explicitly signalled; terminating an attach command alone can merely detach it.
The ``after_script`` collects retained filesystem diagnostics after hard failures
and attempts a read-only recovery snapshot. An unavailable snapshot is reported
as incomplete evidence; the job does not claim success.

Validation sequence
-------------------

1. Run ``shared-ci`` with filesystem storage. Confirm distinct worker nodes,
   correct CI resources, job completion waiting, and binary-cache publication.
2. Compare cold one-node and two-node runs using different case labels and the
   same lock file for each machine. A cold case must have an empty install tree
   and binary cache. Record elapsed time, node-hours and completed packages.
3. Retry a failed or interrupted job. Verify persistent successes are reused,
   missing uploads recover and remaining packages resume. Test GitLab cancellation.
4. Once filesystem operation is validated, add the shared-memory staging
   comparison on this branch. Use identical locks/resources and separate empty
   install namespaces. Keep installations and the authoritative Spack checkout
   on the filesystem. Shared-memory staging is not enabled in this first version.
5. Apply PR 210's ``cached-cmake`` changes as the final environment validation.
   Inspect each pipeline with ``cz-ci``; keep package fixes separate from backend changes.

Local checks
------------

The standard-library test suite runs without a cluster:

.. code-block:: console

   python3 -m unittest discover -s .gitlab/spack/parallel/tests -v

Run it with ``spack python -m unittest discover`` to include Spack's real YAML
schema validation. For an offline native integration check, use a Spack 1.2.2
checkout that includes its mock package repositories:

.. code-block:: console

   spack python .gitlab/spack/parallel/tests/smoke.py --out /absolute/path/to/new-smoke-directory

The smoke check creates small fixture packages and runs concurrent native
installers, autopush, reconciliation and a warm retry. It uses no scheduler or
production storage and retains its logs for inspection. These local checks do
not verify Jacamar runner deployment or scheduler behavior on LC.
