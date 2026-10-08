"""Assemble only redistributable prebuilt code; never include Minecraft or saves."""
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def archive(entries):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, content in sorted(entries.items()):
            item = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            item.external_attr = 0o644 << 16
            z.writestr(item, content)
    return output.getvalue()


def as_json(value):
    return (json.dumps(value, indent=2, ensure_ascii=False)+'\n').encode('utf8')


def main():
    from build_native import build
    output = ROOT/'dist'
    info = json.loads((output/'build-info.json').read_text(encoding='utf8'))
    # Select the exact Gradle version; never accidentally bundle a previous build.
    jar = ROOT/'minecraft/build/libs'/f"skycraft-{info['mod_version']}.jar"
    api = ROOT/'minecraft/build/release-mods'/f"fabric-api-{info['fabric_api']}.jar"
    if not jar.is_file() or not api.is_file():
        raise SystemExit('Run Gradle build copyReleaseMods with -Pversion matching dist/build-info.json first')
    with zipfile.ZipFile(jar) as z:
        mod = json.loads(z.read('fabric.mod.json'))
        if mod['version'] != info['mod_version']:
            raise ValueError('Built Minecraft mod version mismatch')
    mods = {f"mods/mciblender-{info['channel']}-v{info['identity']}.jar": jar.read_bytes(),
            'mods/'+api.name: api.read_bytes()}
    licenses = {'LICENSE': (ROOT/'LICENSE').read_bytes(),
                'THIRD-PARTY-NOTICES.md': (ROOT/'THIRD-PARTY-NOTICES.md').read_bytes(),
                'licenses/SkyCraft-MIT.txt': (ROOT/'licenses/SkyCraft-MIT.txt').read_bytes()}
    pack = archive({
        'modrinth.index.json': as_json({'formatVersion': 1, 'game': 'minecraft',
            'versionId': info['identity'], 'name': 'MCInBlender',
            'summary': 'Minecraft simulation for the MCInBlender Blender host (Windows x64).',
            'files': [], 'dependencies': {'minecraft': info['minecraft'], 'fabric-loader': info['fabric_loader']}}),
        **{'overrides/'+name: data for name, data in mods.items()},
        'overrides/mciblender-build-info.json': as_json(info),
        **{'overrides/mciblender-licenses/'+name: data for name, data in licenses.items()}})
    addon_entries = {'blender_minecraft/'+p.name: p.read_bytes() for p in (ROOT/'blender_minecraft').glob('*.py')}
    addon_entries.update({'blender_minecraft/bin/mc_atomic.dll': build().read_bytes(),
                          'blender_minecraft/build-info.json': as_json(info),
                          'blender_minecraft/resources/minecraft.mrpack': pack,
                          **{'blender_minecraft/'+name: data for name, data in licenses.items()}})
    # Blender's legacy add-on metadata supports a tuple of version integers.
    init = addon_entries['blender_minecraft/__init__.py'].decode('utf8')
    init = init.replace("'version':(0,1,0)", "'version':"+str(tuple(map(int, info['version'].split('.')))))
    addon_entries['blender_minecraft/__init__.py'] = init.encode('utf8')
    addon = archive(addon_entries)
    names = {'addon': info['stem']+'-addon.zip', 'pack': info['stem']+'-minecraft.mrpack',
             'bundle': info['stem']+'-bundle.zip'}
    bundle = archive({names['addon']: addon, names['pack']: pack, 'build-info.json': as_json(info),
                      'INSTALL.md': (ROOT/'docs/INSTALL.md').read_bytes(),
                      'USAGE.md': (ROOT/'docs/USAGE.md').read_bytes(), **licenses, **mods})
    products = {names['addon']: addon, names['pack']: pack, names['bundle']: bundle}
    for name, data in products.items():
        (output/name).write_bytes(data)
    sums = ''.join(f'{hashlib.sha256(data).hexdigest()}  {name}\n' for name, data in sorted(products.items()))
    (output/'SHA256SUMS.txt').write_text(sums, encoding='utf8')
    print('\n'.join(products))


if __name__ == '__main__':
    main()
