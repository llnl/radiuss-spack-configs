.. Copyright (c) 2026, Lawrence Livermore National Security, LLC and
.. other RADIUSS Project Developers. See the top-level COPYRIGHT file.
.. SPDX-License-Identifier: (MIT)

Run rad-bat
===========

``rad-bat`` (RADIUSS Builds And Tests) is the repository-local Python tool for
projects that have adopted a maintained-host-configuration workflow. It either
uses an existing host configuration without starting Spack, or prepares
dependencies with pinned native Spack and retains the generated configuration.
Both paths invoke the same project-owned build/test command.

The tool is distributed by RADIUSS Spack Configs. A project that carries this
repository at ``scripts/radiuss-spack-configs`` runs:

.. code-block:: bash

   scripts/radiuss-spack-configs/bin/rad-bat --help

No installation is required. The runtime uses Python 3.8 or newer and the
standard library. Use the revisions and workflow committed by the project.

Choose a mode
-------------

.. graphviz:: /figures/rad-bat-modes.dot
   :align: center
   :caption: Both rad-bat modes produce the host configuration consumed by the same project driver.
   :alt: Inputs select either an existing host configuration or pinned native Spack. Native Spack generates a host configuration. Both paths invoke the project build and test driver.

``host-config`` is the fast path. It validates the selected file and runs the
project command without invoking Spack:

.. code-block:: bash

   scripts/radiuss-spack-configs/bin/rad-bat host-config \
     --host-config host-configs/dane-gcc.cmake \
     --work-dir /dev/shm/rad-bat-source-build \
     --jobs 16

``spack`` is the explicit dependency-refresh path. The spec contains the
project variants, compiler, and dependency constraints without the project
name; ``rad-bat`` adds the configured project package at ``@develop``:

.. code-block:: bash

   scripts/radiuss-spack-configs/bin/rad-bat spack \
     --spec "+openmp %gcc@13.3.1" \
     --work-dir /dev/shm/rad-bat-refresh \
     --install-tree /usr/workspace/$USER/my-project/deps/generation-1 \
     --output-dir generated-host-configs \
     --host-config-name dane-gcc.cmake \
     --jobs 16

This mode checks out the recorded Spack and remote package-repository commits,
copies the selected machine environment, registers repositories, concretizes,
and installs through the recipe's ``initconfig`` phase. It retains the one
newly generated top-level ``.cmake`` file before running the project command.

Manage work and dependencies
----------------------------

Treat ``--work-dir`` as disposable. It contains the managed Spack checkout,
isolation state, and generated environment. ``--install-tree`` is the durable
dependency prefix; CI should put it in project-owned persistent storage and
use an immutable generation while committed host configurations still refer to
it. ``--output-dir`` is a separate artifact directory for generated host
configurations.

Multiple refresh jobs may share an install tree. ``rad-bat`` serializes writes
with a filesystem lock and a group-writable umask. Optional ``--upstream`` and
``--buildcache`` inputs provide dependency reuse. Reading a buildcache never
publishes to it; publication requires ``--push-to-buildcache`` and includes
dependencies only.

Run the project driver
----------------------

The project records its default command in ``.rad-bat.json``. That command is
an argument array and can use the whole-argument placeholders
``{host_config}``, ``{work_dir}``, ``{source}``, and ``{jobs}``. Arguments after
``--`` replace the configured command, which is useful when developing or
debugging the project driver:

.. code-block:: bash

   scripts/radiuss-spack-configs/bin/rad-bat host-config \
     --host-config host-configs/dane-gcc.cmake \
     -- python3 scripts/gitlab/build_and_test.py \
       --host-config /absolute/path/to/dane-gcc.cmake

The project driver owns configure, build, install, test, benchmark, and
project-specific artifacts. It should also run independently from ``rad-bat``.
See :doc:`../reference/rad_bat` for the complete command and configuration
contract, and :doc:`ci` for the maintained-host-configuration CI workflow.

Install a complete environment
------------------------------

For an existing ``spack.yaml``, use the explicit ``rad-bat env`` workflow.
It prepares pinned Spack, retains the concrete environment and installations
across retries, and publishes only after successful installation when requested.
It defaults to one node and can run native installers on multiple nodes of an
existing allocation. See :doc:`../reference/rad_bat` for its command line and
:doc:`../ci_implementation/parallel` for the environment CI pilot.
