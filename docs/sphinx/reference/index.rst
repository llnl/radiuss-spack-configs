.. Copyright (c) 2026, Lawrence Livermore National Security, LLC and
.. other RADIUSS Project Developers. See the top-level COPYRIGHT file.
.. SPDX-License-Identifier: (MIT)

Terminology and configuration responsibilities
==============================================

.. _reference-ownership:

References and their owners
---------------------------

.. list-table:: Independently selected inputs
   :header-rows: 1
   :widths: 25 40 35

   * - Input
     - Consumer selection
     - Meaning
   * - Project source
     - Project checkout; ``package_version`` selects applicable recipe conditions
     - Source being built; ``develop`` is not a recipe-repository revision
   * - Recipe repository
     - ``spack_packages_commit`` in ``.uberenv_config.json``
     - Upstream recipes and build systems used by Spack
   * - Spack
     - ``spack_commit`` or ``spack_branch`` in ``.uberenv_config.json``
     - Package manager, including the concretizer and installer
   * - Shared configuration
     - RADIUSS Spack Configs submodule commit; ``spack_configs_path`` locates
       the checkout
     - Machine settings and shared CI specifications
   * - Uberenv
     - Uberenv submodule commit
     - Setup and dependency preparation driver
   * - Shared CI
     - Versioned GitLab component reference in the consumer pipeline
     - CI execution, allocation, and reporting infrastructure
   * - Generated host configuration
     - Explicit ``.cmake`` file passed to ``cmake -C``
     - Output tied to a specification, machine, and dependency installation

The generated host configuration is an initial CMake cache script, not the
build directory's ``CMakeCache.txt``. Keep the compiler and dependency
installations referenced by the host configuration available at the recorded
paths.

File responsibilities
---------------------

.. list-table:: Where changes belong
   :header-rows: 1
   :widths: 48 52

   * - Location
     - Responsibility
   * - ``spack-packages/repos/spack_repo/builtin/packages/<name>/package.py``
     - Upstream versions, variants, dependencies, and build behavior;
       package directory names replace hyphens with underscores
   * - ``spack_repo/llnl_radiuss/repo.yaml`` and adjacent ``packages/``
     - Local recipe testing in RADIUSS Spack Configs
   * - Platform/machine ``spack.yaml``
     - Environment settings and configuration includes
   * - Platform/machine ``packages.yaml``
     - Externals, compiler executables, package requirements, providers,
       and named toolchains
   * - ``config.yaml`` and ``modules.yaml``
     - Spack storage/general settings and module generation settings
   * - ``gitlab/radiuss-jobs/<machine>.yml``
     - Shared consumer jobs and ``SPEC`` variable hooks
   * - ``.gitlab/spack/envs/<environment>/spack.yaml``
     - Repository validation specs and ``spack.repos.builtin.commit`` recipe pin
   * - ``.gitlab/spack/envs/<environment>/pipeline.yml``
     - Spack revision and machine pipeline includes for repository CI

.. _essential-precedence:

Essential precedence rules
--------------------------

* In Uberenv, ``spack_commit`` takes precedence over ``spack_branch``.
  ``spack_packages_commit`` takes precedence over ``spack_packages_branch``,
  which takes precedence over ``spack_packages_tag``. Remove obsolete selectors
  when changing selection strategy. To use a new package version, normally
  update ``spack_packages_commit``; Spack itself may not need an update.
* ``spack_packages_path`` selects optional local recipe directories; it does
  not pin the upstream recipe repository. Each ``packages`` directory needs
  a ``repo.yaml`` in its parent directory. In a list, the rightmost local
  repository has highest priority; local recipes can hide upstream fixes.
* Configuration includes, scopes, and override keys affect the effective Spack
  settings. Inspect ``spack config blame packages`` and
  ``spack config blame repos`` in the generated environment rather than
  inferring the result from one file. See `Spack configuration scopes
  <https://spack.readthedocs.io/en/latest/configuration.html>`_.
* RADIUSS Spack Configs CI selects an environment using GitLab's
  ``MY_ENV_NAME`` variable. The CI Spack checkout uses ``MY_SPACK_COMMIT`` when set,
  otherwise ``MY_SPACK_BRANCH`` (which can name a tag). A project's
  ``.uberenv_config.json`` does not configure these pipelines.
* Consumer CI combines shared jobs with project settings. Inspect the final
  merged GitLab configuration when names collide; see :doc:`../user_guide/ci`.

See the `Uberenv guide <https://uberenv.readthedocs.io/en/latest/>`_ for setup
options and their mechanics. For release selection, use
:doc:`../user_guide/releases`.

Figure vocabulary
-----------------

Figures use the same shapes throughout: folders are Git repositories, a note
labeled ``package.py`` is a recipe, tabbed documents are configuration inputs,
small revision badges are pins, rounded boxes are actions, and parallelograms
are generated outputs or storage artifacts.

Solid arrows show execution or output flow. Dashed arrows with open heads show
input or dependency relationships. Dotted arrows with V-shaped heads show
adoption of a selected revision. Labels carry the meaning without relying on
color.
