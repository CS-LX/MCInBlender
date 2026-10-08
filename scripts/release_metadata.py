"""One version policy for local packages, CI prereleases and four-part tags."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
VERSION_RE = r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)'


def metadata(version, sha, ref='refs/heads/main'):
    if not re.fullmatch(VERSION_RE, version):
        raise ValueError('VERSION must have four numeric components, for example 0.1.0.0')
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('Expected a full Git commit SHA')
    stable = ref.startswith('refs/tags/')
    if stable and ref != 'refs/tags/v'+version:
        raise ValueError('Release tag must exactly match v + VERSION (four numeric components)')
    if not stable and ref != 'refs/heads/main':
        raise ValueError('Publishing is restricted to main and version tags on main')
    channel = 'release' if stable else 'ci'
    identity = version if stable else version+'+g'+sha[:8]
    major, minor, patch, revision = version.split('.')
    mod_version = f'{major}.{minor}.{patch}+rev.{revision}' + ('' if stable else f'.g{sha[:8]}')
    return {'version': version, 'identity': identity, 'channel': channel, 'sha': sha,
            'mod_version': mod_version, 'tag': 'v'+version if stable else 'ci-v'+identity,
            'stem': f'MCInBlender-{channel}-v{identity}-windows-x64',
            'minecraft': '26.3', 'fabric_loader': '0.19.5', 'fabric_api': '0.161.0+26.3',
            'blender_minimum': '5.0.0', 'protocol': 11}


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ref', default=os.environ.get('GITHUB_REF', 'refs/heads/main'))
    ap.add_argument('--sha', default=os.environ.get('GITHUB_SHA'))
    ap.add_argument('--check-main', action='store_true')
    args = ap.parse_args()
    info = metadata((ROOT/'VERSION').read_text().strip(), args.sha or git('rev-parse', 'HEAD'), args.ref)
    if args.check_main:
        subprocess.run(['git', 'merge-base', '--is-ancestor', info['sha'], 'origin/main'], cwd=ROOT, check=True)
    out = ROOT/'dist'
    out.mkdir(exist_ok=True)
    (out/'build-info.json').write_text(json.dumps(info, indent=2)+'\n', encoding='utf8')
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf8') as stream:
            for key in ('channel', 'identity', 'tag', 'stem', 'mod_version'):
                stream.write(f'{key}={info[key]}\n')
    print(json.dumps(info))


if __name__ == '__main__':
    main()
