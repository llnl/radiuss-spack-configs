.. Copyright (c) 2026, Lawrence Livermore National Security, LLC and
.. other RADIUSS Project Developers. See the top-level COPYRIGHT file.
.. SPDX-License-Identifier: (MIT)

.. _use_spack-label:
.. _use-spack-to-install-dependencies-and-configure-the-project-build:

.. _why-spack:
.. _end-product:

Prepare dependencies
====================

RAJA records its Spack and ``spack-packages`` revisions in
``.uberenv_config.json``, and its Uberenv and RADIUSS Spack Configs revisions
as Git submodules. Start with these recorded versions. From the RAJA repository
root, run the following in a compute allocation on your LC machine:

.. code-block:: bash

   git submodule update --init --recursive
   python3 scripts/uberenv/uberenv.py --spec="%gcc" --prefix="${PWD}/uberenv_libs"

``--spec`` takes a Spack spec **without the project name**. Here ``%gcc``
selects GCC. To reproduce a CI build, use its compiler version, variants, and
dependency constraints. For example, list the shared Dane specs in the
RADIUSS Spack Configs submodule:

.. code-block:: bash

   git -C scripts/radiuss-spack-configs grep SPEC gitlab/radiuss-jobs/dane.yml

Replace ``PROJECT_DANE_VARIANTS`` and ``PROJECT_DANE_DEPS`` with their values
from the project's CI settings before using a shared spec. Use specs intended
for your machine.

Uberenv configures Spack, which concretizes the spec, installs dependencies,
and runs the project recipe through ``initconfig``. Use the generated
``.cmake`` file shown in the output to :doc:`build and test <build_and_test>`.

.. note::

   RAJAPerf gets Uberenv and RADIUSS Spack Configs through its ``tpl/RAJA``
   submodule. Use RAJAPerf's build/test script: it calls that Uberenv checkout
   with RAJAPerf's own ``.uberenv_config.json``.

.. _uberenv-guide:
.. _main-steps:

Integrating the same workflow in a project
------------------------------------------

Add Uberenv at ``scripts/uberenv`` and RADIUSS Spack Configs at
``scripts/radiuss-spack-configs`` as submodules. Select compatible revisions
following :doc:`../developer_guide/baselines` and commit the submodule references.
In this JSON **template**, replace both placeholders with tested commit hashes
and set your project's Spack package name:

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
location, so ``../..`` selects the project source directory.
``spack_configs_path`` and ``spack_packages_path`` are relative to the directory
containing ``.uberenv_config.json``. ``package_version`` determines which recipe
conditions apply to the source; it does not change your Git checkout.

The example uses upstream recipes. To test a project-local recipe, add
``spack_packages_path``; see :ref:`local-recipe-overrides`.
For all Uberenv options, consult the `Uberenv guide
<https://uberenv.readthedocs.io/en/latest/>`_.

.. _get-the-shared-spack-configuration:

Shared machine configuration
----------------------------

``spack_configs_path`` tells Uberenv where to find RADIUSS Spack Configs:
``scripts/radiuss-spack-configs`` in this example. Within that directory,
Uberenv selects configuration files for the platform and machine, using LC's
``SYS_TYPE`` as part of its detection. Check the paths printed by Uberenv.

RADIUSS Spack Configs provides ``spack.yaml``, ``config.yaml``, and
``packages.yaml`` files for supported platforms and machines. Compiler
externals and named toolchains are defined in ``packages.yaml``. See
:doc:`../developer_guide/index` for maintenance and :doc:`../reference/index`
for file responsibilities.

.. _generate-config-file:

.. _setup-your-spack-package-to-generate-a-configuration-file:
.. _cmake-projects-spack-cachedcmakepackage:
.. _non-cmake-projects-custom-implementation:

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
