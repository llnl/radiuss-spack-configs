.. Copyright (c) 2026, Lawrence Livermore National Security, LLC and
.. other RADIUSS Project Developers. See the top-level COPYRIGHT file.
.. SPDX-License-Identifier: (MIT)

.. _User Guide:

Understand the components
=========================

The recommended workflow is **specification → dependency preparation →
generated host configuration → repeated CMake builds and tests**. This guide
uses RAJA as an example: its Uberenv submodule is at ``scripts/uberenv``,
and its RADIUSS Spack Configs submodule is at ``scripts/radiuss-spack-configs``.

.. graphviz:: /figures/components.dot
   :align: center
   :caption: Components that turn project requirements into a generated host configuration.
   :alt: Uberenv configures Spack with the project's selected package recipes and machine settings. Spack concretizes the spec, installs dependencies, and generates a CMake host configuration.

Responsibilities
----------------

* The project repository contains source code, tests, and the selected
  versions of its build tools.
* Spack, developed in `spack/spack <https://github.com/spack/spack>`_, is a
  package manager. Its concretizer turns a spec into a concrete dependency
  graph, which Spack then installs.
* `spack/spack-packages <https://github.com/spack/spack-packages>`_ owns the
  upstream ``package.py`` recipes and build system implementations, including
  ``CachedCMakePackage``.
* RADIUSS Spack Configs provides shared machine configuration and CI specs.
* Uberenv sets up and drives Spack using the project's
  ``.uberenv_config.json``. The recipe's ``initconfig`` phase produces the host
  configuration that CMake consumes.
* RADIUSS Shared CI supplies GitLab execution components. Projects provide the
  command that prepares dependencies, builds their checkout, and runs tests.

Developers can use a package repository inside their project to test recipe
changes. Keep these overrides temporary to avoid maintaining duplicate recipes;
the preferred approach is a pull request in ``spack/spack-packages``. See
:ref:`local-recipe-overrides`.

Next, :doc:`prepare dependencies <use_spack>` and :doc:`build and test
<build_and_test>`. Later sections cover :doc:`recipe and dependency changes
<changes>`, :doc:`release coordination <releases>`, and :doc:`CI integration <ci>`.

See :doc:`../reference/index` for file ownership and reference selection.
