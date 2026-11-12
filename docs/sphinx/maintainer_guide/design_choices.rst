.. Copyright (c) 2026, Lawrence Livermore National Security, LLC and
.. RADIUSS project contributors. SPDX-License-Identifier: (MIT)

Design choices: the rad-bat contract
====================================

This page records the assumptions behind rad-bat and the boundaries that keep
it small. It is a contract for callers and maintainers, with concrete examples
of what a retry means and which files must survive it. Command syntax is in
:doc:`../reference/rad_bat`.

Three workflows, one project handoff
------------------------------------

rad-bat prepares dependencies or a complete environment using Spack. For
projects, it also provides a common entry point that invokes a project-owned
build/test command with a host configuration.

.. list-table:: Inputs and successful results
   :header-rows: 1
   :widths: 18 40 42

   * - Workflow
     - Caller supplies
     - rad-bat produces or does
   * - ``host-config``
     - An existing CMake host-config and the project's JSON configuration.
     - Checks the file exists and invokes the project command. No Spack run.
   * - ``spack``
     - The project's JSON, a machine configuration and a single root spec
       assembled from the package name and the requested spec fragment.
     - Creates an intermediate Spack environment, installs dependencies,
       retains a host-config, optionally publishes dependencies, then invokes
       the same project command.
   * - ``env``
     - A Spack environment file and the reference of Spack to run.
     - Installs the environment and optionally publishes its packages. No
       project JSON, project command or host-config is required.

The project command owns CMake configuration, compilation, installation,
CTest, benchmarks and project-specific reports. rad-bat supplies its arguments,
a timed enclosing section and failure propagation. The command may use the
shared logging utilities, and can also be invoked directly by a developer.

In project Spack mode, the default stopping phase is ``initconfig``. A project
may select another phase with ``spack.until``, but the workflow still requires
exactly one newly generated or modified top-level ``.cmake`` file. Completing
a phase without producing the expected host-config is an error. Host-config
mode consumes an existing file; it never tries to generate a missing one.

Versions and ownership of Spack
-------------------------------

Spack 1.2 is the minimum supported version. Projects can update RADIUSS Spack
Configs without automatically changing their Spack pin. Known incompatibilities
must be reported; support for 1.2 and newer is not a guarantee that every future
Spack release will work unchanged. Package repository API incompatibilities
remain Spack diagnostics.

Each scenario owns one workspace and one Spack checkout. The caller owns the
choice of scenarios and their directory names. rad-bat checks out the requested
commit and uses ``spack isolate``; it does not repair a checkout moved to a
different commit. A new Spack reference requires a new workspace.

Only the bootstrap code must run before Spack exists. Environment creation,
configuration parsing, package repository checkout, concretization, package
locking and buildcache publication use native Spack mechanisms. The small
``rad_bat.spack_helpers`` module runs under ``spack python -m`` and uses Spack's
Python APIs. A separate extension command is not needed to duplicate those
operations. Keep the host-config workflow independent of Spack imports.

Configuration sources and precedence
------------------------------------

The project JSON records the Spack commit, package repository commits, the
machine configuration path template and project-specific settings. Developers
edit these references in one place. The intermediate environment is generated
state, not a second configuration they must maintain.

A normal machine path template is:

.. code-block:: text

   scripts/radiuss-spack-configs/{sys_type}/{machine}/spack.yaml

``{sys_type}`` comes from ``SYS_TYPE`` and ``{machine}`` from ``LCSCHEDCLUSTER``.
For example, ``toss_4_x86_64_ib`` and ``corona`` select the Corona configuration
regardless of whether the job runs on ``corona82`` or another node. Hostnames
are not parsed to guess a cluster. ``--spack-env`` (or ``RAD_BAT_SPACK_ENV`` in
environment-driven project execution) explicitly selects a source file and
bypasses this selection. Missing inputs or configuration files are errors.

Each supported machine has a coherent ``packages.yaml`` containing its
toolchains and externals. Common general settings may be shared through
``config.yaml``. Navigability takes priority over eliminating every repeated
line; avoid splitting one toolchain definition across many files.

In ``env`` mode, the supplied environment defines its specs, package repository
pins, includes and reuse policies. The project JSON is not consulted. The
Spack checkout comes from ``--spack-url`` and ``--spack-commit``, falling back
to ``MY_SPACK_REPO`` and ``MY_SPACK_COMMIT`` when those arguments are absent.
The argument takes precedence over its environment variable.

Both modes exclude personal Spack configuration. Initial setup disables local
configuration before isolation; later commands use the isolated configuration
scope and a workspace-owned cache. Explicit upstreams and read mirrors remain
available. A personal ``~/.spack`` setting must not change a job's dependencies.
The machine's actual external installations must still match its configuration.

The environment may use includes; it need not be a single self-contained file.
Use paths supported by native ``spack env create``: keep relative includes
inside the environment directory, or use explicit absolute paths. Included
files kept outside the workspace, local recipe repositories and project source
checkouts must remain available and unchanged during a retry.

CI resource and module boundary
--------------------------------

The caller supplies an allocation. Jacamar or the surrounding CI manages
queueing, allocation lifetime and CI status. rad-bat never acquires or extends
an allocation. A developer supplies equivalent resources before invoking it.

``MODULE_LIST`` is a shell-quoted, whitespace-separated list of modules. When
set, rad-bat loads them using the site's Bash module initialization before
preparing dependencies or invoking a project. The resulting environment is
inherited by workers and the project command. Failure to load a requested
module is an error. Modules needed only by project-specific steps can instead
be managed by that project's script.

An environment build launches one native Spack installer per allocated node.
Each installer has a node-local CPU jobserver and may build several packages
concurrently. All installers see the same concrete environment and installation
tree; Spack's prefix locks and database coordinate installation. One package's
compilation stays on one node. Node count affects execution, not storage identity.

One coordinator owns a workspace at a time. The workspace lock is not held by
individual Spack workers. The existing project-mode install-tree lock remains
for a separate review; this contract does not silently remove it.

Storage: what survives and why
-------------------------------

The initial implementation uses filesystem storage. Shared-memory optimization
is deferred until the filesystem workflow is validated. In particular, a
host-config must reference persistent dependency installations, never packages
that disappear with an allocation or an ephemeral working directory.

.. graphviz:: /figures/rad-bat-storage.dot
   :align: center
   :caption: Durable installation paths connect host-config consumers to their dependencies.
   :alt: The scenario workspace stores Spack, the concrete environment and a retained host-config. Each CI attempt receives an artifact copy. The retained and copied host-configs reference the persistent install tree and optional upstreams. A binary cache supplies or receives packages, but does not preserve these filesystem paths.

.. list-table:: Storage responsibilities
   :header-rows: 1
   :widths: 25 42 33

   * - Location
     - Contents
     - Lifetime
   * - Scenario workspace
     - Spack, isolated configuration, package repositories, concrete
       environment, preparation state and the project's retained host-config.
     - Stable across retries of the same scenario.
   * - Installation tree
     - Completed packages, including progress from an unsuccessful environment
       build.
     - Persistent. Keep it while any host-config or upstream consumer needs it.
   * - Attempt outputs
     - Logs, reports and exported copies of host-configs.
     - A new environment output directory for each attempt; CI may collect
       and recreate artifact directories.
   * - Stages, caches and temporary files
     - Downloaded sources, compilation intermediates and worker socket files.
     - On the filesystem initially. They are not the published dependency
       installations.
   * - Binary cache
     - Transferable packages published after installation success.
     - A reuse source, not a substitute for a host-config's filesystem paths.

For a project scenario, a caller might choose:

.. code-block:: text

   /usr/workspace/raja-dev/rad-bat/raja/dane/<pipeline>/<job-name>/
     work/
       .rad-bat/
         spack/                 # one owned checkout
         isolation/             # native Spack isolation
         isolated               # isolation completed successfully
         cache/                 # Spack user cache
         repositories/          # repositories from the JSON
         spack-env/             # spack.yaml and fixed spack.lock
         prepared               # preparation completed
         host-configs/job.cmake # durable successful output
         host-config            # identifies that output for resumption
       build_.../               # example project-driver output
     install/                   # dependencies referenced by the host-config

   <CI checkout>/.rad-bat-artifacts/host-configs/job.cmake
                                # exported before publication, on each attempt

The caller sets ``RAD_BAT_WORK_DIR``, ``RAD_BAT_INSTALL_TREE`` and optionally
``RAD_BAT_OUTPUT_DIR`` accordingly. The project driver must restrict its cleanup
to its own build/install subdirectories, leaving ``.rad-bat`` intact.

The environment CI adapter uses the same pipeline/job-name identity, with
``attempts/<CI_JOB_ID>`` for logs. GitLab gives a retry a new job ID, so that ID
must not identify the persistent scenario. Node count is not part of the path.
The pilot can share an installation tree across pipelines while each pipeline
has a separate concrete environment. See :doc:`../ci_implementation/parallel`.

rad-bat has no installation cleanup manager. Teams or CI maintainers own
retention. A future RAJA cleanup policy could retain generations referenced by
versioned host-configs on develop and open branches; that policy is not
implemented here. Retention also covers any upstream prefixes those files use.

Retry means resume, not refresh
-------------------------------

Once preparation succeeds, the same workspace means the same inputs and the
same concrete environment. rad-bat prints that it is resuming and does not
re-read changed configuration to silently alter the build. It neither hashes
input files nor performs automatic invalidation or source updates.

Preparation interrupted before its completion marker can be repeated. After
concretization, an interrupted installation reuses completed packages under
Spack's control. Successful installation is recorded so a publication retry
can skip installation. A project artifact is restored from the durable
host-config copy even if the CI checkout was recreated.

.. list-table:: Concrete usage cases
   :header-rows: 1
   :widths: 42 58

   * - Situation
     - Expected action and result
   * - An environment installs 18 packages and fails on the nineteenth.
     - Retry the same job in the same pipeline. Keep its workspace and install
       tree, use a new attempt output directory, and let Spack reuse the 18
       completed installations. Nothing was published by the failed build.
   * - All project dependencies install, but cache publication fails.
     - The host-config is already retained and exported. The job fails before
       running the project command. Retry publication using the same concrete
       environment and installs; do not reconcretize or regenerate the file.
   * - Dependencies publish successfully, but RAJA tests fail.
     - Dependencies and host-config remain valid. The developer can use
       ``host-config`` mode or invoke the project driver directly to work on
       RAJA without starting Spack.
   * - A developer edits only RAJA sources.
     - Reuse the existing host-config for the normal project build/test loop.
   * - A developer changes a spec, a Spack pin or a machine configuration.
     - Choose a new scenario workspace. Keep old installations while consumers
       still refer to them. Existing upstreams and caches may still be reused.
   * - A developer wants the latest sources of a dependency at ``@develop``.
     - This is an explicit update, not a retry. rad-bat has no refresh command.
       A new workspace alone does not force new sources if Spack reuses an
       existing installation or binary. Manage the desired source reference
       and reuse/rebuild policy explicitly with Spack.
   * - The site replaces an externally installed compiler or library.
     - Update the machine configuration and prepare a new scenario. rad-bat
       does not monitor or restore the site's external installations.
   * - Compare one node with two nodes, or filesystem with shared memory.
     - Use separate pipelines. Keep the specs/lock comparable and explicitly
       control upstream and cache reuse for a cold comparison. Node count
       itself never creates a separate installation namespace.

These rules guarantee resumption under fixed inputs. They do not promise
bit-identical binaries across changes to external software or moving source
references. Automatic refresh and cross-pipeline continuation of the same
workspace are outside the contract.

Publication and success boundaries
-----------------------------------

.. graphviz:: /figures/rad-bat-success.dot
   :align: center
   :caption: Publication waits for installation success, while project tests remain a later step.
   :alt: Project dependency installation and host-config retention precede optional publication and the project command. Environment workers must all succeed and pass verification before publication. Failed publication preserves successful installation state for retry.

Autopush is disabled, including on inherited mirrors. For projects, dependency
installation and host-config validation must succeed before publication. For
environments, every installer must succeed and the installed root/runtime
closure must be verified. Partial build progress stays in the installation tree.

Spack performs package selection, skips existing cache entries and updates the
index. A publication failure fails the job but does not invalidate completed
installations or delete the host-config. Publication is not an atomic mirror
transaction: a failed transfer can leave some completed packages published,
and its retry completes the remaining work.

Project test success is not a prerequisite for publishing dependencies.
Conversely, the existence of a host-config proves only that its production
step succeeded; it does not prove that the project's tests passed or that
someone has not subsequently deleted its dependencies.

Shared configurations do not imply identical environments
---------------------------------------------------------

RADIUSS Spack Configs supplies both specs used by project CI and environments
built by the repository's own CI. Their correspondence is maintained manually.
They share machine definitions but need not have identical roots, variants or
Spack/package pins. Enforcing exact equivalence is not a rad-bat responsibility.

Migration from the earlier implementation
------------------------------------------

* Add ``/{machine}`` to the JSON's machine path template and provide
  ``LCSCHEDCLUSTER``. System-only ``spack.yaml`` and ``packages.yaml`` entry
  points were removed for the supported TOSS systems.
* ``--spack-env`` / ``RAD_BAT_SPACK_ENV`` now selects a **source** machine
  configuration. The generated project environment always belongs to the
  workspace; it is no longer an arbitrary output path.
* Move project Spack work from per-attempt ``/dev/shm`` paths to persistent
  pipeline/job-name directories. Host-config-only project builds can still
  use disposable build directories because dependency preparation is skipped.
* Use a new workspace when adopting this contract. Previous workspace layouts
  are not migrated or repaired automatically.
* Keep the JSON's project command and the host-config workflow. They continue
  to own the same handoff to the project's build/test script.

Automatic machine exploration and shared-memory preparation remain possible
future additions. Neither is part of the normal build path: missing machine
configuration currently results in an error.
