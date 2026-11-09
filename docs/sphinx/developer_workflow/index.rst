.. Copyright (c) 2026, Lawrence Livermore National Security, LLC and
.. other RADIUSS Project Developers. See the top-level COPYRIGHT file.
.. SPDX-License-Identifier: (MIT)

.. _User Guide:

Understand the components
=========================

The recommended workflow is **specification → dependency preparation →
generated host configuration → repeated CMake builds and tests**. This guide
uses ``rad-bat`` (RADIUSS Builds And Tests), distributed by a project's
RADIUSS Spack Configs checkout at ``scripts/radiuss-spack-configs``.

.. graphviz:: /figures/components.dot
   :align: center
   :caption: RADIUSS Spack Configs provides rad-bat, which prepares a host configuration and invokes the project's build/test driver.
   :alt: The project owns its rad-bat settings and Python build/test driver. RADIUSS Spack Configs provides rad-bat and machine settings. rad-bat uses Spack and package recipes to select or generate a host configuration, then invokes the project driver.

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
* ``rad-bat`` reuses a maintained host configuration or drives pinned native
  Spack from ``.rad-bat.json``. The recipe's ``initconfig`` phase produces the
  host configuration that CMake consumes. Both paths then call the project's
  independently runnable build/test driver.
* RADIUSS Shared CI supplies GitLab execution components. Projects provide the
  command that prepares dependencies, builds their checkout, and runs tests.

Developers can use a package repository inside their project to test recipe
changes. Keep these overrides temporary to avoid maintaining duplicate recipes;
the preferred approach is a pull request in ``spack/spack-packages``. See
:ref:`local-recipe-overrides`.

Start by :doc:`running rad-bat <rad_bat>`, then :doc:`build and test
<build_and_test>`. Later sections cover :doc:`recipe and dependency changes
<changes>`, :doc:`release coordination <releases>`, and :doc:`CI integration
<ci>`.

See :doc:`../reference/index` for file ownership and reference selection.
