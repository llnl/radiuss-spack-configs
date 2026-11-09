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
#. Merge recipes upstream and update the ``spack-packages`` remote repository
   ``commit`` in each project's ``.rad-bat.json`` to the **actual merged
   revision** before releases begin.
#. Add final ``version(...)`` entries with tags, commit hashes, or archive
   checksums as source releases become available. Coordinate any necessary
   recipe-repository pin updates among remaining participants and validate the
   updated builds.
#. Close the release round by updating participating development branches to
   the same tested ``spack-packages`` revision, including final version metadata.

Project ``develop`` branches and release tags must use upstream-merged recipe
revisions. Published tags retain their tested pins; do not retag a source
release simply to adopt a later recipe revision.

A source release cannot record a recipe revision that already contains the
release's final commit hash: updating ``.rad-bat.json`` changes the source
commit hash. Prepare recipe behavior first, then publish the final source
identity in the upstream recipe afterward.

.. graphviz:: /figures/release-pins.dot
   :align: center
   :caption: The RAJA release records recipe revision R1. Only the later recipe revision R2 can record RAJA's final source commit S; the published RAJA tag keeps R1.
   :alt: First merge recipe behavior as R1. Record R1 in RAJA's .rad-bat.json, test RAJA, and tag source commit S. Then add S to the upstream recipe's version metadata and merge as R2. R1, R2, and S are symbolic commit labels.

.. _future-version-conditions:

Prepare future behavior and preserve older releases
---------------------------------------------------

RADIUSS projects are tested together as coordinated sets of releases. Encode
those relationships in the recipes so older releases keep using their tested
dependency series, even when other combinations are not known to fail. The
version ranges for the newest release stay open-ended to support ongoing
development. Bound those ranges when a development incompatibility appears
or the next release round begins.

The following lifecycle uses RAJA's dependency on CAMP, with illustrative
March and July release series. Apply the same review to other dependencies
within the joint release; compatible series need not share version numbers.

**After the March release**, allow RAJA to use CAMP from March onward:

.. code-block:: python

   depends_on("camp@2026.03:", when="@2026.03:")

The ``when="@2026.03:"`` condition also matches ``raja@develop``. With March
as the latest available CAMP release, a fresh concretization normally selects
``camp@2026.03`` over ``camp@develop``. Explicit specs, configured preferences,
and reuse of existing concretizations can affect that selection.

**If RAJA development needs an unreleased CAMP feature**, keep RAJA
2026.03 on CAMP 2026.03 and give ``raja@develop`` an explicit requirement.
Replace the previous rule with:

.. code-block:: python

   depends_on("camp@2026.03", when="@2026.03")
   depends_on("camp@develop commit=<commit>", when="@develop")

Replace ``<commit>`` with the full hash of a tested CAMP commit containing the
feature. The ``commit`` constraint selects exactly one revision of
``camp@develop``, rather than "this commit or later."
The bounded ``camp@2026.03`` constraint permits patches in the March series,
but excludes CAMP 2026.07 and ``camp@develop``.

**When preparing July**, bound both March version ranges even if no
incompatibility was found. Replace the previous rules, including any temporary
development pin, with:

.. code-block:: python

   depends_on("camp@2026.03", when="@2026.03")
   depends_on("camp@2026.07:", when="@2026.07:")

The ``when="@2026.07:"`` condition matches both ``raja@2026.07`` and
``raja@develop`` without requiring a July ``version(...)`` entry in RAJA's
recipe. If CAMP declares only March and ``develop``, ``camp@2026.07:`` permits
``camp@develop`` and excludes CAMP 2026.03. Once CAMP 2026.07 is declared,
Spack normally prefers that release over ``camp@develop``. The colon matters:
``camp@2026.07`` excludes ``develop``; an unavailable numeric version is not
an alias for a development branch. The open range also permits explicitly
testing ``raja@develop ^camp@develop``.

Removing the commit pin makes CAMP a moving dependency until a suitable
release is available. Record the source commits tested, and validate again
when adopting the published releases. Merge the tested recipe behavior before
tagging projects, then add final ``version(...)`` metadata as the sources
become available. Do not declare a tag or archive that does not yet exist:
Spack can select the declared version during concretization, but fetching
the unavailable source will fail.

.. _validate-both-version-semantics:

Test development and release versions
-------------------------------------

``rad-bat spack`` develops the project checkout as ``<package>@develop`` and
therefore validates the recipe's development conditions. Validate the planned
release conditions separately with a root spec selecting the intended numeric
version. Use local source while release staging requires it; after publication,
check that Spack fetches and builds the released source through its final
``version(...)`` entry.

For each affected package, check that the candidate recipe permits compatible
dependencies and rejects combinations outside the coordinated series for
supported older releases. Concretize specs to check dependency selection, then
build and test to check compatibility. Include both results in the release review.
