.. Copyright (c) 2026, Lawrence Livermore National Security, LLC and
.. other RADIUSS Project Developers. See the top-level COPYRIGHT file.
.. SPDX-License-Identifier: (MIT)

Publish tested baselines
========================

A tested baseline is a combination of configuration revision, Spack engine
revision, recipe-repository revision, specifications, and validation results.
A configuration tag identifies that combination; it does not update consumer
pins automatically.

#. Review platform and shared-spec changes, and the complete impact of a
   recipe revision update. Check compatible Uberenv behavior in consumers.
#. Run the relevant :doc:`validation environments
   <../ci_implementation/index>` and representative consumer build/test jobs.
   Record exact resolved revisions, machines, specifications, and results in
   the review or release record.
#. Merge the validated changes and tag the tested configuration commit.
#. Have consumers adopt the configuration submodule revision and any required
   engine and recipe pins together, then verify their own build/test loop.
   Follow :doc:`../user_guide/releases` for coordinated project releases.

Tag naming
----------

Recent tags follow
``v<release>-spack-<engine-ref>-packages-<recipe-sha>``.
For example, the existing tag
``v2026.07.0-spack-v1.2.2-packages-e4c0b2d275`` records a configuration release,
a Spack reference, and a recipe revision. The first field is the configuration
release, not a declaration of the latest supported RAJA or Umpire version.
Older tags use earlier naming conventions.

A nearby ancestor tag is useful context, but is not proof that a later
configuration commit was tested with the same inputs. Consult its validation
record and the selected environment files. Record full hashes in validation
evidence even when a tag abbreviates them. Preserve published tags and their
tested pins.
