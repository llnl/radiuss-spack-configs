
.. ##
.. ## Copyright (c) 2022-25, Lawrence Livermore National Security, LLC and
.. ## other RADIUSS Project Developers. See the top-level COPYRIGHT file for
.. ## details.
.. ##
.. ## SPDX-License-Identifier: (MIT)
.. ##

.. _CI Implementation:

#################
CI Implementation
#################

In this repository, we configured GitLab CI to generate CI pipelines that can
build any Spack environment we provide.

We rely on `Spack Pipeline feature <https://spack.readthedocs.io/en/latest/pipelines.html>`_
to generate the CI pipeline.

Each CI pipeline run corresponds to the build of *one* Spack environment. The
environment being built is configured by the variable ``MY_ENV_NAME`` in CI
context. This variable must match a directory in ``.gitlab/spack/envs`` and
defaults to the value "shared-ci": an environment meant to build several
RADIUSS projects using the shared Spack specs.

.. note:: The shared Spack specs can be found in each
   ``gitlab/radiuss-jobs/<machine>.yml`` file. The specs there have been copied
   to the ``shared-ci/spack.yml`` file. Maintaining coherency between both is
   important for the quality of our CI.

The intent of the default configuration is to test that changes in
radiuss-spack-configs does not affect our projects. However, the CI can be set
to build other environments, which will allow us to test larger environments on
a less frequent basis, and to track changes in Spack as well.

Incidentally, this CI setup will populate a buildcache with pre-built binaries
of our RADIUSS projects, which could prove useful to developers willing to
save build time for the selected specs.

Persistent CI storage is written under a ``CACHE_TARGET`` namespace. The
default branch writes to ``main`` and other branch pipelines write to
``ref-<commit-ref-slug>``. Each namespace has its own persistent Spack install
tree and filesystem buildcache under ``SPACK_CI_STORAGE_ROOT``. Non-main
pipelines also configure the ``main`` install tree as a Spack upstream and the
``main`` buildcache as a read mirror, so they can reuse existing binaries
without publishing experimental builds into the default branch namespace.
A dedicated cleanup job removes stale ``ref-*`` storage targets corresponding
to branch references already merged into ``main``. The job scans all configured
environments under
``SPACK_CI_STORAGE_ROOT`` and is gated by two explicit variables:
``MY_ENV_NAME == ""`` and ``RSC_CLEANUP == "ON"``. This makes cleanup opt-in,
so regular branch pipelines (including ``develop``) do not trigger cleanup by
default. The intended usage is a scheduled pipeline configured with those
variables.

By default, ``SPACK_CI_STORAGE_ROOT`` points to the RADIUSS workspace. The
storage setup configures Spack package permissions with ``read: world``,
``write: group``, and ``group: SPACK_CI_STORAGE_GROUP`` so install tree
contents remain writable by the RADIUSS group. It also applies the storage
group to the persistent cache directories, marks those directories setgid, and
sets a group-writable umask so buildcache entries and other files written under
the persistent storage root remain accessible to members of the RADIUSS group.

The install tree is the fast path used by Spack during installation, while the
filesystem buildcache gives Spack CI the mirror metadata it needs to prune
already-built specs during pipeline generation.

The Spack checkout itself is a third storage layer. It is kept under
``MY_SPACK_PARENT_DIR`` on ``/dev/shm`` and reused by all jobs for the same
machine and pipeline, so the CI does not clone Spack separately for every build
job. In contrast, the Spack user cache is computed at job runtime and includes
the GitLab job id, so each job gets its own staging, test, and misc cache
locations under ``/dev/shm``. This keeps parallel Spack jobs isolated while the
checkout and persistent binary/install storage remain shared where useful.


=================
CI file structure
=================

Main CI pipeline
================

The root file for CI implementation with GitLab is ``.gitlab-ci.yml``. In this
file, we only define general variables and the list of stages. Then we include
the files that will actually describe our pipelines.

The additional CI files are found under the ``.gitlab`` directory. There, the
``variables.yml`` file sets variable for the different LC machines we run CI on,
namely ``corona``, ``dane``, ``matrix``, ``tioga`` and ``tuolumne``. The
pipelines for each machine is described in the corresponding ``<machine>.yml``
file.

``spack/envs/<MY_ENV_NAME>/pipeline.yml`` must be defined for each environment
and provide the Spack repo and commit to fetch (``MY_SPACK_REPO``,
``MY_SPACK_COMMIT``), and include the pipeline files for each machine to run
on. I.e., for each environment, we can chose a specific Spack version and the
list of machines.

Machine pipelines
=================

In each ``<machine>.yml`` file, we describe a pipeline that will allocate
resource for the CI on the machine, and then generate and trigger a CI pipeline
to build each required spec as a separate job.

Pipeline generation is handle by spack (see `Spack documentation`_ for more
about the CI feature) and is configured in ``.gitlab/spack/ci.yaml`` and
other files in that directory.

Scripts
=======

Scripts used by the main CI configuration are located in ``.gitlab/scripts``
while scripts used for Spack specific operations (typically occurring when
generating the sub-pipelines or while running them) are located in
``.gitlab/spack``.

.. note:: We ensure to separate the scripts files from the CI configuration.
   This helps with testing, keeping the CI files readable, and reproducing the
   CI process outside of CI context.

Spack Pipeline Feature
======================

To learn more about the Spack Pipeline feature used in this CI configuration,
it is a good idea to first read the dedicated `Spack documentation`_.



.. _Spack documentation: https://spack.readthedocs.io/en/latest/pipelines.html
