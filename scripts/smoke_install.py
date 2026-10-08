"""CI install/enable test in an isolated Blender user profile, using official binaries."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import shutil
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = '5.0.1'
NAME = f'blender-{VERSION}-windows-x64.zip'
URL = f'https://download.blender.org/release/Blender5.0/{NAME}'


def download(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'MCInBlender-Build/0.1'}), timeout=60)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--blender', type=Path)
    args = ap.parse_args()
    blender = args.blender
    if not blender:
        cache = ROOT/'.cache'/'blender-ci'
        cache.mkdir(parents=True, exist_ok=True)
        checksum_url = f'https://download.blender.org/release/Blender5.0/blender-{VERSION}.sha256'
        with download(checksum_url) as response:
            checksums = response.read().decode()
        expected = next(line.split()[0] for line in checksums.splitlines() if line.rstrip().endswith(NAME))
        package = cache/NAME
        if not package.exists():
            temp = package.with_suffix('.tmp')
            with download(URL) as response, temp.open('wb') as stream:
                shutil.copyfileobj(response, stream)
            temp.replace(package)
        if hashlib.sha256(package.read_bytes()).hexdigest() != expected:
            raise ValueError('Official Blender package SHA-256 mismatch')
        with zipfile.ZipFile(package) as archive:
            archive.extractall(cache)
        blender = cache/f'blender-{VERSION}-windows-x64'/'blender.exe'
    info = json.loads((ROOT/'dist/build-info.json').read_text())
    profile = ROOT/'.local'/'package-smoke'
    env = os.environ.copy()
    for name, folder in [('BLENDER_USER_CONFIG', 'config'), ('BLENDER_USER_SCRIPTS', 'scripts')]:
        path = profile/folder
        path.mkdir(parents=True, exist_ok=True)
        env[name] = str(path)
    result = subprocess.run([str(blender), '--background', '--python-exit-code', '1',
        '--python', str(ROOT/'scripts/install_addon.py'), '--',
        str(ROOT/'dist'/(info['stem']+'-addon.zip'))], env=env, cwd=ROOT, check=True,
        capture_output=True, text=True, encoding='utf8', errors='replace')
    print(result.stdout)
    if 'MCIBLENDER_INSTALLED ' not in result.stdout:
        raise RuntimeError('Blender did not confirm installation')


if __name__ == '__main__':
    main()
