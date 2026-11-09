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
     - Project checkout developed as ``<package>@develop`` by rad-bat
     - Source being built; ``develop`` is not a recipe-repository revision
   * - Recipe repository
     - Pinned remote repository in ``.rad-bat.json``
     - Upstream recipes and build systems used by Spack
   * - Spack
     - ``spack.commit`` in ``.rad-bat.json``
     - Package manager, including the concretizer and installer
   * - Shared configuration
     - RADIUSS Spack Configs submodule commit; ``spack.environment`` selects
       the machine environment
     - Machine settings and shared CI specifications
   * - rad-bat
     - RADIUSS Spack Configs submodule commit and project ``.rad-bat.json``
     - Host-config selection or native-Spack dependency preparation followed
       by the project build/test driver
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
   * - Project ``.rad-bat.json``
     - Project command, package name, Spack and recipe pins, machine-environment
       path, conditional spec fragments, and repository precedence
   * - ``rad_bat/`` and ``bin/rad-bat``
     - Repository-local native-Spack and maintained-host-config orchestration
   * - ``.gitlab/spack/envs/<environment>/spack.yaml``
     - Repository validation specs and ``spack.repos.builtin.commit`` recipe pin
   * - ``.gitlab/spack/envs/<environment>/pipeline.yml``
     - Spack revision and machine pipeline includes for repository CI

.. _essential-precedence:

Essential precedence rules
--------------------------

* In ``rad-bat``, ``.rad-bat.json`` records full Spack and remote repository
  commits. Repository array order defines precedence, and conditional spec
  fragments apply only when their declared environment variable is non-empty.
  See :doc:`rad_bat` for the complete schema and CI variables.
* Configuration includes, scopes, and override keys affect the effective Spack
  settings. Inspect ``spack config blame packages`` and
  ``spack config blame repos`` in the generated environment rather than
  inferring the result from one file. See `Spack configuration scopes
  <https://spack.readthedocs.io/en/latest/configuration.html>`_.
* RADIUSS Spack Configs CI selects an environment using GitLab's
  ``MY_ENV_NAME`` variable. The CI Spack checkout uses ``MY_SPACK_COMMIT`` when set,
  otherwise ``MY_SPACK_BRANCH`` (which can name a tag). A project's
  ``.rad-bat.json`` does not configure these repository-validation pipelines.
* Consumer CI combines shared jobs with project settings. Inspect the final
  merged GitLab configuration when names collide; see :doc:`../developer_workflow/ci`.

For release selection, use :doc:`../developer_workflow/releases`.

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
