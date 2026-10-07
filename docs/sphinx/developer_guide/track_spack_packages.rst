.. ## Copyright (c) 2026, Lawrence Livermore National Security, LLC and
.. ## other RADIUSS Project Developers. See the top-level COPYRIGHT file for
.. ## details.
.. ##
.. ## SPDX-License-Identifier: (MIT)

.. _Tracking Spack Packages:

###############################
Tracking Spack Package Updates
###############################

The ``Track spack-packages updates`` GitHub Actions workflow watches selected
parts of `spack/spack-packages <https://github.com/spack/spack-packages>`_. It
runs weekly and, when it finds a relevant change, opens or refreshes a tracking
issue and prepares a branch with the corresponding Spack pin update. Each
workflow matrix entry has its own issue and generated branch.

Reviewing updates
=================

Review the issue's changed paths and diff, then inspect the prepared branch
named ``automation/spack-packages-tracker-<matrix-entry>``. Once the proposed
pin and any required testing are acceptable, open a pull request from that
branch.

Adding watched inputs
=====================

The matrix in ``.github/workflows/track-spack-packages.yml`` defines each
environment and what it watches. Add a Spack package name to its ``packages``
value, or add an upstream non-package path to ``files``. Keep the watched scope
limited to changes that may require a new vetted Spack reference.
