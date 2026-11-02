.. Copyright (c) 2026, Lawrence Livermore National Security, LLC and
.. other RADIUSS Project Developers. See the top-level COPYRIGHT file.
.. SPDX-License-Identifier: (MIT)

Coordinate releases
===================

Prepare and test recipe changes together before releasing the participating
projects. Agree on who maintains each recipe and aim to use the same tested
``spack-packages`` revision, leaving only final version metadata to add as
source releases become available.

.. graphviz:: /figures/release-coordination.dot
   :align: center
   :caption: Prepare and validate recipes together before publishing source releases.
   :alt: Agree on participants and owners, prepare recipes, and validate candidates in parallel. Merge upstream, adopt the actual merged revision, converge, publish source and final metadata, then close the round with a common development baseline.

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
#. Merge recipes upstream and update each project's ``spack_packages_commit``
   to the **actual merged revision** before releases begin.
#. Add final ``version(...)`` entries with tags, commit hashes, or archive
   checksums as source releases become available. Coordinate any necessary
   recipe-pin updates among remaining participants and validate them.
#. Close the release round by updating participating development branches to
   the same tested ``spack-packages`` revision, including final version metadata.

Project ``develop`` branches and release tags must use upstream-merged recipe
revisions. Published tags retain their tested pins; do not retag a source
release simply to adopt a later recipe revision.

A tagged project cannot embed a
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

This rule rejects C++17 for RAJAPerf 2026.07.0 and later. Its open-ended
condition also matches ``develop``. In contrast, a bounded release series
such as ``@2025.12`` does not match ``develop``. Choose the version range
according to which releases and development builds need the new behavior.

Restricting a rule to one version of a package does not limit the versions of
its dependencies.
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
other affected dependencies when introducing a release.

.. _validate-both-version-semantics:

Test development and release versions
-------------------------------------

In RAJA's ``.uberenv_config.json``, ``package_version: develop`` selects the
recipe conditions for development builds. Also test the release-staging source
with ``package_version`` set to the planned release version, so Spack applies
its release conditions. Use local source until the release is published, then
test that Spack fetches and builds it using the final ``version(...)`` entry.

For each affected package, check that the candidate recipe permits compatible
dependencies and rejects incompatible newer series for supported older
releases. Concretize specs to check dependency selection, then build and test
to check compatibility. Include both results in the release review.
