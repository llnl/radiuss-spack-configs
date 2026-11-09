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
     - Update the pinned remote repository commit in ``.rad-bat.json`` to a
       validated recipe revision containing the required package version.
   * - Needed Spack capability
     - Update Spack and check compatibility with the selected preparation
       driver, ``spack-packages``, and RADIUSS Spack Configs.
   * - Shared machine/toolchain change
     - Update RADIUSS Spack Configs, validate the changed configuration, and
       adopt the tested revision.

Preparing and adopting a recipe change
--------------------------------------

#. Edit the upstream recipe in a branch of ``spack/spack-packages``. Review
   existing release conditions as well as development behavior.
#. Test the candidate recipe revision from a project feature or release-staging
   branch. Record the candidate commit and the specification tested.
#. Open a pull request in ``spack/spack-packages``, then update its remote
   repository ``commit`` in ``.rad-bat.json`` to the actual merged revision.
   Squash or rebase merges can change commit identities.
#. Rerun ``rad-bat spack`` to install dependencies and generate the host
   configuration, then build and test the project. Project ``develop``
   branches and release tags must use upstream-merged recipe revisions.

Use a new rad-bat work/install generation after updating Spack, or to check
whether an existing installation causes a failure. Keep the old directory
while other builds still use dependencies installed there. See
:ref:`reference-ownership` for the revisions to compare and :doc:`releases` for updates across projects.

.. _local-recipe-overrides:

Temporary local recipe overrides
--------------------------------

To test a recipe locally, create a Spack package repository inside your project.
For example, use ``scripts/spack_repo/my_project/repo.yaml`` and
``scripts/spack_repo/my_project/packages/<name>/package.py``, with repository
metadata matching your Spack version. Add the repository root as a local
``path`` entry in ``spack.repositories``:

.. code-block:: json

   "repositories": [
     {"path": "scripts/spack_repo/my_project"},
     {
       "url": "https://github.com/spack/spack-packages.git",
       "commit": "<validated-spack-packages-commit>",
       "subdirectory": "repos/spack_repo/builtin"
     }
   ]

See :doc:`../reference/rad_bat` for the complete schema. Confirm that Spack
uses the local recipe when rerunning ``rad-bat spack``. Local recipes can hide
upstream fixes and create a second source of truth, so keep this arrangement
temporary. Prefer a pull request in ``spack/spack-packages``; once merged,
update the pinned recipe commit and remove the local override. See
:ref:`essential-precedence` for repository ordering.
