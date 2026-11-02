.. Copyright (c) 2026, Lawrence Livermore National Security, LLC and
.. other RADIUSS Project Developers. See the top-level COPYRIGHT file.
.. SPDX-License-Identifier: (MIT)

Coordinate releases
===================

Prepare compatibility changes early so each project's release needs only
small publication updates. Use explicit owners and parallel validation to
converge before releases begin. Staggered releases are a condition to handle,
not the intended schedule.

.. _joint-release-process:

Joint release process
---------------------

#. Agree on participants, intended versions, dependency compatibility, owners,
   and a target completion date.
#. Prepare recipe changes together on a dedicated branch and pull request in
   ``spack-packages``, using future-version conditions where appropriate.
#. Test candidate commits from project feature or release-staging branches.
   Validate development, intended release, and affected previous-release
   behavior across participants.
#. Merge recipes upstream, replace candidate pins with the **actual merged
   revision**, and converge on that baseline before releases begin.
#. Add final ``version(...)`` entries with tags, commit hashes, or archive
   checksums as source releases become available. Coordinate any necessary
   recipe-pin updates among remaining participants and validate them.
#. Close the round promptly and converge participating development branches on
   a validated recipe baseline containing the final publication updates.

Project ``develop`` branches and release tags must use upstream-merged recipe
revisions. Published tags retain their tested pins; do not retag a source
release simply to adopt a later recipe revision.

Final metadata depends on source availability. A tagged project cannot embed a
recipe revision already containing its own final commit hash: changing that
embedded pin changes the project's hash. Prepare recipe behavior first, then
publish the final source identity in the upstream recipe afterward.

.. _future-version-conditions:

Prepare future behavior and preserve older releases
---------------------------------------------------

.. important::

   Adrien review before publication: carefully review the future-version and
   previous-release compatibility guidance below, including the selected
   historical examples and their applicability to the intended release round.

A condition can mention a future version without a corresponding
``version(...)`` entry. This lets a recipe prepare new requirements before the
source release exists. It does not make an unavailable release downloadable.

For example, `spack-packages #5716
<https://github.com/spack/spack-packages/pull/5716>`_ prepared RAJAPerf's C++
standard behavior using this condition:

.. code-block:: python

   conflicts("cxxstd=17", when="@2026.07.0:")

This historical example teaches preparing version-dependent behavior, not
copying its version threshold into another package. Open-ended future-version
conditions such as ``@2026.07.0:`` can also match ``develop``. Bounded release
series such as ``@2025.12`` do not match ``develop``. Check both meanings when
writing or reviewing recipe conditions.

A restriction on the parent version does not bound its dependencies.
`#5961 <https://github.com/spack/spack-packages/pull/5961>`_ introduced release
updates that left CARE's older release dependency ranges open-ended;
`#6652 <https://github.com/spack/spack-packages/pull/6652>`_ corrected them.
The distinction highlighted in `Adrien's review
<https://github.com/spack/spack-packages/pull/5961#discussion_r3950488022>`_ is:

.. code-block:: python

   # Historical mistake: the parent is restricted, the dependency is not.
   depends_on("umpire@2025.12:", when="@0.15.3")

   # Corrected: preserve the older release's compatible dependency series.
   depends_on("umpire@2025.12", when="@0.15.3")

These are alternatives, not two declarations to add together. The first allows
Umpire 2026.07 and ``develop``; the second excludes them and permits the
2025.12 series. Apply the same compatibility review to RAJA, CHAI, and any
other affected dependencies when introducing a release. Do not assume that
updating the newest release's constraints preserves all previous releases.

Validate both version semantics
-------------------------------

For the RAJA integration, ``package_version: develop`` applies development
recipe conditions to the local checkout. A release-staging checkout must also
be tested with its intended release semantics, matching source and recipe
expectations. Before source publication, validate candidate source through the
project's local development build path; after publication, validate the actual
version metadata and fetched source as well.

For each affected package, check that the candidate recipe permits compatible
dependencies and rejects incompatible newer series for supported older
releases. Concretization checks establish selection behavior; builds and tests
establish source compatibility. Retain both in the release review evidence.
