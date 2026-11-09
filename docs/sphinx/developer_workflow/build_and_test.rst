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
   :alt: rad-bat uses a maintained host configuration or runs Spack to concretize a spec, install dependencies, and generate one. CMake and CTest build and test the project. Source edits repeat builds; recipe, dependency, or toolchain changes require a rad-bat refresh.

``rad-bat`` selects the maintained or newly generated host configuration and
passes it to the project build/test driver. To run the same steps manually,
use the CMake executable recorded in the host configuration, or a compatible
CMake on your PATH, on the same machine with the compiler modules used to
install dependencies. From the project checkout root, replace the filename
below with the selected file:

.. _using-configuration-files-to-build-the-project:

.. code-block:: bash

   cmake -S . -B build -C /absolute/path/to/generated-host-config.cmake
   cmake --build build --parallel
   ctest --test-dir build --output-on-failure

For ordinary source edits, repeat only the build and test commands. Spack is
not needed for each edit.

Use a separate build directory for each host configuration. When changing the
compiler, variants, dependencies, or ``spack-packages`` revision, follow
:doc:`changes`, regenerate the host configuration, and configure a fresh build
directory. Loading a new initial cache into an old CMake build directory can
leave stale values behind.

.. _write-ci-script:

Writing a script for CI
-----------------------

A project build/test driver should also run in an interactive compute
allocation outside GitLab. In a ``rad-bat`` integration, keep dependency
preparation outside that driver: accept an explicit host configuration and
work directory, then configure, build, install, and test the project. Record
the command as an argument array in ``.rad-bat.json``; see :doc:`rad_bat`.

Each project maintains its driver and documents its options and required
compute resources. It should exit on failure and require a filename if several
host configurations are present. See :doc:`ci` for how shared jobs pass
``SPEC`` and an optional maintained host-config selection.

.. _debugging:

Debugging
---------

Identify whether a failure occurs during dependency preparation, configuration,
compilation, or testing. Follow :doc:`how_to` to narrow down the cause.
