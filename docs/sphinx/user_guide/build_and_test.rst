.. Copyright (c) 2026, Lawrence Livermore National Security, LLC and
.. other RADIUSS Project Developers. See the top-level COPYRIGHT file.
.. SPDX-License-Identifier: (MIT)

.. _build_and_test-label:
.. _build-and-test-your-code-using-your-usual-workflow:

Build and test
==============

After :doc:`use_spack`, select the generated host configuration explicitly.
Use the CMake executable recorded in it, or a compatible CMake on your PATH,
and retain the machine/toolchain environment used to prepare dependencies.
From the RAJA checkout root, replace the filename below with the actual output:

.. _using-configuration-files-to-build-the-project:

.. code-block:: bash

   cmake -S . -B build -C /absolute/path/to/generated-host-config.cmake
   cmake --build build --parallel
   ctest --test-dir build --output-on-failure

For ordinary source edits, repeat only the build and test commands. Spack and
Uberenv are not needed for each edit. CMake can regenerate its build system
when project CMake inputs change.

Use a separate build directory for each host configuration. When changing the
compiler, variants, dependency requirements, or recipe baseline, follow
:doc:`changes`, regenerate the host configuration, and configure a fresh build
directory. Loading a new initial cache into an old CMake build directory can
leave stale values behind.

.. _write-ci-script:

Writing a script for CI
-----------------------

A project build/test driver should accept ``SPEC`` without the project name,
run dependency preparation, select the resulting host configuration, configure
and build the project checkout, and report test failures. It should also run
from a developer allocation outside GitLab. RAJA's integration exposes this as:

.. code-block:: bash

   SPEC="%gcc" ./scripts/gitlab/build_and_test.sh

The project owns this driver, its allocation requirements, and any additional
options. When writing one, propagate failures and require an explicit selection
if several host configurations are present. See :doc:`ci` for how shared jobs
pass ``SPEC`` to the driver.

.. _debugging:

Debugging
---------

Identify whether a failure occurs during dependency preparation, configuration,
compilation, or testing. Use :doc:`how_to` to reproduce that stage with the
same inputs.
