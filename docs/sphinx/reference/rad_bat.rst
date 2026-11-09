.. Copyright (c) 2026, Lawrence Livermore National Security, LLC and
.. other RADIUSS Project Developers. See the top-level COPYRIGHT file.
.. SPDX-License-Identifier: (MIT)

rad-bat reference
=================

Command line
------------

The repository-local entry point supports two subcommands. With no arguments,
it translates environment variables into one of the same workflows.

.. code-block:: text

   rad-bat host-config --host-config PATH [--work-dir PATH]
       [--source PATH] [--jobs N] [-- COMMAND...]

   rad-bat spack --spec SPEC --work-dir PATH
       [--spack-env PATH] [--install-tree PATH] [--output-dir PATH]
       [--upstream PATH ...] [--buildcache URL]
       [--buildcache-username-variable NAME]
       [--buildcache-password-variable NAME]
       [--push-to-buildcache] [--host-config-name NAME]
       [--source PATH] [--jobs N] [-- COMMAND...]

``--source`` selects the project root containing ``.rad-bat.json``. Relative
paths in the command and configuration resolve from that root. Arguments after
``--`` replace ``project.command`` for that run.

The direct ``spack`` command defaults its install tree and output directory
below the work directory. Environment-driven CI execution requires an explicit
persistent install tree. ``--host-config-name`` must be a filename ending in
``.cmake`` without a directory component.

Project configuration
---------------------

Schema version 1 is a JSON object stored at the project root as
``.rad-bat.json``. This representative configuration uses placeholder commit
values; a real configuration records full tested commits.

.. code-block:: json

   {
     "schema_version": 1,
     "project": {
       "package": "my-project",
       "command": [
         "python3",
         "scripts/gitlab/build_and_test.py",
         "--host-config", "{host_config}",
         "--work-dir", "{work_dir}",
         "--source", "{source}",
         "--jobs", "{jobs}"
       ]
     },
     "spack": {
       "url": "https://github.com/spack/spack.git",
       "commit": "0123456789abcdef0123456789abcdef01234567",
       "environment": "scripts/radiuss-spack-configs/{sys_type}/spack.yaml",
       "spec_fragments": [
         {
           "if_env": "DEPENDENCY_REFERENCE",
           "value": "^dependency@git.{DEPENDENCY_REFERENCE}=main"
         }
       ],
       "repositories": [
         {"path": "scripts/spack_repo/project"},
         {
           "url": "https://github.com/spack/spack-packages.git",
           "commit": "89abcdef0123456789abcdef0123456789abcdef",
           "subdirectory": "repos/spack_repo/builtin"
         }
       ]
     }
   }

.. list-table:: Configuration fields
   :header-rows: 1
   :widths: 35 65

   * - Field
     - Meaning
   * - ``project.package``
     - Spack package name. Spack mode creates an explicit
       ``<package>@develop`` root and develops it from the project source.
   * - ``project.command``
     - Non-empty argument array for the project driver. Supported
       whole-argument placeholders are ``{host_config}``, ``{work_dir}``,
       ``{source}``, and ``{jobs}``; partial interpolation is rejected.
   * - ``spack.url`` and ``spack.commit``
     - Managed Spack checkout and full 40-character commit.
   * - ``spack.environment``
     - Machine environment path. ``{sys_type}`` is replaced with ``SYS_TYPE``.
   * - ``spack.repositories``
     - Ordered local repositories, or remote repositories pinned by URL and
       full commit. ``subdirectory`` selects a repository inside a remote
       monorepo. Earlier entries have higher Spack precedence.
   * - ``spack.spec_fragments``
     - Optional environment-controlled dependency constraints.

A conditional spec fragment requires exactly ``if_env`` and ``value``. The
value must contain the matching ``{VARIABLE}`` placeholder. A non-empty
environment value substitutes and appends the fragment; an unset or empty
value appends nothing. Declaring a variable without this configuration entry
does not change the spec. The array permits independent dependency overrides
without project-specific behavior in ``rad-bat``.

Environment-driven execution
----------------------------

.. list-table:: CI variables
   :header-rows: 1
   :widths: 38 62

   * - Variable
     - Purpose
   * - ``RAD_BAT_MODE``
     - Optional explicit ``host-config`` or ``spack`` selection.
   * - ``RAD_BAT_SOURCE_DIR``
     - Project root; defaults to ``CI_PROJECT_DIR`` and then the current
       directory.
   * - ``RAD_BAT_JOBS``
     - Positive build parallelism; defaults to the detected CPU count.
   * - ``RAD_BAT_WORK_DIR``
     - Disposable work. Required in Spack mode and optional in host-config
       mode, where the default is ``.rad-bat-work`` below the project root.
   * - ``RAD_BAT_SPEC`` or ``SPEC``
     - Project spec fragment used by Spack mode.
   * - ``RAD_BAT_HOST_CONFIG`` or ``HOST_CONFIG``
     - Direct host-configuration path.
   * - ``RAD_BAT_HOST_CONFIG_NAME``
     - Stable ``.cmake`` filename. Host-config mode combines it with
       ``RAD_BAT_HOST_CONFIG_DIR``; Spack mode uses it for the retained output.
   * - ``RAD_BAT_SPACK_ENV``
     - Optional generated Spack environment location.
   * - ``RAD_BAT_INSTALL_TREE``
     - Persistent dependency installation tree required by environment-driven
       Spack mode.
   * - ``RAD_BAT_OUTPUT_DIR``
     - Host-configuration artifact directory.
   * - ``RAD_BAT_UPSTREAMS``
     - Platform path-separator-delimited Spack upstream install trees.
   * - ``RAD_BAT_BUILDCACHE``
     - Optional filesystem or OCI binary mirror used for reads.
   * - ``RAD_BAT_BUILDCACHE_USERNAME_VARIABLE`` and
       ``RAD_BAT_BUILDCACHE_PASSWORD_VARIABLE``
     - Names of credential environment variables passed to Spack. These values
       name variables; they are not credentials themselves.
   * - ``RAD_BAT_PUSH_TO_BUILDCACHE``
     - Boolean opt-in to publish dependencies. Legacy ``PUSH_TO_REGISTRY`` is
       accepted when the prefixed variable is absent.

With ``RAD_BAT_MODE`` unset, a host-config selector takes precedence over a
spec. A selector alone chooses host-config mode, a spec alone chooses Spack
mode, both choose host-config mode, and neither is an error. An explicit mode
still validates its required inputs. A missing host configuration never falls
back to Spack.

``RAD_BAT_LOG_START_TIME`` and ``RAD_BAT_LOG_DEPTH`` are internal logging
context propagated to project drivers that use ``rad_bat.logs``. Projects
should not set them as workflow inputs.
