#!/usr/bin/env python3
"""Audit a concrete stack environment: spack python check-stack-coherence.py.

Requirements on language/MPI virtuals are checked against every recorded edge,
including build dependencies. Externals without compiler edges have unknown
provenance and are counted separately. This is a selection check, not an ABI test.
"""
import shlex

import spack.config
import spack.environment as ev
from spack.spec import Spec
from spack.traverse import traverse_nodes


def main():
    environment = ev.active_environment()
    if environment is None:
        raise SystemExit("Activate a concrete Spack environment first.")
    errors = []
    root_count = 0
    for group in environment.manifest.groups():
        roots = [spec for _, spec in environment.concretized_specs_by(group=group)]
        if not roots:
            continue
        root_count += len(roots)
        with environment.config_override_for_group(group=group):
            packages = spack.config.get("packages")
            providers = {}
            for virtual in ("c", "cxx", "fortran", "mpi"):
                requirements = packages.get(virtual, {}).get("require", [])
                if len(requirements) != 1 or not isinstance(requirements[0], str):
                    errors.append(f"{group}: expected one explicit {virtual} provider requirement")
                    continue
                providers[virtual] = Spec(requirements[0])
            bindings, unknown = 0, set()
            for node in traverse_nodes(roots):
                recorded = False
                for edge in node.edges_to_dependencies():
                    for virtual in edge.virtuals:
                        if virtual not in providers:
                            continue
                        recorded = True
                        bindings += 1
                        if not edge.spec.satisfies(providers[virtual]):
                            errors.append(f"{group}: {node.name} uses {virtual}={edge.spec}, expected {providers[virtual]}")
                        # Pairing flags live on compiler metadata so package.require cannot erase them.
                        flag = {"c": "cflags", "cxx": "cxxflags", "fortran": "fflags"}.get(virtual)
                        if flag and not node.external:
                            externals = packages.get(edge.spec.name, {}).get("externals", [])
                            for external in externals:
                                if not edge.spec.satisfies(Spec(external["spec"])):
                                    continue
                                required_flags = external.get("extra_attributes", {}).get("flags", {}).get(flag, "")
                                actual = list(node.compiler_flags.get(flag, []))
                                if any(f not in actual for f in shlex.split(required_flags)):
                                    errors.append(f"{group}: {node.name} is missing compiler {flag}: {required_flags}")
                if node.external and not recorded:
                    unknown.add(node.name)
                if node.name.endswith("-runtime"):
                    for requirement in packages.get(node.name, {}).get("require", []):
                        if isinstance(requirement, str) and not node.satisfies(Spec(requirement)):
                            errors.append(f"{group}: {node} violates runtime requirement {requirement}")
            selected = ", ".join(f"{v}={s}" for v, s in providers.items())
            print(f"Stack {group}: {len(roots)} roots, {bindings} checked bindings; {selected}")
            print(f"  Externals without recorded language/MPI bindings: {', '.join(sorted(unknown)) or 'none'}")
    if not root_count:
        errors.append("No concrete roots found; concretize the environment before checking it.")
    if errors:
        raise SystemExit("Stack coherence check failed:\n" + "\n".join(errors))
    print("Stack coherence check passed.")


if __name__ == "__main__":
    main()
