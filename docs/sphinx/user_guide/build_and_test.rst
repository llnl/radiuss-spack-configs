.. Copyright (c) 2026, Lawrence Livermore National Security, LLC and
.. other RADIUSS Project Developers. See the top-level COPYRIGHT file.
.. SPDX-License-Identifier: (MIT)

.. _build_and_test-label:
.. _build-and-test-your-code-using-your-usual-workflow:

Build and test
==============

.. graphviz:: /figures/developer-loop.dot
   :align: center
   :caption: Prepare once for a specification, then repeat the source build and test loop.
   :alt: Uberenv runs Spack to concretize a spec, install dependencies, and generate a host configuration. CMake and CTest build and test the project. Source edits repeat builds; recipe, dependency, or toolchain changes require rerunning Uberenv.

After :doc:`use_spack`, select the generated host configuration explicitly.
Use the CMake executable recorded in it, or a compatible CMake on your PATH,
on the same machine with the compiler modules used to install dependencies.
From the RAJA checkout root, replace the filename below with the actual output:

.. _using-configuration-files-to-build-the-project:

.. code-block:: bash

   cmake -S . -B build -C /absolute/path/to/generated-host-config.cmake
   cmake --build build --parallel
   ctest --test-dir build --output-on-failure

For ordinary source edits, repeat only the build and test commands. Spack and
Uberenv are not needed for each edit.

Use a separate build directory for each host configuration. When changing the
compiler, variants, dependencies, or ``spack-packages`` revision, follow
:doc:`changes`, regenerate the host configuration, and configure a fresh build
directory. Loading a new initial cache into an old CMake build directory can
leave stale values behind.

.. _write-ci-script:

Writing a script for CI
-----------------------

A project build/test script should accept ``SPEC`` without the project name,
run dependency preparation, select the resulting host configuration, configure
and build the project checkout, and report test failures. It should also run
in an interactive compute allocation outside GitLab. For RAJA, run:

.. code-block:: bash

   SPEC="%gcc" ./scripts/gitlab/build_and_test.sh

Each project maintains its script and documents its options and required
compute resources. The script should exit on failure and require a filename
if several host configurations are present. See :doc:`ci` for how shared jobs
pass ``SPEC`` to the script.

.. _debugging:

Debugging
---------

Identify whether a failure occurs during dependency preparation, configuration,
compilation, or testing. Follow :doc:`how_to` to narrow down the cause.
