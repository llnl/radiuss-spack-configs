.. Copyright (c) 2026, Lawrence Livermore National Security, LLC and
.. other RADIUSS Project Developers. See the top-level COPYRIGHT file.
.. SPDX-License-Identifier: (MIT)

.. _developer-guide:

Maintain platforms and shared specifications
============================================

This is the maintainer guide for RADIUSS Spack Configs. Project developers
should start with :doc:`../user_guide/index`.

Platform configuration
----------------------

Platform directories such as ``toss_4_x86_64_ib`` and
``toss_4_x86_64_ib_cray`` contain ``spack.yaml``, ``config.yaml``, and
``packages.yaml``. Machine subdirectories supply machine-specific settings;
some files are symlinks to shared platform files. Inspect the actual include
paths and symlink targets before editing.

Compilers are external packages in ``packages.yaml`` with executable paths in
``extra_attributes.compilers``. Named combinations live in the ``toolchains``
section. Do not add a legacy ``compilers.yaml`` to this setup. Use configuration
syntax supported by the tested Spack and ``spack-packages`` revisions.

For a machine or toolchain update:

#. Verify installed compiler, MPI, accelerator toolkit, and dependency paths
   and versions on the affected machine.
#. Update the narrowest applicable configuration. Review external package
   constraints, compiler runtime dependencies, and named toolchains together.
#. Update the relevant shared specifications in
   ``gitlab/radiuss-jobs/<machine>.yml``. Check the project variant and dependency
   variables and job names, which projects may override.
#. Keep the corresponding compiler/specification definitions in
   ``.gitlab/spack/envs/shared-ci/spack.yaml`` consistent. The environment
   definitions are maintained separately, without automatic imports from the
   shared job files.
#. Validate the affected environments and representative consumer builds, then
   :doc:`publish a tested baseline <baselines>`.

The ``darwin`` configuration is a development starting point, outside LC
validation. Adapt external paths and versions to the local installation.

Repository maintenance
----------------------

The optional ``spack_repo/llnl_radiuss`` repository is for local recipe testing
in RADIUSS Spack Configs. Shared recipes belong upstream in
`spack/spack-packages <https://github.com/spack/spack-packages>`_. For testing
inside a consuming project, use :ref:`local-recipe-overrides`.

* :doc:`../ci_implementation/index` describes validation purposes, manual
  environment selection, and storage lifetimes.
* :doc:`track_spack_packages` describes automated recipe revision proposals.
* :doc:`baselines` describes recording and publishing tested combinations.
