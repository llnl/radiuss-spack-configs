.. Copyright (c) 2026, Lawrence Livermore National Security, LLC and
.. other RADIUSS Project Developers. See the top-level COPYRIGHT file.
.. SPDX-License-Identifier: (MIT)

Use CI
======

A project's CI runs the developer workflow against its source checkout. RADIUSS
Spack Configs supplies shared ``SPEC`` jobs, the project supplies its build/test
command and custom jobs, and `RADIUSS Shared CI
<https://radiuss-shared-ci.readthedocs.io/en/latest/>`_ supplies versioned GitLab
components for machine execution, allocations, and reporting.

.. graphviz:: /figures/consumer-ci.dot
   :align: center
   :caption: Consumer CI combines shared specifications, project settings, and a selected CI component.
   :alt: Shared jobs and project settings feed pipeline composition. The selected Shared CI component revision provides execution. The generated child pipeline runs the project preparation, build, and test driver with SPEC.

RADIUSS Spack Configs also has its own CI to :doc:`validate Spack environments
<../ci_implementation/index>`.

.. _consumer-shared-jobs:

Compose shared and project jobs
-------------------------------

In the RAJA integration, a generation job combines
``scripts/radiuss-spack-configs/gitlab/radiuss-jobs/dane.yml`` and
``.gitlab/jobs/dane.yml`` into a ``dane-jobs.yml`` artifact. The child pipeline
includes the selected Shared CI machine component, project custom jobs, and
that artifact. RAJA passes its build/test script through the component's
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
whenever updating the RADIUSS Spack Configs submodule: a renamed or changed shared
job may invalidate the override. Temporary ``allow_failure: true`` exceptions
should have a tracked cause and a removal condition.

Use maintained host configurations with rad-bat
------------------------------------------------

A project using :doc:`rad_bat` can keep one job definition for both ordinary
CI and dependency refresh. Each maintained job stores its ``SPEC`` beside a
stable ``RAD_BAT_HOST_CONFIG_NAME``. With ``RAD_BAT_MODE`` unset, the inputs
select the workflow:

.. list-table:: Environment-driven mode selection
   :header-rows: 1
   :widths: 25 30 45

   * - ``SPEC``
     - Host-config selector
     - Selected mode
   * - Set
     - Unset
     - Spack
   * - Unset
     - Set
     - Host-config
   * - Set
     - Set
     - Host-config
   * - Unset
     - Unset
     - Error

A selector is a direct ``RAD_BAT_HOST_CONFIG`` or legacy ``HOST_CONFIG``, or a
``RAD_BAT_HOST_CONFIG_NAME`` resolved below ``RAD_BAT_HOST_CONFIG_DIR``. Empty
values count as unset. An explicit ``RAD_BAT_MODE=host-config`` or
``RAD_BAT_MODE=spack`` overrides inference but still requires that mode's
inputs. Each job logs which inputs are set and the selected mode without
printing their values.

This convention gives maintained jobs a fast ordinary path while preserving
Spack behavior for a new ``SPEC``-only job. A missing selected host
configuration is an error and never triggers Spack implicitly.

Refresh maintained host configurations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Start a new pipeline explicitly with ``RAD_BAT_MODE=spack`` to regenerate the full
maintained set. The existing jobs concretize their specs, install dependencies
into a project-owned immutable generation, and publish generated host
configurations as GitLab artifacts. Download and review the artifacts, then
commit them to the project's ``host-configs/`` directory through the normal
GitHub pull-request workflow. The GitLab mirror is not modified by the
pipeline, and generated files never overwrite tracked files automatically.

Give each pipeline/job-name pair a persistent workspace. Retries reuse its
concrete environment and completed dependencies. A new workspace allows new
inputs, but does not force rebuilding packages available from upstreams or
binary caches.

``rad-bat`` does not infer staleness or compare fingerprints. Such a check
would require concretization merely to decide whether concretization can be
skipped and would still be incomplete for moving targets. Intentionally
dynamic jobs should select Spack mode explicitly. Buildcache publication is
also explicit through ``RAD_BAT_PUSH_TO_BUILDCACHE``.

Connect rad-bat to Shared CI
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Pass ``scripts/radiuss-spack-configs/bin/rad-bat`` as the machine component's
opaque ``job_cmd``. When executing from the submodule, set ``PYTHONPATH`` to
the submodule root because Flux may copy the launcher into its spool directory
while the separate ``rad_bat`` package remains in the project checkout.

rad-bat loads ``MODULE_LIST`` before preparing dependencies or invoking the
project command. A Shared CI component may also load modules needed by its
scheduler launcher. The reproducer must preserve the variable and allocation.
Project CI retains ownership of resource flags, specs, storage paths, and the
project driver. See :doc:`../maintainer_guide/rad_bat` for this boundary and
scheduler descriptor handling.

Reproduce a CI failure
----------------------

When reporting a failure, include the project commit,
``git submodule status --recursive`` output, ``.rad-bat.json``, machine,
selected mode, expanded ``SPEC``, host-config name,
and failing command. This information identifies the
source, tools, and settings needed to reproduce the failure. In a compute allocation, run the
:ref:`project build/test script <write-ci-script>` or the failing rad-bat,
Spack, CMake, or CTest command. See :doc:`how_to` for narrowing the failure.
