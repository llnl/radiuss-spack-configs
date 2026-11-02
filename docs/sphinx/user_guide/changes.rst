.. Copyright (c) 2026, Lawrence Livermore National Security, LLC and
.. other RADIUSS Project Developers. See the top-level COPYRIGHT file.
.. SPDX-License-Identifier: (MIT)

Change recipes or dependencies
==============================

Update the component responsible for the change. A new package version usually
requires newer recipes in ``spack-packages``. New concretizer features or
configuration syntax may require a newer Spack version.

.. list-table:: What to update
   :header-rows: 1
   :widths: 32 68

   * - Change
     - Action
   * - Ordinary source edit
     - Rebuild and test using the existing dependencies and host configuration.
   * - Recipe fix, dependency requirement, or build variant
     - Update the recipe as needed, adopt the appropriate recipe revision, and
       regenerate the configuration.
   * - Needed package version
     - Update ``spack_packages_commit`` to a validated revision containing it.
   * - Needed Spack capability
     - Update Spack and check compatibility with Uberenv, ``spack-packages``,
       and RADIUSS Spack Configs.
   * - Shared machine/toolchain change
     - Update RADIUSS Spack Configs, validate it, and adopt that configuration
       revision.

Preparing and adopting a recipe change
--------------------------------------

#. Edit the upstream recipe in a branch of ``spack/spack-packages``. Review
   existing release conditions as well as development behavior.
#. Test the candidate recipe revision from a project feature or release-staging
   branch. Record the candidate commit and the specification tested.
#. Open a pull request in ``spack/spack-packages``, then update
   ``spack_packages_commit`` to the actual merged revision. Squash or rebase
   merges can change commit identities.
#. Rerun Uberenv to install dependencies and generate the host configuration,
   then build and test the project. Project ``develop`` branches and release
   tags must use upstream-merged recipe revisions.

Use a new ``--prefix`` directory after updating Spack or Uberenv, or to check
whether an existing installation causes a failure. Keep the old directory
while other builds still use its dependencies. See :ref:`reference-ownership`
for the revisions to compare and :doc:`releases` for updates across projects.

.. _local-recipe-overrides:

Temporary local recipe overrides
--------------------------------

To test a recipe locally, create a Spack package repository inside your project.
For example, use ``scripts/spack_repo/my_project/repo.yaml`` and
``scripts/spack_repo/my_project/packages/<name>/package.py``, with repository
metadata matching your Spack version. In the project's ``.uberenv_config.json``,
add:

.. code-block:: json

   "spack_packages_path": "scripts/spack_repo/my_project/packages"

Confirm that Spack uses your local recipe when you rerun Uberenv. Local recipes
can hide upstream fixes and create a second source of truth, so keep this
arrangement temporary. Prefer a pull request in ``spack/spack-packages``; once
merged, update ``spack_packages_commit`` and remove the local override. See
:ref:`essential-precedence` for repository ordering.
