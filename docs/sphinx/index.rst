.. Copyright (c) 2026, Lawrence Livermore National Security, LLC and
.. other RADIUSS Project Developers. See the top-level COPYRIGHT file.
.. SPDX-License-Identifier: (MIT)

RADIUSS Spack Configs
=====================

RADIUSS Spack Configs provides shared machine and toolchain configuration for
Spack on Livermore Computing (LC) systems, plus specifications used by project
CI. Developers use these settings to prepare dependencies, generate a CMake
host configuration, and return to their normal build and test loop.

.. _overview:
.. _radiuss-spack-configs-user-documentation:
.. _radiuss-spack-configs-developer-documentation:
.. _shared-spack-specs-for-ci:
.. _ci-implementation-for-radiuss-spack-configs:
.. _custom-ci-pipelines:

Start with :doc:`developer_workflow/index`. Infrastructure maintainers should use
:doc:`maintainer_guide/index` for platform changes and validation procedures.

.. toctree::
   :maxdepth: 1
   :caption: Developer workflow

   developer_workflow/index
   developer_workflow/use_spack
   developer_workflow/rad_bat
   developer_workflow/build_and_test
   developer_workflow/changes
   developer_workflow/releases
   developer_workflow/ci
   developer_workflow/how_to

.. toctree::
   :maxdepth: 1
   :caption: Maintainer guide

   maintainer_guide/index
   maintainer_guide/rad_bat
   ci_implementation/index
   maintainer_guide/track_spack_packages
   maintainer_guide/baselines

.. toctree::
   :maxdepth: 1
   :caption: Reference

   reference/index
   reference/rad_bat

Background and motivation
-------------------------

LLNL's RADIUSS effort supports libraries and tools for scientific application
development. Shared configurations let participating projects test comparable
toolchains and exercise their upstream packaging during development. Build
preparation also works in an interactive compute allocation, without CI.
