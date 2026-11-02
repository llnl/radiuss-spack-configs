.. Copyright (c) 2026, Lawrence Livermore National Security, LLC and
.. other RADIUSS Project Developers. See the top-level COPYRIGHT file.
.. SPDX-License-Identifier: (MIT)

.. _use_spack-label:
.. _use-spack-to-install-dependencies-and-configure-the-project-build:

Prepare dependencies
====================

Use the project checkout's tested pins first. RAJA's integration supplies
``.uberenv_config.json`` and the submodules described in :doc:`index`. Run from
the RAJA repository root and use a compute allocation appropriate to the LC
machine for dependency builds.

.. code-block:: bash

   git submodule update --init --recursive
   python3 scripts/uberenv/uberenv.py --spec="%gcc" --prefix="${PWD}/uberenv_libs"

``--spec`` takes a Spack specification **without the project name**. Here
``%gcc`` selects GCC; for a reproducible comparison use the complete compiler,
version, variants, and dependency constraints from a supported shared job for
your machine. List those specs from the configuration checkout:

.. code-block:: bash

   git -C scripts/radiuss-spack-configs grep SPEC gitlab/radiuss-jobs/dane.yml

Resolve any ``PROJECT_DANE_VARIANTS`` and ``PROJECT_DANE_DEPS`` hooks using the
project's CI settings before reproducing a job. A spec for one machine is not
necessarily valid on another.

Uberenv configures Spack, prepares dependencies, and runs the project's recipe
through ``initconfig``. Note the generated ``.cmake`` filename in the output,
then continue to :doc:`build_and_test`. Keep the selected spec and input
revisions with your build results.

.. note::

   For an indirect submodule, initialize recursively and use the paths and JSON
   configuration owned by the enclosing integration. Update that enclosing
   revision when adopting a change; adding another Uberenv checkout is not
   necessary.

.. _uberenv-guide:
.. _main-steps:

Integrating the same workflow in a project
------------------------------------------

Add Uberenv and RADIUSS Spack Configs as submodules at the canonical paths,
select validated revisions, and commit those selections in the project. The
following JSON is a **template** for this layout, not a current recommended
baseline. Replace both placeholder hashes with full validated commit hashes
and set the package name for your project before running it.

.. code-block:: json

   {
     "package_name": "raja",
     "package_version": "develop",
     "package_final_phase": "initconfig",
     "package_source_dir": "../..",
     "spack_url": "https://github.com/spack/spack.git",
     "spack_commit": "<validated-spack-commit>",
     "spack_packages_url": "https://github.com/spack/spack-packages.git",
     "spack_packages_commit": "<validated-spack-packages-commit>",
     "spack_configs_path": "scripts/radiuss-spack-configs",
     "spack_setup_clingo": false
   }

In this layout ``package_source_dir`` is relative to the Uberenv script
location, so ``../..`` selects the project checkout. Configuration and local
recipe paths are relative to the project JSON location. ``package_version``
selects the recipe's version-dependent behavior for that checkout; it does
not change your Git branch or pin the recipe repository.

The example uses upstream recipes. Add ``spack_packages_path`` only if an
intentional local repository is needed; see :ref:`local-recipe-overrides`.
For all Uberenv options, consult the `Uberenv guide
<https://uberenv.readthedocs.io/en/latest/>`_.

.. _get-the-shared-spack-configuration:

Shared machine configuration
----------------------------

``spack_configs_path`` points to the configuration checkout. Uberenv selects
platform/machine configuration using its platform detection, including LC's
``SYS_TYPE``. Confirm the selected paths in its output. The repository contains
platform and machine ``spack.yaml``, ``config.yaml``, and ``packages.yaml``
files; compiler externals and named toolchains are defined in
``packages.yaml``. See :doc:`../developer_guide/index` for maintenance and
:doc:`../reference/index` for file responsibilities.

.. _generate-config-file:

Generate a host configuration from a recipe
-------------------------------------------

The upstream recipe should inherit from ``CachedCMakePackage`` and generate
compiler paths, dependency paths, build flags, and project options in its
``initconfig`` phase. Setting ``package_final_phase`` to ``initconfig`` stops
before the project build, leaving that build under the developer's control.
See `Spack's CachedCMakePackage documentation
<https://spack.readthedocs.io/en/latest/build_systems/cachedcmakepackage.html>`_.

For a non-CMake project, an equivalent generated configuration and build driver
need a project-specific implementation. The workflow here assumes CMake.
