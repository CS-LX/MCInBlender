"""Exercise the actual Save & Quit operator and preserve the Blender scene."""
import ctypes
import json
import struct
import sys
import time
from pathlib import Path
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import bootstrap_blender
import blender_minecraft as addon

output = ROOT/'artifacts/lifecycle'
output.mkdir(parents=True,exist_ok=True)
for name in ('complete.json','failed.json'):
    (output/name).unlink(missing_ok=True)
started = time.monotonic()
phase = 0
names = None
mc_pid = None
offset = 0
before = None


def alive(pid):
    kernel = ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes = [ctypes.c_uint32,ctypes.c_int,ctypes.c_uint32]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p,ctypes.c_uint32]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(0x00100000,False,pid)
    if not handle:
        return False
    try:
        return kernel.WaitForSingleObject(handle,0)==258
    finally:
        kernel.CloseHandle(handle)


def models(scene):
    return [{'name':o.name,'matrix':[list(row) for row in o.matrix_world],
             'vertices':len(o.data.vertices) if o.type=='MESH' else None,
             'modifiers':[(m.name,m.type) for m in o.modifiers],
             'materials':[slot.material.name if slot.material else None for slot in o.material_slots]}
            for o in sorted(scene.objects,key=lambda o:o.name)]


def frame():
    global phase,names,mc_pid,offset,before
    try:
        if time.monotonic()-started>120:
            raise TimeoutError(f'Lifecycle phase {phase}')
        s = addon.SESSION
        if phase == 0:
            if (not s or not s.link.alive or not s.player or not s.player.in_world or
                s.renderer.environment.get('screen')!='' or len(s.renderer.sections)<50):
                return 0.2
            assert not s.errors,s.errors
            names = models(s.scene)
            assert names,'Load a native model scene for this test'
            mc_pid = struct.unpack_from('<I',s.link.m,12)[0]
            assert alive(mc_pid)
            before = {'position':s.position,'inventory':s.renderer.environment.get('inventory'),'objects':names,'mc_pid':mc_pid}
            offset = (ROOT/'logs/minecraft-build.log').stat().st_size
            s.command('setblock -4 100 -4 minecraft:gold_block')
            phase = 1
        elif phase == 1:
            with (ROOT/'logs/minecraft-build.log').open(encoding='utf8',errors='replace') as stream:
                stream.seek(offset)
                messages = stream.read()
            if 'Changed the block at -4, 100, -4' not in messages and 'Could not set the block' not in messages:
                return 0.2
            with bpy.context.temp_override(window=s.window,area=s.area,region=s.region):
                result = bpy.ops.mciblender.quit_game()
                assert result=={'FINISHED'},result
            phase = 2
        elif phase == 2:
            if alive(mc_pid) or addon.SESSION is not None:
                return 0.2
            assert models(bpy.context.scene)==names
            log = (ROOT/'logs/minecraft-build.log').read_text(encoding='utf8',errors='replace')
            assert 'Saving players' in log and 'Saving worlds' in log
            result = {'passed':True,'operator':'mciblender.quit_game','minecraft_exited':True,
                      'blender_scene_retained':True,'before':before}
            (output/'complete.json').write_text(json.dumps(result,indent=2))
            print('PASS Save & Quit operator preserves native scene and Minecraft saves',flush=True)
            bpy.ops.wm.quit_blender()
            return None
        return 0.2
    except Exception as exc:
        (output/'failed.json').write_text(json.dumps({'phase':phase,'error':repr(exc)},indent=2))
        print('FAIL lifecycle',repr(exc),flush=True)
        return None


bpy.app.timers.register(frame,first_interval=2)
