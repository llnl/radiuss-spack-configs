# `rad-bat` design

## Purpose

`rad-bat` (RADIUSS Builds And Tests) is a reusable replacement for the
combination of Uberenv and project-specific CI orchestration scripts. Its goal
is to make the fast path through RADIUSS CI cheap and predictable while keeping
dependency refreshes explicit and reproducible.

The tool is maintained directly in `radiuss-spack-configs`. Projects that
already carry that repository as a submodule can run it without installing a
Python package or adding another submodule.

The first adopters are Umpire and RAJA. The design also accounts for the build
and test sequences in Axom, Smith, CHAI, CARE, Caliper, and RAJAPerf.

## Decisions

### Interface and implementation

- The user-facing executable is `rad-bat`.
- The Python package is `rad_bat`, configuration is `.rad-bat.json`, and
  tool-specific environment variables use the `RAD_BAT_` prefix.
- Python 3.8 or newer and the standard library are the only runtime
  requirements.
- JSON is used for project configuration because Python supports it natively
  and commands can be represented as argument arrays without embedding shell.
- Project-specific build and test behavior remains one independently runnable
  executable. `rad-bat` selects the host-config and prepares dependencies, then
  invokes that executable.
- A configured command is an argv array. Arguments following `--` replace the
  configured command.
- Substitutions are allowed only when the complete argument is a placeholder.
  The initial placeholders are `{host_config}`, `{dest}`, `{source}`, and
  `{jobs}`. Partial string interpolation is rejected.

### Explicit operating modes

There are two modes and no automatic mode in the initial implementation:

```text
rad-bat host-config --host-config PATH [--dest PATH] [--jobs N]
    [--source PATH] [-- COMMAND...]

rad-bat spack --spec SPEC --dest PATH
    [--spack-env PATH]
    [--upstream PATH ...]
    [--buildcache URL]
    [--push-to-buildcache]
    [--host-config-name NAME]
    [--jobs N] [--source PATH]
    [-- COMMAND...]

rad-bat ci
```

`host-config` never invokes Spack. It validates the selected host-config and
runs the project command. Its default destination is an ignored, project-local
work directory so the developer workflow remains convenient.

`spack` requires an explicit destination. It prepares a pinned Spack instance,
concretizes the requested spec, builds dependencies through the package's
`initconfig` phase, retains the generated host-config, and runs the same project
command.

`ci` translates CI environment variables to one of the normal modes. New
tool-specific settings use `RAD_BAT_*`; the migration adapter may accept the
established `HOST_CONFIG`, `SPEC`, and `MODULE_LIST` job inputs while project
job definitions are converted.

### Host-config policy

- The ordinary CI path uses a maintained, job-specific host-config and does not
  invoke Spack or concretize.
- Each CI job keeps its `SPEC` beside the host-config selection as the recipe
  used to regenerate it.
- Manual or scheduled dependency-refresh jobs use `spack` mode. They leave the
  generated host-config in the destination for review and manual promotion into
  the project's tracked `host-configs/` directory.
- Generated host-configs never overwrite tracked files automatically.
- Moving dependency references, multi-project builds, refresh jobs, and other
  intentionally dynamic configurations explicitly use `spack` mode.
- `rad-bat` does not infer whether a host-config is stale. This avoids an
  implicit concretization merely to decide whether concretization can be
  skipped, and avoids incomplete moving-target detection.

This policy deliberately follows the model used by Smith and Axom: a
host-config freezes dependencies for the common CI path, while an explicit
refresh updates that frozen state. The difference is that `rad-bat` provides a
shared native-Spack refresh path rather than project-specific Uberenv wrappers.

### Native Spack behavior

- `rad-bat` never silently uses `spack` from `PATH`.
- The Spack source URL and a full commit are recorded in project configuration.
  The initial development pin is
  `2a4c87fd44bd303643c0b0e0d7ed6fe1d1a23937`.
- Remote package repositories are pinned to full commits. Local repositories,
  including the RADIUSS package repository, are registered in an explicit
  precedence order.
- Existing RADIUSS machine environments remain the source of compiler,
  external-package, and machine policy.
- The implementation uses native Spack environments, `spack develop
  --no-clone`, `spack isolate`, and `spack install --until initconfig`.
- `spack isolate` modifies configuration inside its Spack checkout. Therefore
  the checkout is tool-managed and stored separately from dependency install
  trees. Replacing a Spack pin must not remove installed dependencies.
- A writable destination cannot be shared by concurrent refresh jobs. CI uses
  scheduler/resource-group serialization for a shared refresh destination.
  Ordinary builds consume published install trees as read-only upstreams.

### Dependency reuse and publication

- Persistent filesystem install trees and Spack upstreams are the primary
  dependency-reuse mechanism.
- A `spack` run may read from an optional filesystem or OCI buildcache.
- Publishing to a buildcache requires `--push-to-buildcache`; reads never imply
  writes.
- A push publishes dependencies only, never the project-under-development.
- A multi-project-triggered refresh may populate the shared upstream. This is
  an intended use, provided writes to that destination are serialized.

### Project boundary

`rad-bat` owns:

- CLI and configuration validation;
- pinned Spack download/update;
- isolation and environment creation;
- repository, upstream, install-tree, and buildcache configuration;
- dependency installation and host-config discovery;
- safe command substitution and process execution;
- shared command/severity logging, nested GitLab sections, timing, and logging
  context propagation to project drivers;
- top-level diagnostics and exit-code propagation.

Each project executable owns its lifecycle and project-specific artifacts.
For Umpire, the initial Python driver declares the configure, build, install,
CTest/JUnit, benchmark, installed-example, and verbose-retry phases using the
shared `rad_bat.logs` API. RAJA uses the same logging API and general lifecycle
with its own exceptions.

Other projects can retain their existing drivers. Axom can pass the selected
host-config to `build_src.py`; Smith can adapt its Python wrapper. Their docs,
tutorials, ATS, examples, and benchmark phases remain project-owned. RAJAPerf's
performance execution and artifacts likewise remain outside the generic tool.

## `radiuss-shared-ci` integration

No new `rad-bat` GitLab component is introduced. Existing machine components
continue treating `job_cmd` as an opaque command, for example:

```text
scripts/radiuss-spack-configs/bin/rad-bat ci
```

One shared-CI change is required: the machine component loads `MODULE_LIST` in
the submitting shell before invoking `srun` or `flux batch`. Slurm and Flux then
propagate that prepared environment to `job_cmd`. The emitted reproducer must
perform the same module initialization and load before its scheduler command.

Thus the responsibility split is:

```text
radiuss-shared-ci:
    initialize/load modules -> print reproducer -> launch opaque job_cmd

rad-bat:
    select workflow -> prepare/reuse dependencies -> invoke project driver
```

No Spack, host-config, caching, or project-build policy belongs in
`radiuss-shared-ci`.

## Configuration model

The project root contains `.rad-bat.json` with schema version 1. It records:

- the project package name;
- the default project command as an argv array;
- the exact Spack URL and commit;
- the RADIUSS machine-environment location;
- ordered local or pinned remote package repositories.

A representative shape is:

```json
{
  "schema_version": 1,
  "project": {
    "package": "umpire",
    "command": [
      "python3",
      "scripts/gitlab/build_and_test.py",
      "--host-config", "{host_config}",
      "--dest", "{dest}",
      "--source", "{source}",
      "--jobs", "{jobs}"
    ]
  },
  "spack": {
    "url": "https://github.com/spack/spack.git",
    "commit": "2a4c87fd44bd303643c0b0e0d7ed6fe1d1a23937",
    "environment": "scripts/radiuss-spack-configs/{sys_type}/spack.yaml",
    "repositories": [
      {
        "path": "scripts/radiuss-spack-configs/spack_repo/llnl_radiuss"
      },
      {
        "url": "https://github.com/spack/spack-packages.git",
        "commit": "4d3d0f8ee5ffd6f099727f46ec704f3f4ee98e5c",
        "subdirectory": "repos/spack_repo/builtin"
      }
    ]
  }
}
```

Paths in the file are resolved relative to the project root. A remote
repository must include both `url` and a full `commit`; `subdirectory` selects
the Spack repository within a remote monorepo. The project configuration, not a
moving Spack default, pins the built-in `spack-packages` repository.

## Rollout

1. Implement and unit-test `rad_bat` in a fresh `radiuss-spack-configs` branch.
2. Implement module loading and matching reproducer output in a fresh
   `radiuss-shared-ci` branch.
3. Integrate Umpire from a fresh `develop` branch without modifying the existing
   experimental `woptim/ci-spack-optimized` worktree.
4. Validate CPU, CUDA, and HIP canaries in both modes.
5. Remove Umpire's Uberenv integration only after the canaries pass.
6. Integrate RAJA from a fresh `develop` branch.
7. Evaluate Axom and Smith adoption through their existing Python drivers.

## Verification

- Unit-test schema and CLI validation, whole-argument substitution, CI variable
  translation, exact Git checkout handling, and diagnostics.
- Use a fake Spack executable for command-order, failure, upstream, buildcache,
  and host-config-discovery tests.
- Prove that `host-config` mode cannot invoke Spack.
- Exercise a real native-Spack environment through `initconfig`.
- Verify that changing the Spack pin preserves dependency install trees.
- Verify dependency-only buildcache publication is impossible without the
  explicit push flag.
- Verify `MODULE_LIST` is loaded before Slurm and Flux launch and that generated
  reproducers contain the equivalent setup.
- Run Umpire CPU, CUDA, and HIP CI canaries before replacing the current path.
- Run each project driver independently of `rad-bat`.
