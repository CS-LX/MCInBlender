"""Publish this exact build; channel comes from validated Git metadata."""
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
out = ROOT/'dist'
info = json.loads((out/'build-info.json').read_text())
tag = info['tag']
notes = out/'release-notes.md'
notes.write_text(f'''MCInBlender {info['identity']} ({info['channel']})

Windows x64 · Blender 5.0+ · Minecraft {info['minecraft']} · Java 25.

Download **{info['stem']}-bundle.zip** for the add-on, precompiled Minecraft mods,
importable MRPACK and installation instructions. No compiler or Gradle is needed.
The separate `-addon.zip` is installed directly in Blender. Import `-minecraft.mrpack`
in Prism/HMCL, then launch the game through that launcher with your Minecraft account.

Minecraft, Java, account data and saves are not included. First import downloads
Minecraft/Fabric through your launcher. This version is Windows x64 only.

[中文安装](https://github.com/CS-LX/MCInBlender/blob/{info['sha']}/docs/INSTALL.md) ·
[使用说明](https://github.com/CS-LX/MCInBlender/blob/{info['sha']}/docs/USAGE.md) ·
[Known limitations](https://github.com/CS-LX/MCInBlender/blob/{info['sha']}/docs/STATUS.md)

Source commit: `{info['sha']}`. Protocol: {info['protocol']}.
SHA-256 checksums and machine-readable build metadata are attached.
''', encoding='utf8')
existing = subprocess.run(['gh', 'release', 'view', tag], cwd=ROOT, capture_output=True).returncode == 0
if not existing:
    command = ['gh', 'release', 'create', tag, '--target', info['sha'],
               '--title', f"MCInBlender {info['identity']} · {info['channel']}", '--notes-file', str(notes)]
    if info['channel'] == 'ci':
        command += ['--prerelease', '--latest=false']
    else:
        command += ['--verify-tag', '--latest']
    subprocess.run(command, cwd=ROOT, check=True)
assets = sorted(out.glob(info['stem']+'*.zip')) + sorted(out.glob(info['stem']+'*.mrpack'))
assets += [out/'SHA256SUMS.txt', out/'build-info.json']
subprocess.run(['gh', 'release', 'upload', tag, *map(str, assets), '--clobber'], cwd=ROOT, check=True)
