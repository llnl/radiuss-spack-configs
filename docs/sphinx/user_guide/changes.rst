.. Copyright (c) 2026, Lawrence Livermore National Security, LLC and
.. other RADIUSS Project Developers. See the top-level COPYRIGHT file.
.. SPDX-License-Identifier: (MIT)

Change recipes or dependencies
==============================

Choose the input that owns the behavior you need to change. A newer package
version normally needs newer recipes, while a new resolver or configuration
capability needs a newer Spack engine.

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
   * - Needed Spack engine capability
     - Update Spack and check compatibility with Uberenv, recipes, and
       configuration.
   * - Shared machine/toolchain change
     - Update RADIUSS Spack Configs, validate it, and adopt that configuration
       revision.

Preparing and adopting a recipe change
--------------------------------------

#. Edit the upstream recipe in a branch of ``spack/spack-packages``. Review
   existing release conditions as well as development behavior.
#. Test the candidate recipe revision from a project feature or release-staging
   branch. Record the candidate commit and the specification tested.
#. Submit the change upstream, then replace the candidate pin with the actual
   merged revision. Squash or rebase merges can change commit identities.
#. Regenerate dependencies and the host configuration, and build/test the
   project. Project ``develop`` branches and published release tags must use
   upstream-merged recipe revisions.

Use a new Uberenv prefix after engine/setup changes or when checking whether
stale preparation state explains a failure. Keep the previous prefix available
until dependent builds are no longer needed. Check :ref:`reference-ownership`
when comparing revisions, and :doc:`releases` when several projects must
converge.

.. _local-recipe-overrides:

Temporary local recipe overrides
--------------------------------

A local override is useful for a short experiment, but can hide subsequent
upstream fixes. The optional repository layout here is
``spack_repo/llnl_radiuss/repo.yaml`` with recipes under
``spack_repo/llnl_radiuss/packages/<name>/package.py``. For the canonical
integration, its Uberenv packages path is
``scripts/radiuss-spack-configs/spack_repo/llnl_radiuss/packages``.

Do not use the obsolete ``radiuss-spack-configs/packages`` path. A local
repository must contain valid metadata for the selected Spack version. Verify
which repository supplies the recipe, upstream the change, and remove the
override once its merged revision is adopted. For repository ordering, see
:ref:`essential-precedence`.
