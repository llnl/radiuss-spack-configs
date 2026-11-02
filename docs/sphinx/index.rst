.. Copyright (c) 2026, Lawrence Livermore National Security, LLC and
.. other RADIUSS Project Developers. See the top-level COPYRIGHT file.
.. SPDX-License-Identifier: (MIT)

RADIUSS Spack Configs
=====================

RADIUSS Spack Configs provides shared machine and toolchain configuration for
Spack on Livermore Computing (LC) systems, plus specifications used by project
CI. It helps developers prepare dependencies, generate a CMake host
configuration, and return to their normal build and test loop.

.. _overview:
.. _radiuss-spack-configs-user-documentation:
.. _radiuss-spack-configs-developer-documentation:
.. _shared-spack-specs-for-ci:
.. _ci-implementation-for-radiuss-spack-configs:
.. _custom-ci-pipelines:

Start with :doc:`user_guide/index`. Infrastructure maintainers should use
:doc:`developer_guide/index` for platform changes and validation baselines.

.. toctree::
   :maxdepth: 1
   :caption: Developer workflow

   user_guide/index
   user_guide/use_spack
   user_guide/build_and_test
   user_guide/changes
   user_guide/releases
   user_guide/ci
   user_guide/how_to

.. toctree::
   :maxdepth: 1
   :caption: Maintainer guide

   developer_guide/index
   ci_implementation/index
   developer_guide/track_spack_packages
   developer_guide/baselines

.. toctree::
   :maxdepth: 1
   :caption: Reference

   reference/index

Background and motivation
-------------------------

LLNL's RADIUSS effort supports libraries and tools for scientific application
development. Shared configurations let participating projects test comparable
toolchains and exercise their upstream packaging during development. Build
preparation also works outside CI; adopting one does not require the other.
