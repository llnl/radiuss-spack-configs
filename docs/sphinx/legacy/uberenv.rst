.. Copyright (c) 2026, Lawrence Livermore National Security, LLC and
.. other RADIUSS Project Developers. See the top-level COPYRIGHT file.
.. SPDX-License-Identifier: (MIT)

.. _use_spack-label:
.. _use-spack-to-install-dependencies-and-configure-the-project-build:
.. _use-uberenv:
.. _why-spack:
.. _end-product:

Legacy Uberenv workflow
=======================

.. warning::

   Uberenv is a legacy workflow. New integrations should use
   :doc:`rad-bat <../developer_workflow/rad_bat>`, the supported workflow
   described by the main documentation. This page is retained for projects
   that have not migrated yet.

Prepare dependencies
--------------------

An Uberenv project records its Spack and ``spack-packages`` revisions in
``.uberenv_config.json`` and commonly carries Uberenv and RADIUSS Spack Configs
as Git submodules. Start with the versions recorded by the project. From its
repository root, run the following in a compute allocation on the LC machine:

.. code-block:: bash

   git submodule update --init --recursive
   python3 scripts/uberenv/uberenv.py --spec="%gcc" --prefix="${PWD}/uberenv_libs"

``--spec`` takes a Spack spec without the project name. To reproduce a CI
build, use the compiler version, variants, and dependency constraints from the
CI job. For example, list shared Dane specs from a RADIUSS Spack Configs
submodule with:

.. code-block:: bash

   git -C scripts/radiuss-spack-configs grep SPEC gitlab/radiuss-jobs/dane.yml

Substitute the project's ``PROJECT_DANE_VARIANTS`` and
``PROJECT_DANE_DEPS`` values before using a shared spec. Uberenv configures
Spack, concretizes the spec, installs dependencies, and runs the project recipe
through ``initconfig``. Use the generated ``.cmake`` file shown in the output
to :doc:`build and test <../developer_workflow/build_and_test>`.

Some projects keep dependency preparation in a script. For example, a legacy
RAJA checkout can accept ``SPEC`` without the project name:

.. code-block:: bash

   SPEC="%gcc" ./scripts/gitlab/build_and_test.sh

RAJAPerf obtains Uberenv and RADIUSS Spack Configs through its ``tpl/RAJA``
submodule; its legacy build/test script calls that nested checkout with
RAJAPerf's own ``.uberenv_config.json``.

.. _uberenv-guide:
.. _main-steps:
.. _some-options:

Configure an Uberenv project
----------------------------

Add Uberenv at ``scripts/uberenv`` and RADIUSS Spack Configs at
``scripts/radiuss-spack-configs`` as submodules. Select compatible revisions
following :doc:`../maintainer_guide/baselines` and commit the submodule
references. This JSON template shows the main settings:

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

In this layout ``package_source_dir`` is relative to the Uberenv script, so
``../..`` selects the project source. ``spack_configs_path`` and
``spack_packages_path`` are relative to the directory containing
``.uberenv_config.json``. ``package_version`` determines which recipe
conditions apply without changing the Git checkout. Setting
``package_final_phase`` to ``initconfig`` stops before the project build.

``spack_commit`` takes precedence over ``spack_branch``.
``spack_packages_commit`` takes precedence over ``spack_packages_branch``,
which takes precedence over ``spack_packages_tag``. Remove obsolete selectors
when changing strategy. Updating a package version normally requires a newer
``spack_packages_commit``, but not necessarily a newer Spack revision.

For all options, consult the `Uberenv guide
<https://uberenv.readthedocs.io/en/latest/>`_.

.. _get-the-shared-spack-configuration:

Use shared machine configuration
--------------------------------

``spack_configs_path`` tells Uberenv where to find RADIUSS Spack Configs.
Uberenv selects configuration files for the platform and machine, using LC's
``SYS_TYPE`` as part of its detection. Check the selected paths printed by the
tool. RADIUSS Spack Configs supplies ``spack.yaml``, ``config.yaml``, and
``packages.yaml`` files; see :doc:`../maintainer_guide/index` for their
maintenance and :doc:`../reference/index` for current responsibilities.

.. _generate-config-file:
.. _setup-your-spack-package-to-generate-a-configuration-file:
.. _cmake-projects-spack-cachedcmakepackage:
.. _non-cmake-projects-custom-implementation:

Generate a host configuration
-----------------------------

The upstream recipe should inherit from ``CachedCMakePackage`` and generate
compiler paths, dependency paths, flags, and project options in its
``initconfig`` phase. See `Spack's CachedCMakePackage documentation
<https://spack.readthedocs.io/en/latest/build_systems/cachedcmakepackage.html>`_.
An equivalent generated configuration and project-specific driver are needed
for a non-CMake project.

.. _reference-used-by-uberenv-to-clone-spack:
.. _update_spack_uberenv_rsc:
.. _update-spack-uberenv-or-radiuss-spack-configs:
.. _updating-uberenv:

Update or troubleshoot the legacy stack
----------------------------------------

When changing Spack, recipes, or Uberenv, verify that their revisions remain
compatible and retry with a new ``--prefix`` to exclude stale setup files.
Compare project commits, recursive submodule status, the references in
``.uberenv_config.json``, machine configuration, expanded spec, and generated
host configuration. Keep an old prefix while host configurations still refer
to dependencies installed there.

To test a project-local recipe, add its packages directory:

.. code-block:: json

   "spack_packages_path": "scripts/spack_repo/my_project/packages"

This setting does not pin the upstream recipe repository. Each ``packages``
directory requires ``repo.yaml`` in its parent. With multiple local
repositories, the rightmost has highest priority. Keep local overrides
temporary because they can hide upstream fixes.

Release-version semantics
-------------------------

For development builds, ``package_version: develop`` selects the recipe's
development conditions. To validate a planned release, set ``package_version``
to its numeric version so Spack applies the corresponding conditions. Use
local source before publication, then verify that Spack fetches and builds the
released source using its final ``version(...)`` metadata.
