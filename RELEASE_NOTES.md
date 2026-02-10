# v2026.02.0

Recommended Spack version: v1.1.0,
Required spack-packages commit: 3f482a6fca

## Packages
- BREAKING: moved local packages to upstream spack/spack-packages Updates of
  the radiuss packages should not be pushed directly to spack/spack-packages.
  Reference to spack-packages was updated accordingly.  We kept the structure
  for a local repository for temporary testing purpose only.

- With the update of the spack-packages reference, some changes happened in
  radiuss packages (latest releases, updated dependencies...). Please refer to
  spack-packages history for more details.

## Configs Update
- Added rocprofiler external for Caliper

# v2025.11.1

Recommended Spack version: v1.0.2,
Vetted spack-packages commit: a229f54670

## Packages
- BLT:
    - patch googletest with fix for oneapi 2025 (change in flag name).

# v2025.11.0

Recommended Spack version: v1.0.2,
Vetted spack-packages commit: a229f54670

## Packages
- Camp:
    - add release 2025.12
- Care:
    - better constraints on umpire raja and chai dependencies (protect from c++ standard mix up)
- CHAI:
    - better constraints on umpire and raja dependencies (protect from c++ standard mix up)
- quandary:
    - add version 4.3
- RAJA:
    - better constraints on camp (protect from c++ standard mix up)
    - add conflict with cuda 13:
    - add rocprim 7 requires c++17.
- RAJAPerf:
    - add release 2025.03 which requires blt 7
    - add rocprim7 requires c++17.
- Umpire:
    - better constraints on camp (protect from c++ standard mix up)
    - add conflict with cuda 13:.
- Do not use dirname to infer rocm root from llvm-amdgpu prefix

## Configs Update
- Corona:
    - gcc 13
    - oneapi 2025
    - sycl clang 22 custom install
    - llvm-amdgpu 6.4.2
- Dane:
    - gcc 13
    - llvm 19
    - oneapi 2025
    - llvm 14 gcc 13 toolchain
    - llvm 18 gcc 13 toolchain
    - llvm 19 gcc 13 toolchain
- Matrix:
    - gcc 13
    - llvm 14 gcc 11 toolchain
    - llvm 18 gcc 13 toolchain
- Tioga:
    - Add cce 20
- Tuolumne:
    - Add cce 20
- Use rocm root as prefix for llvm-amdgpu

## CI
- Matrix: update to cuda_arch 90.

## Shared specs:
- llvm 14 -> llvm 19
- oneapi 2023 -> oneapi 2025
- gcc 10 -> gcc 13
- gcc 11 -> gcc 13
- cce 19 -> cce 20
- sycl clang 20 -> sycl clang 22

# v2025.10.0

Recommended Spack version: v1.0.2
Vetted spack-packages commit: a3806d96d2

## Machine Changes
- Retire Lassen
- Add Matrix for CUDA jobs

## Packages
- Update RAJA CMake requirement to 3.24+ for versions 2025.09.0 and later
- Add CMake 3.25.2 to available external packages

## Configs Update
- Add Matrix machine configuration (toss_4_x86_64_ib)
- Add LLVM 18.1.8 compiler to non-CUDA machines
- Add CUDA externals to Dane (non-GPU machine) for cross-compilation compatibility with Matrix, enabling optimized builds for Matrix architecture

## CI
- Add Matrix to CI pipeline (but turn it off)
- Update CI configurations for Matrix and Dane
- Fix spec list configuration in shared CI environment

# v2025.09.1

Recommended Spack version: v1.0.2
Vetted spack-packages commit: a3806d96d2

## Packages
- Add latest release of some RADIUSS packages.
- Style changes.

## Configs
- Add sycl compiler tied to rocm 6.3.1.

## CI
- Allow to deactivate a CI machine by variable.

# v2025.09.0

Recommended Spack version: 1.0.2:
Vetted spack-packages commit: a3806d96d2

Update Spack configurations to v1 format
- Remove compilers.yaml
- Move compiler definition to packages.yaml
- Create appropriate toolchains
Update most packages with 2025.09 release.
Add support for spack-packages repository set from environment

Retire Ruby

Update CI configuration
Use CI reservation on Dane

Add patches for Caliper

# v2025.06.0

Recommended Spack version: branch rsc-2025-03-0

## Configs Update
- Add rocm 6.4.1 and cce 19.0.0 (cray machines)
- Update gcc to 13.3.1, update mpich to 8.1.32 (cray machines)
- Update cuda to 11.8.0 and add 12.2.0 (cray machines)
- Support running on Dane and Tuolumne
- Check external packages on every machine (expect lassen), update when necessary

## CI
- Replace Poodle with Dane in CI
- Mention CI capabilities in documentation

## Others
- Add utilities to help with spack configs updates
- Improve ordering of externals in packages.yaml files
- Update copyright
- Fix naming convention

# v2025.03.0

Recommended Spack version: branch rsc-2025-03-0

## Add CI
- We add a GitLab CI pipeline leveraging Spack CI to test building some packages with our shared specs.

## Packages Update
- add 2025.03.0 releases for Camp, Umpire, RAJA, CHAI, and 0.15 releases for CARE.
- clean hip support

## Configs Update
- Updated rocm 6.3.0 to 6.3.1 on tioga
- Cleaned older rocm toolchains

## Shared CI jobs
- Updated specs to prepare spack@1.0.0: variants must be applied before compiler

## CI
- Force concretization
- Point at spack internal mirror to reduce firewall traffic

# v2025.01.0

Recommended Spack version: develop-2025-01-12

## Packages Update
- Update Care package with 0.14.x releases and C++17 requirements.
- Update sycl
- Split spack environment file in separate files (access packages.yaml and compilers.yaml directly)
- Update external specs with latest available version on each machine.
- Make config more consistent with what Axom is using (goal: build axom with RSC).
- Add rocrand, rocsparse, rocthurst for hypre builds.
- Add lowopttest variant in RAJA and RAJAPerf for Intel CI checks
- Apply workarounds to enforce using a single compiler for a packages and its dependencies
- Update rocm tioga toolchain: add rocm 6.3.0, remove rocm 5.4.1, 5.7.0 and 6.1.1
- Add compiler rpaths when necessary (mimics LC wrappers, prevent from tweaking spack packages)
- Rename intel to oneapi when relevant
- Sync with Spack@develop of January 12 2025

## Configs Update
- Use llvm-amdgpu to determine ROCM_PATH (utility function in camp package).
- Add intel 2024.

## Shared CI jobs

# v2024.09.0

Recommended Spack version: develop-2024-10-06

## Packages Update
- Add 2024.07 versions to packages
- Turn CARE and Caliper into CachedCMakePackages
- Improve coherency in version constraints
- Various updates from upstream Spack.

## Configs Update
- Add rocm 6.2.0 on Tioga
- Drop rocm 5.7.0 in favor of 5.7.1 on corona
- Enforce coherency between rocm software stack and compiler

## Shared CI jobs
- Remove XL jobs
