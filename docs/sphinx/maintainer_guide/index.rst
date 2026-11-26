.. Copyright (c) 2026, Lawrence Livermore National Security, LLC and
.. other RADIUSS Project Developers. See the top-level COPYRIGHT file.
.. SPDX-License-Identifier: (MIT)

.. _developer-guide:

Maintain platforms and shared specifications
============================================

This is the maintainer guide for RADIUSS Spack Configs. Project developers
should start with :doc:`../developer_workflow/index`.

Platform configuration
----------------------

Platform directories such as ``toss_4_x86_64_ib`` and
``toss_4_x86_64_ib_cray`` contain ``spack.yaml``, ``config.yaml``, and
``packages.yaml``. Machine subdirectories supply machine-specific settings;
some files are symlinks to shared platform files. Inspect the actual include
paths and symlink targets before editing.

For the TOSS and Cray platforms, generic externals and machine settings live in
``packages.yaml``. Each ``stacks/<name>.yaml`` defines one complete compiler
stack: requirements on the ``c``, ``cxx``, ``fortran`` and ``mpi`` virtuals,
compiler externals with executable paths and pairing flags in
``extra_attributes``, runtime requirements, and stack-specific MPI/GPU externals.
Compiler definitions may repeat between independent stacks. This lets the same
Clang version pair with different GCC versions in separate environments.
Stack names identify exact compiler versions, GCC pairing where needed, and
the MPI provider/version, including its compiler-labelled external suffix.
CUDA stacks append ``-cuda-<version>``. For example,
``clang-18.1.8-gcc-13.3.1-mvapich2-2.3.7.gcc_13-cuda-12.6.0`` identifies
the complete CUDA build stack. ``mvapich2-unavailable`` explicitly marks a
stack without a verified MPI installation. Do not add shorter alias names.
Machine directories link identical full names and own files that differ.
Do not add a legacy ``compilers.yaml`` to this setup.

RADIUSS Spack Configs CI loads one stack file per environment group using
``$env/$LCSCHEDCLUSTER/stacks/<name>.yaml`` in the group's ``override.include``.
Each group applies its stack to independently concretized roots. Project CI
selects one stack for its whole environment using ``RADIUSS_SPACK_STACK=<name>``
before Uberenv creates the environment. The platform manifest copies the selected
include into the new environment. An unknown stack fails while loading its
include. Without a stack selection, these platform files supply only generic
settings.

The language requirements select compilers for every consumer, including build
tools and dependencies whose root does not use Fortran or MPI. They do not
activate root variants. Keep root-only MPI coverage in project/root specs.

Stacks require the MPI provider and version through the ``mpi`` virtual; the
DAG audit checks every recorded MPI edge against that selection. Shared
``providers: mpi`` lists supply preferences. No MPI dependency requirement in
``all.require`` is needed, including when only a dependency uses MPI.
Retain ``compiler_mixing: false`` and ``reuse: false``; avoid recursive ``%%``
preferences, which can supersede applicable variant defaults for generic
externals with absent compiler metadata.

Stack files record the actual MPI installation. Corona ROCm and Clang 18 accept
a GCC MPI external with its solver-visible compiler binding deliberately omitted;
comments and prefixes retain its provenance. This compatibility exception still
needs build/runtime validation. Stacks without a matching installed MPI disable
building that provider and fail if MPI is requested. Generic externals with
unknown compiler provenance are accepted without claiming binary coherence.

The full installed CUDA catalog lives in shared ``packages.yaml``; it is not
a declaration that every toolkit is compatible with every compiler. A CUDA
stack replaces that catalog with a ``cuda::`` package override containing one
external, ``buildable: false`` and an exact version requirement. CPU stack files
contain no CUDA catalog. Select a separately named, verified CUDA stack for a
CUDA build rather than relying on the shared catalog to infer compatibility. ROCm
stacks expose only their ROCm version; absent components remain non-buildable.
Use configuration syntax supported by the tested Spack and recipe revisions.

For a machine or toolchain update:

#. Verify installed compiler, MPI, accelerator toolkit, and dependency paths
   and versions on the affected machine.
#. Update the narrowest applicable configuration. Review external package
   constraints, compiler flags, runtime requirements, and MPI selection together.
#. Update the relevant shared specifications in
   ``gitlab/radiuss-jobs/<machine>.yml``. Check the project variant and dependency
   variables, ``RADIUSS_SPACK_STACK``, and job names, which projects may override.
#. Keep the corresponding compiler/specification definitions in
   ``.gitlab/spack/envs/shared-ci/spack.yaml`` consistent. The environment
   root definitions are maintained separately; both paths load the same stack files.
#. Validate the affected environments and representative consumer builds, then
   :doc:`publish a tested baseline <baselines>`.

The generation job runs ``spack python utilities/check-stack-coherence.py``
after concretization. It checks every recorded language/MPI edge, pairing flags
and pinned runtimes, verifies CUDA stack overrides expose one pinned toolkit,
and rejects an empty concrete environment. It reports
externals with absent bindings separately; it does not test binary compatibility.

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
