.. Copyright (c) 2026, Lawrence Livermore National Security, LLC and
.. other RADIUSS Project Developers. See the top-level COPYRIGHT file.
.. SPDX-License-Identifier: (MIT)

.. _User Guide:

Understand the components
=========================

The recommended workflow is **specification → dependency preparation →
generated host configuration → repeated CMake builds and tests**. This guide
uses RAJA, with Uberenv at ``scripts/uberenv`` and RADIUSS Spack Configs at
``scripts/radiuss-spack-configs``, as its canonical integration example.

Responsibilities
----------------

* The project repository owns source code, tests, and the revisions it adopts.
* ``spack/spack`` provides the engine that resolves specifications and drives
  installations.
* ``spack/spack-packages`` owns the upstream ``package.py`` recipes and build
  system implementations, including ``CachedCMakePackage``.
* RADIUSS Spack Configs owns shared machine configuration and CI specifications.
  Its optional recipe repository is for temporary testing, not the canonical
  home of RADIUSS recipes.
* Uberenv sets up and drives Spack using the project's
  ``.uberenv_config.json``. The recipe's ``initconfig`` phase produces the host
  configuration that CMake consumes.
* RADIUSS Shared CI supplies GitLab execution components. Projects provide the
  command that prepares dependencies, builds their checkout, and runs tests.

Next, :doc:`prepare dependencies <use_spack>` and :doc:`build and test
<build_and_test>`. Use :doc:`changes` when an input changes, :doc:`releases`
for coordinated releases, and :doc:`ci` to run the same workflow in CI.

See :doc:`../reference/index` for file ownership and reference selection.
