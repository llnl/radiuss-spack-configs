.. ## Copyright (c) 2026, Lawrence Livermore National Security, LLC and
.. ## other RADIUSS Project Developers. See the top-level COPYRIGHT file for
.. ## details.
.. ##
.. ## SPDX-License-Identifier: (MIT)

.. _Tracking Spack Packages:


Tracking Spack Package Updates
##############################

The ``Track spack-packages updates`` GitHub Actions workflow watches selected
parts of `spack/spack-packages <https://github.com/spack/spack-packages>`_. It
runs weekly and, when it finds a relevant change, opens or refreshes a tracking
issue and prepares a branch with the corresponding recipe-repository pin update. Each
workflow matrix entry has its own issue and generated branch.

Reviewing updates
=================

Review the issue's changed paths and diff, then inspect the prepared branch
named ``automation/spack-packages-tracker-<matrix-entry>``. The proposal updates ``spack.repos.builtin.commit`` in the selected
environment's ``spack.yaml``; it does not update the Spack engine or consumers.
The normal target is the last upstream commit touching a watched path, not
necessarily the latest upstream HEAD. That revision also includes intervening
changes outside the watched paths, so assess the complete impact of adopting it.

Open a pull request for the reviewed proposal and validate the selected
:doc:`environment <../ci_implementation/index>` before merging. A
``cached-cmake`` proposal needs a manually selected pipeline. If the configured
pin is missing from upstream history or is not an ancestor of upstream
``develop``, the issue calls for manual review and no branch is prepared.
Publish accepted changes following :doc:`baselines`.

Adding watched inputs
=====================

The matrix in ``.github/workflows/track-spack-packages.yml`` defines each
environment and what it watches. Add a Spack package name to its ``packages``
value, or add an upstream non-package path to ``files``. Keep the watched scope
limited to changes that may require a new validated recipe-repository revision.
