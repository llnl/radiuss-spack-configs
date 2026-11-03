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

RADIUSS projects are tested together as coordinated sets of releases. Encode
those relationships in the recipes so older releases keep using their tested
dependency series, even when other combinations are not known to fail. The
newest release series stays open-ended to support ongoing development; close
it when a development incompatibility appears or the next release round begins.

The following lifecycle uses RAJA's dependency on CAMP, with illustrative
March and July release series. Apply the same review to other dependencies
within the joint release; compatible series need not share version numbers.

**After the March release**, allow the newest series and later versions:

.. code-block:: python

   depends_on("camp@2026.03:", when="@2026.03:")

This condition also applies to ``raja@develop``. With March as the latest
available CAMP release, a fresh concretization normally selects it over
``camp@develop``. Explicit specs, configured preferences, and reuse of
existing concretizations can affect that selection.

**If RAJA development needs an unreleased CAMP feature**, keep March on its
coordinated series and give development an explicit requirement. Replace the
previous rule with:

.. code-block:: python

   depends_on("camp@2026.03", when="@2026.03")
   depends_on("camp@develop commit=<commit>", when="@develop")

Replace ``<commit>`` with the full hash of a tested CAMP commit containing the
feature. The ``commit`` constraint selects that exact commit of
``camp@develop``. It does not mean "this commit or later."
The bounded March rule permits patches in the 2026.03 series, but excludes
July and ``develop``.

**When preparing July**, close the March rule even if no incompatibility was
found. Replace the previous rules, including any temporary development pin,
with:

.. code-block:: python

   depends_on("camp@2026.03", when="@2026.03")
   depends_on("camp@2026.07:", when="@2026.07:")

The July condition applies to both ``raja@2026.07`` and ``raja@develop`` without
requiring a July ``version(...)`` entry. If CAMP declares only March and
``develop``, ``camp@2026.07:`` permits ``develop`` and excludes March. Once the
July release is declared, Spack normally prefers it. The colon matters:
``camp@2026.07`` excludes ``develop``; an unavailable numeric version is not
an alias for a development branch. The open range also permits explicitly
testing ``raja@develop ^camp@develop``.

Removing the commit pin makes CAMP a moving dependency until a suitable
release is available. Record the source commits tested, and validate again
when adopting the published releases. Merge the tested recipe behavior before
tagging projects, then add final ``version(...)`` metadata as the sources
become available. Do not declare a tag or archive that does not yet exist:
Spack can select it during concretization, but fetching it will fail.

.. _validate-both-version-semantics:

Test development and release versions
-------------------------------------

In RAJA's ``.uberenv_config.json``, ``package_version: develop`` selects the
recipe conditions for development builds. Also test the release-staging source
with ``package_version`` set to the planned release version, so Spack applies
its release conditions. Use local source until the release is published, then
test that Spack fetches and builds it using the final ``version(...)`` entry.

For each affected package, check that the candidate recipe permits compatible
dependencies and rejects combinations outside the coordinated series for
supported older releases. Concretize specs to check dependency selection, then
build and test to check compatibility. Include both results in the release review.
