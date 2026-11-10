"""Small helpers executed by the pinned Spack's Python interpreter."""

import argparse
import json
from pathlib import Path


def write_manifest(path, data, yaml):
    temporary = Path(path).with_suffix('.yaml.tmp')
    with temporary.open('w') as stream:
        yaml.dump_config(data, stream)
    temporary.replace(path)


def override(mapping, name, value):
    import spack.util.spack_yaml as sy

    mapping.pop(name, None)
    key = sy.syaml_str(name)
    key.override = True
    mapping[key] = value


def repositories(options):
    import spack.util.spack_yaml as sy

    manifest = Path(options['environment']) / 'spack.yaml'
    with manifest.open() as stream:
        data = sy.load_config(stream)
    # JSON entries take precedence, retaining repositories from the machine manifest.
    configured = dict(options['repos'])
    for name, repo in data['spack'].get('repos', {}).items():
        configured.setdefault(name, repo)
    data['spack']['repos'] = configured
    write_manifest(manifest, data, sy)


def prepare(options):
    import spack.util.spack_yaml as sy

    manifest = Path(options['environment']) / 'spack.yaml'
    with manifest.open() as stream:
        data = sy.load_config(stream)
    config = data['spack']

    # CI generation is replaced by the environment install workflow.
    config['include'] = [x for x in config.get('include', []) if x != 'ci.yaml']
    config.pop('ci', None)
    config['view'] = False
    override(config, 'repos', config.get('repos', {}))
    if not config['repos']:
        raise ValueError('Supply pinned package repositories in spack.yaml')
    for name, repo in config['repos'].items():
        if isinstance(repo, dict) and 'git' in repo and not repo.get('commit'):
            raise ValueError('Pin package repository {} by commit'.format(name))
    cfg = config.setdefault('config', {})
    override(cfg, 'build_stage', ['$user_cache_path/stage'])
    cfg['test_stage'] = '$user_cache_path/test'
    cfg['misc_cache'] = '$user_cache_path/misc'
    cfg['source_cache'] = options['source_cache']
    override(config, 'bootstrap', {'root': options['bootstrap']})
    if options.get('group'):
        config.setdefault('packages', {}).setdefault('all', {})['permissions'] = {
            'read': 'world', 'write': 'group', 'group': options['group']}
    write_manifest(manifest, data, sy)


def disable_autopush():
    """Honor success-gated publication even when included configs enable autopush."""
    import spack.config
    import spack.environment as ev
    import spack.util.spack_yaml as sy

    mirrors = spack.config.get('mirrors', {})
    for name, mirror in list(mirrors.items()):
        if isinstance(mirror, str):
            mirror = {'url': mirror}
            mirrors[name] = mirror
        mirror['autopush'] = False
    manifest = Path(ev.active_environment().path) / 'spack.yaml'
    with manifest.open() as stream:
        data = sy.load_config(stream)
    override(data['spack'], 'mirrors', mirrors)
    write_manifest(manifest, data, sy)


def freeze():
    import spack.environment as ev
    import spack.repo
    import spack.util.spack_yaml as sy

    manifest = Path(ev.active_environment().path) / 'spack.yaml'
    with manifest.open() as stream:
        data = sy.load_config(stream)
    override(data['spack'], 'repos', {r.namespace: r.root for r in spack.repo.PATH.repos})
    write_manifest(manifest, data, sy)


def installed():
    import spack.environment as ev
    import spack.store

    environment = ev.active_environment()
    roots = list(environment.concrete_roots())
    if not roots:
        raise ValueError('The environment has no concrete roots')
    if sorted(str(s) for s in environment.user_specs) != sorted(
            str(s) for s, _ in environment.concretized_specs()):
        raise ValueError('Concrete lock does not match the selected root specs')
    with spack.store.STORE.db.read_transaction():
        # Cached packages can legitimately omit their build-only dependencies.
        for root in roots:
            for spec in root.traverse(deptype=('link', 'run')):
                if not spec.external and not spec.installed:
                    raise ValueError('Required installation missing: {}'.format(spec))
        return ['/' + spec.dag_hash() for spec in environment.all_specs()
                if spec.installed and not spec.external]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest='action', required=True)
    actions.add_parser('prepare').add_argument('path', type=Path)
    actions.add_parser('repositories').add_argument('options', type=json.loads)
    actions.add_parser('verify').add_argument('path', type=Path)
    actions.add_parser('freeze')
    actions.add_parser('disable-autopush')
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare(json.loads(args.path.read_text()))
    elif args.action == 'repositories':
        repositories(args.options)
    elif args.action == 'disable-autopush':
        disable_autopush()
    elif args.action == 'freeze':
        freeze()
    else:
        args.path.write_text(json.dumps(installed()))


if __name__ == '__main__':
    main()
