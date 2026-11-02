.. Copyright (c) 2026, Lawrence Livermore National Security, LLC and
.. other RADIUSS Project Developers. See the top-level COPYRIGHT file.
.. SPDX-License-Identifier: (MIT)

Use CI
======

Consumer CI runs the developer workflow against the project checkout. RADIUSS
Spack Configs supplies shared ``SPEC`` jobs, the project supplies its build/test
command and custom jobs, and `RADIUSS Shared CI
<https://radiuss-shared-ci.readthedocs.io/en/latest/>`_ supplies versioned GitLab
components for machine execution, allocations, and reporting.

.. graphviz:: /figures/consumer-ci.dot
   :align: center
   :caption: Consumer CI combines shared specifications, project settings, and a selected CI component.
   :alt: Shared jobs and project settings feed pipeline composition. The selected Shared CI component revision provides execution. The generated child pipeline runs the project preparation, build, and test driver with SPEC.

This differs from :doc:`../ci_implementation/index`, which validates Spack
environments inside RADIUSS Spack Configs itself.

.. _consumer-shared-jobs:

Compose shared and project jobs
-------------------------------

In the RAJA integration, a generation job combines
``scripts/radiuss-spack-configs/gitlab/radiuss-jobs/dane.yml`` and
``.gitlab/jobs/dane.yml`` into a ``dane-jobs.yml`` artifact. The child pipeline
includes the selected Shared CI machine component, project custom jobs, and
that artifact. The project passes its build/test driver through the component's
``job_cmd`` input, commonly from ``JOB_CMD``.

Follow the integration instructions for the selected Shared CI component
version, including its required stages and inputs. Older ``project/ref/file``
template examples are not interchangeable with the component interface.

Shared jobs set ``SPEC`` and extend the machine job template. For example,
the Dane GCC job uses ``PROJECT_DANE_VARIANTS`` and ``PROJECT_DANE_DEPS`` to
let each project add applicable variants and dependencies. Set these in the
project CI variables; do not impose a project-only option on all consumers.

Overrides and merged configuration
----------------------------------

Keep shared definitions before project definitions when composing jobs, so the
project's overrides take precedence in the supported integration. Because a
combined artifact can contain repeated YAML keys, inspect GitLab's final
merged configuration; do not assume every YAML parser merges duplicate job
mappings field by field. Preserve the required shared fields in a local
replacement unless the integration explicitly merges them.

A local job with the same name can adjust its spec, resources, or
``allow_failure`` behavior. A new name adds a separate job. Review overrides
whenever adopting a new configuration revision: a renamed or changed shared
job may invalidate the override. Temporary ``allow_failure: true`` exceptions
should have a tracked cause and a removal condition.

Reproduce a CI failure
----------------------

Record the project checkout, recursive submodule revisions, engine and recipe
pins, machine, resolved ``SPEC``, and failing stage. In a suitable allocation,
run the :ref:`project driver <write-ci-script>` or the individual preparation
and CMake steps. See :doc:`how_to` for narrowing the failure.
