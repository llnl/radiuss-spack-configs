"""Optional dependency tree from saved environment artifacts; never runs Spack.

Usage: python3 -m rad_bat.report /path/to/attempt-or-collected-artifacts
An unreported package is not inferred to have failed. Native reports may be
missing after interruption. This observer has no role in publication decisions.
"""

import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def dependency_report(directory):
    directory = Path(directory)
    lock = json.loads((directory / 'spack.lock').read_text())
    nodes = lock['concrete_specs']
    outcomes, diagnostics = {}, []
    for native in sorted(directory.glob('workers/*/native.xml')):
        try:
            for case in ET.parse(native).iter('testcase'):
                key = case.get('name')
                if key not in nodes:
                    continue
                state = ('failed' if case.find('failure') is not None or case.find('error') is not None
                         else 'skipped' if case.find('skipped') is not None else 'success')
                if outcomes.get(key) != 'failed':
                    outcomes[key] = state
        except ET.ParseError:
            diagnostics.append('Incomplete native report: {}'.format(native))
    # A completed verification is stronger evidence than per-worker skip records.
    if (directory / 'installed.json').exists():
        for key in json.loads((directory / 'installed.json').read_text()):
            outcomes[key.lstrip('/')] = 'installed'
    lines, seen = [], set()

    def visit(key, prefix='', branch=''):
        node = nodes[key]
        state = outcomes.get(key, 'external' if node.get('external') else 'unreported')
        repeated = key in seen
        lines.append('{}{}[{}] {}@{} /{}{}'.format(prefix, branch, state, node['name'],
                     node.get('version', '?'), key[:7], ' (shown above)' if repeated else ''))
        if repeated:
            return
        seen.add(key)
        children = node.get('dependencies', [])
        continuation = prefix + ('    ' if branch == '`-- ' else '|   ' if branch else '')
        for index, child in enumerate(children):
            visit(child['hash'], continuation, '`-- ' if index == len(children) - 1 else '|-- ')

    for root in lock['roots']:
        visit(root['hash'])
    return '\n'.join(lines + diagnostics) + '\n'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    print(dependency_report(parser.parse_args().directory), end='')
