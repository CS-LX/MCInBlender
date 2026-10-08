"""Focused delivery checks: no build tools/game payloads, exact mod version, loadable DLL."""
import ctypes
import hashlib
import io
import json
from pathlib import Path
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    out = ROOT/'dist'
    info = json.loads((out/'build-info.json').read_text())
    for line in (out/'SHA256SUMS.txt').read_text().splitlines():
        digest, name = line.split('  ', 1)
        assert hashlib.sha256((out/name).read_bytes()).hexdigest() == digest, name
    addon_file = out/(info['stem']+'-addon.zip')
    with zipfile.ZipFile(addon_file) as addon:
        names = addon.namelist()
        assert all(n.startswith('blender_minecraft/') for n in names)
        assert not any(token in n.lower() for n in names for token in ('__pycache__', 'accounts', '/saves/', '/.git/'))
        assert json.loads(addon.read('blender_minecraft/build-info.json')) == info
        pack_data = addon.read('blender_minecraft/resources/minecraft.mrpack')
        assert pack_data == (out/(info['stem']+'-minecraft.mrpack')).read_bytes()
        with tempfile.TemporaryDirectory() as temp:
            dll_path = Path(temp)/'mc_atomic.dll'
            dll_path.write_bytes(addon.read('blender_minecraft/bin/mc_atomic.dll'))
            # PE machine type must be AMD64; loading exercises runtime dependencies.
            binary = dll_path.read_bytes()
            pe = int.from_bytes(binary[0x3c:0x40], 'little')
            assert binary[pe:pe+4] == b'PE\0\0' and binary[pe+4:pe+6] == b'\x64\x86'
            dll = ctypes.CDLL(str(dll_path))
            for name in ('mc_exchange32', 'mc_exchange64', 'mc_load64'):
                assert getattr(dll, name)
            ctypes.windll.kernel32.FreeLibrary.argtypes = [ctypes.c_void_p]
            ctypes.windll.kernel32.FreeLibrary(dll._handle)
    with zipfile.ZipFile(io.BytesIO(pack_data)) as pack:
        manifest = json.loads(pack.read('modrinth.index.json'))
        assert manifest['dependencies'] == {'minecraft': info['minecraft'], 'fabric-loader': info['fabric_loader']}
        jars = [n for n in pack.namelist() if n.endswith('.jar')]
        assert len(jars) == 2, jars
        assert any('/fabric-api-' in n for n in jars)
        bridge = next(n for n in jars if '/mciblender-' in n)
        with zipfile.ZipFile(io.BytesIO(pack.read(bridge))) as mod:
            assert json.loads(mod.read('fabric.mod.json'))['version'] == info['mod_version']
    print('PASS package hashes, payload allowlist, exact versions and Windows x64 DLL')


if __name__ == '__main__':
    main()
