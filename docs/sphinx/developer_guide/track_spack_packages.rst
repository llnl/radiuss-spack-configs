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
runs each Monday at 06:17 UTC and opens or refreshes one tracking issue for
each affected environment. It also prepares a branch containing the associated
pin update, ready for review and for opening a pull request.

Watched inputs
==============

The workflow matrix in
``.github/workflows/track-spack-packages.yml`` declares an entry's Spack
environment file and its watched paths. Package names are converted to Spack's
directory convention (for example, ``raja-perf`` becomes ``raja_perf``).
Literal paths can also be tracked; the cached-CMake build-system implementation
is one such path.

The workflow first looks for its generated branch,
``automation/spack-packages-tracker-<matrix-entry>``. When that branch has a
valid ``spack.repos.builtin.commit`` value for the matrix entry's
``spack.yaml``, that in-progress pin is the baseline. Otherwise the baseline
is the pin in the default-branch version of ``spack.yaml``. Each matrix entry
independently updates only its own environment file.

Selecting a stable target
=========================

The workflow fetches the upstream ``develop`` branch and checks whether the
baseline pin is an ancestor of it. It then compares that revision with
``develop``, limited to the watched paths. Using the generated branch's pin
when present means that changes already prepared on that branch are not
repeated in a later issue or diff.

When relevant changes exist, the target is the last ``develop`` commit that
touches a watched path in that range. This is the first revision containing all
of the current watched-path changes. In particular, commits added to
``develop`` after that point do not change the proposed pin unless they touch a
watched path. The corresponding issue diff is also limited to the range from
the current pin to this stable target.

If the pin is unavailable upstream or is not an ancestor of ``develop``, the
workflow opens a tracking issue without preparing a branch. This prevents an
automatic update from silently choosing an unsafe history transition; resolve
the divergence manually before updating the pin.

Prepared branches and issues
============================

For a normal update, the workflow creates a branch named
``automation/spack-packages-tracker-<matrix-entry>`` from the repository's
checked-out default branch. The branch name does not include the target SHA, so
each matrix entry has one long-lived generated pull-request source. An entry
changes its own pinned commit in ``spack.yaml``, commits that change, and pushes
its branch. Later runs that select a newer target add a new commit to that
branch; a rerun that selects the already-pinned target makes no change. This
lets the branch remain the pull-request source as relevant upstream changes
arrive without mixing updates from different tracked scopes.

The branch is automation-owned. If its tracked environment file no longer
contains a valid Spack commit, the workflow rebuilds the branch from the
scheduled-run checkout and force-updates it with a lease after applying the
selected pin. Every push uses a lease, which prevents replacing a branch that
changed after the workflow fetched it.

The tracking issue records the current and proposed commits, changed watched
paths, a bounded diff, and a link to the prepared branch. Repeated scheduled
runs update the existing open issue for the same matrix entry. After reviewing
the branch and any CI results, open a pull request from it in the usual way.

Maintaining the tracker
=======================

To watch another package, add its Spack package name to the appropriate
``packages`` matrix value. To watch a non-package path, add it to ``files``.
Each entry must declare at least one of these values. Keep the scope limited to
inputs that can require a new vetted Spack reference; broad paths make the
tracker noisier and cause more pin updates.

The workflow needs ``contents: write`` to push its prepared branches and
``issues: write`` to maintain tracking issues. The destination repository must
also retain the ``automation`` label used by the issue lookup and creation
steps.
