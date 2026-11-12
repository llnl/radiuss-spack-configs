.. Copyright (c) 2026, Lawrence Livermore National Security, LLC and
.. other RADIUSS Project Developers. See the top-level COPYRIGHT file.
.. SPDX-License-Identifier: (MIT)

Maintain rad-bat integrations
=============================

``rad-bat`` is maintained directly in RADIUSS Spack Configs as the ``rad_bat``
standard-library Python package and ``bin/rad-bat`` entry point. Projects can
run the tool from their pinned submodule without another submodule or package
installation. RADIUSS Shared CI is not a distribution source for the tool.

The maintained contract and its rationale are in :doc:`design_choices`.
Keep the generic and project-specific boundaries explicit. ``rad-bat`` owns:

* CLI and ``.rad-bat.json`` validation;
* the pinned Spack checkout and translation of project JSON repository pins;
* Spack isolation, environments, repositories, upstreams, install trees, and
  buildcache configuration;
* dependency installation, generated host-config discovery, and safe project
  command expansion;
* nested timed GitLab sections, diagnostics, process status, and scheduler
  descriptor propagation.

The project driver owns its configure, build, install, test, benchmark, and
project-specific artifact lifecycle. Source preparation that is not represented
in the Spack DAG also remains project-owned. For example, a conditional Spack
fragment may constrain a dependency revision, while checking out a nested
project source tree belongs in that project's driver.

Native Spack lifecycle
----------------------

Spack mode never selects an executable from ``PATH``. It checks out the URL and
full commit recorded by the project, runs ``spack isolate`` in the managed
checkout, and uses native environment creation with the selected RADIUSS machine configuration. It writes the
local paths and commit-pinned remote repositories from ``.rad-bat.json`` into
that intermediate environment in configured precedence order. Spack owns the
package-repository clones and checkouts, including monorepo subdirectory
selection. Developers continue to edit their pins in the JSON. On first preparation it then:

#. adds the explicit ``<package>@develop`` root and project spec fragment;
#. runs ``spack develop --no-clone`` against the source checkout;
#. concretizes the environment;
#. installs through ``spack.until`` (default ``initconfig``); and
#. requires exactly one new or changed top-level ``.cmake`` file.

``spack isolate`` modifies its checkout, which belongs to the persistent
scenario workspace. A retry reuses the concrete environment and skips
installation when the retained host-config already records success. Updating a
Spack pin must not remove installations still referenced by maintained host
configurations.

Storage and dependency reuse
----------------------------

Consumer projects choose their storage roots. Keep persistent scenario work, durable
install trees, and exported host-config artifacts distinct. Use immutable
install-tree generations so committed host configurations retain valid
absolute paths. Shared refresh jobs serialize writes with
``.rad-bat-write.lock`` and use a ``0002`` umask; host-config-mode jobs only
read their selected generation.

Filesystem upstreams are the primary cross-generation reuse mechanism. An
optional filesystem or OCI buildcache may also supply dependencies. Reading a
buildcache does not authorize publication: the push flag is required, and the
command uses Spack's dependency-only publication. Credential configuration
records environment-variable names rather than secret values so diagnostics
and reproducers do not expose credentials.

Shared CI boundary
------------------

Machine components treat ``job_cmd`` as opaque and supply the allocation.
rad-bat loads the documented ``MODULE_LIST`` before dependencies or the project
command; all children inherit that environment. A component may also need
modules before launching its scheduler command, but rad-bat does not depend on
that for its own module loading. The project owns specs, resource flags,
storage locations and its driver.

The resulting responsibility split is:

.. code-block:: text

   CI / Jacamar: allocate resources -> launch job_cmd -> await completion
   rad-bat: load modules -> prepare/resume dependencies -> invoke project driver
   project driver: configure -> build -> install -> test

Scheduler descriptors and MPI tests
-----------------------------------

Python subprocesses close non-standard file descriptors by default. Retaining
an environment variable such as ``PMI_FD`` while closing the corresponding
descriptor leaves an MPI-aware child with an invalid scheduler connection.
Before invoking children, ``rad-bat`` validates ``PMI_FD`` with ``fstat()`` and
passes an open descriptor explicitly. Invalid or already closed values are
ignored. This preserves the earlier shell inheritance behavior; it does not
allocate resources or choose an MPI launcher.

BLT and the project continue to choose whether an individual test runs
directly, through ``mpirun``, or through a scheduler launcher. Do not add an
unconditional nested ``srun`` or Flux allocation in ``rad-bat``. Some Project
CI layouts already run a job step inside a shared allocation, and another
scheduler level may be unsupported. Project resource variables and cluster
policy remain authoritative.

Validation
----------

Run ``python3 -m unittest discover -s tests -p 'test_*.py'`` after changes.
The suite covers schema and CLI validation, mode inference, whole-argument
substitution, pinned Git checkout behavior, scheduler descriptor inheritance,
conditional spec fragments, and mocked host-config and native-Spack workflows.
For workflow changes, also validate representative consumer jobs in both modes
on affected CPU and accelerator platforms. Confirm that host-config mode never
starts Spack, refresh artifacts use the requested stable names, project drivers
run independently, and buildcache writes remain explicitly opt-in.

Shared environment workflow
---------------------------

The ``env`` workflow shares pinned-checkout, isolation, storage configuration,
publication and section-logging helpers with the project workflows. Its prepared
state is persistent for retries within the same pipeline/job workspace. A new
job workspace prepares new inputs; no file hashes or automatic invalidation
are maintained. Upstreams and read mirrors are preserved, with autopush disabled.
Package repositories declared in the environment are
resolved by Spack and frozen to shared paths before installation workers start.

``rad_bat.environment`` owns preparation, installation and success-gated
publication. ``rad_bat.allocation`` only launches, waits and signals workers in
an existing allocation; Jacamar owns the allocation lifecycle. Each worker uses
Spack's prefix locks and its own POSIX jobserver. The workspace lock protects
coordinator state and is not an install-tree lock. The project install-tree lock remains pending its separate review. Project
retries now preserve the concrete environment and retained host-config.

``rad_bat.spack_helpers`` runs under the pinned Spack interpreter with
``spack python -m``, using native environment creation and configuration APIs. ``rad_bat.report`` only reads saved artifacts and is optional;
keep it independent of installation and publication decisions. The RADIUSS CI
adapter maps machine/storage variables to the tool and collects artifacts.
