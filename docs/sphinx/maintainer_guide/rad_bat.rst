.. Copyright (c) 2026, Lawrence Livermore National Security, LLC and
.. other RADIUSS Project Developers. See the top-level COPYRIGHT file.
.. SPDX-License-Identifier: (MIT)

Maintain rad-bat integrations
=============================

``rad-bat`` is maintained directly in RADIUSS Spack Configs as the ``rad_bat``
standard-library Python package and ``bin/rad-bat`` entry point. Projects can
run the tool from their pinned submodule without another submodule or package
installation. RADIUSS Shared CI is not a distribution source for the tool.

Keep the generic and project-specific boundaries explicit. ``rad-bat`` owns:

* CLI and ``.rad-bat.json`` validation;
* pinned Spack and package-repository checkouts;
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
checkout, copies the selected RADIUSS machine environment, and registers local
or commit-pinned remote repositories in configured precedence order. It then:

#. adds the explicit ``<package>@develop`` root and project spec fragment;
#. runs ``spack develop --no-clone`` against the source checkout;
#. concretizes the environment;
#. installs through ``initconfig``; and
#. requires exactly one new or changed top-level ``.cmake`` file.

``spack isolate`` modifies its checkout, so the checkout belongs in disposable
tool-managed work rather than the persistent dependency prefix. Updating a
Spack pin must not remove installations still referenced by maintained host
configurations.

Storage and dependency reuse
----------------------------

Consumer projects choose their storage roots. Keep disposable work, durable
install trees, and generated host-config artifacts distinct. Use immutable
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

Do not add a rad-bat-specific GitLab component. Machine components continue to
treat ``job_cmd`` as opaque. They initialize and load ``MODULE_LIST`` in the
submitting shell before ``srun`` or ``flux batch`` and print a reproducer with
the equivalent setup. The project supplies ``bin/rad-bat`` as ``job_cmd``,
places the submodule root on ``PYTHONPATH`` when required by scheduler spooling,
and owns specs, resource flags, storage locations, and the project driver.

The resulting responsibility split is:

.. code-block:: text

   RADIUSS Shared CI:
       load modules -> print reproducer -> launch opaque job_cmd

   rad-bat:
       select workflow -> prepare or reuse dependencies -> invoke project driver

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
