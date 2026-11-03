.. Copyright (c) 2026, Lawrence Livermore National Security, LLC and
.. other RADIUSS Project Developers. See the top-level COPYRIGHT file.
.. SPDX-License-Identifier: (MIT)

Publish tested baselines
========================

A tested baseline records the RADIUSS Spack Configs, Spack, and
``spack-packages`` revisions, along with the specs tested and their results.
A RADIUSS Spack Configs tag identifies this combination; projects must
explicitly update their references to adopt the tested baseline.

#. Review platform and shared-spec changes, and the complete impact of a
   recipe revision update. Check that projects' Uberenv versions support the changes.
#. Run the relevant :doc:`validation environments
   <../ci_implementation/index>` and representative consumer build/test jobs.
   Record the commit hashes, machines, specs, and results in
   the review or release record.
#. Merge the validated changes and tag the tested configuration commit.
#. Have projects update their RADIUSS Spack Configs submodule and any required
   Spack and ``spack-packages`` revisions together, then build and test.
   Follow :doc:`../user_guide/releases` for coordinated project releases.

Tag naming
----------

Recent tags follow
``v<release>-spack-<spack-ref>-packages-<recipe-sha>``.
For example, the existing tag
``v2026.07.0-spack-v1.2.2-packages-e4c0b2d275`` records a configuration release,
a Spack reference, and a recipe revision. The first field is the configuration
release, not a declaration of the latest supported RAJA or Umpire version.
Older tags use earlier naming conventions.

A nearby ancestor tag is useful context, but is not proof that a later
configuration commit was tested with the same inputs. Consult the validation
record and environment files for the commit you plan to adopt. Record full
hashes in validation evidence even when a tag abbreviates them. Preserve published tags and their
tested pins.
