.. Copyright (c) 2026, Lawrence Livermore National Security, LLC and
.. other RADIUSS Project Developers. See the top-level COPYRIGHT file.
.. SPDX-License-Identifier: (MIT)

.. _user_how_to-label:
.. _how-to:

Troubleshoot and find earlier guidance
======================================

Start with the first failing command, using the same machine, spec, and
project checkout. A successful
concretization alone does not show that a project builds or passes tests.

.. list-table:: Narrow a failure
   :header-rows: 1
   :widths: 28 72

   * - Symptom
     - Next action
   * - Package version or variant unavailable
     - Check ``spack_packages_commit`` and whether a local recipe overrides
       the upstream package. Follow :doc:`changes`.
   * - Compiler/external missing or concretization fails
     - Confirm the machine and selected configuration, then inspect
       ``spack config blame packages`` and the full spec in that environment.
   * - Setup fails after updating Spack or Uberenv
     - Check that the Spack, Uberenv, and recipe revisions are compatible;
       retry with a new ``--prefix`` directory to rule out stale setup files.
   * - Host configuration missing or ambiguous
     - Check whether ``initconfig`` completed and select the intended output
       explicitly. Do not pick an arbitrary ``*.cmake`` file.
   * - CMake uses an old compiler or dependency path
     - Verify the host configuration and its installations; configure a fresh
       build directory using :doc:`build_and_test`.
   * - Compilation or tests fail
     - Reuse the generated configuration to reproduce with CMake/CTest and
       inspect the compiler or test output for the first relevant failure.
   * - Unexpected CI jobs or variants
     - Inspect GitLab's final merged configuration and project overrides;
       use :doc:`ci`.

.. _compare_ci_configs:
.. _compare-the-build-and-ci-configurations-of-two-projects:

.. _reference-used-to-import-radiuss-spack-configs:
.. _reference-used-by-uberenv-to-clone-spack:
.. _reference-used-to-import-radiuss-shared-ci:
.. _local-jobs-defined-by-the-projects:

Compare two configurations
--------------------------

Compare the project commits, ``git submodule status --recursive`` output,
Spack and recipe revisions in ``.uberenv_config.json``, machine configuration,
expanded spec, and generated host configuration. Also compare Shared CI component references, project
variables, and local job overrides. :ref:`reference-ownership` lists the owner
of each component.

Earlier how-to sections
-----------------------

The following entry points retain links from the previous guide.

.. _update_spack_uberenv_rsc:
.. _update-spack-uberenv-or-radiuss-spack-configs:
.. _updating-radiuss-spack-configs:
.. _updating-spack:
.. _updating-uberenv:
.. _choose-a-spack-reference-commit-or-branch:
.. _limiting-local-patching-of-spack-packages:

Update build infrastructure
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Use :doc:`changes` to identify the component to update and
:ref:`essential-precedence` to check which selection takes effect.

.. _shared_ci_jobs:
.. _share-jobs-between-projects-in-the-shared-ci-infrastructure:
.. _allow_job_failure:
.. _allow-failure-for-a-spec-known-to-fail:
.. _project-specific-variants-and-dependencies:
.. _list-the-spack-specs-tested:

.. _append-the-shared-jobs-to-your-local-jobs:

Shared jobs and project overrides
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Use :doc:`ci` for composition, variants, and failure exceptions, and
:doc:`use_spack` to list shared specs from **RADIUSS Spack Configs**.

.. _use-uberenv:

.. _some-options:

Run Uberenv
~~~~~~~~~~~

Follow :doc:`use_spack` for the Uberenv command and :doc:`build_and_test`
for the repeated source-edit loop.

.. _spack-reference-during-the-release-process:

Release reference selection
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Use :doc:`releases` for candidate testing, merged recipe pins, and final
publication updates.
