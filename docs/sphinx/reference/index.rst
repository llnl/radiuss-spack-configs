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
     - Project checkout; ``package_version`` supplies recipe version semantics
     - Source being built; ``develop`` is not a recipe-repository revision
   * - Recipe repository
     - ``spack_packages_commit`` in ``.uberenv_config.json``
     - Upstream recipes and build systems used by Spack
   * - Spack engine
     - ``spack_commit`` or ``spack_branch`` in that JSON
     - Resolver, configuration parser, and installation engine
   * - Shared configuration
     - RADIUSS Spack Configs submodule commit; ``spack_configs_path`` locates it
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
build directory's ``CMakeCache.txt``. It can contain absolute compiler and
installation paths; keep the installations it references available.

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
     - Optional local testing repository; recipes should be upstreamed
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
     - Repository CI engine selection and machine pipeline includes

.. _essential-precedence:

Essential precedence rules
--------------------------

* In Uberenv, ``spack_commit`` takes precedence over ``spack_branch``.
  ``spack_packages_commit`` takes precedence over ``spack_packages_branch``,
  which takes precedence over ``spack_packages_tag``. Remove obsolete selectors
  when changing selection strategy. A package-version need normally changes
  the recipe pin, not the engine pin.
* ``spack_packages_path`` selects optional local recipe directories; it does
  not pin the upstream recipe repository. Each ``packages`` directory needs
  an adjacent parent ``repo.yaml``. In a list, the rightmost local repository
  has highest priority; local recipes can hide upstream fixes.
* Configuration includes, scopes, and override keys affect the effective Spack
  settings. Inspect ``spack config blame packages`` and
  ``spack config blame repos`` in the generated environment rather than
  inferring the result from one file. See `Spack configuration scopes
  <https://spack.readthedocs.io/en/latest/configuration.html>`_.
* Repository CI consumes ``MY_ENV_NAME`` supplied by GitLab. Its engine
  checkout uses ``MY_SPACK_COMMIT`` when set, otherwise ``MY_SPACK_BRANCH``
  (which can name a tag). Consumer JSON pins do not configure repository CI.
* Consumer CI combines shared jobs with project settings. Inspect the final
  merged GitLab configuration when names collide; see :doc:`../user_guide/ci`.

See the `Uberenv guide <https://uberenv.readthedocs.io/en/latest/>`_ for setup
options and their mechanics. For release selection, use
:doc:`../user_guide/releases`.
