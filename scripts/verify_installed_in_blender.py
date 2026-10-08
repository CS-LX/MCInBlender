"""Targeted live test of an installed package, not repository Python sources."""
import json
import os
from pathlib import Path
import time
import bpy
import blender_minecraft as addon
from blender_minecraft.paths import build_info, data_root

bpy.context.preferences.view.show_splash = False
phase = 0
started = time.monotonic()
deadline = started+180
before = None
output = Path(os.environ['MCIBLENDER_PACKAGE_EVIDENCE'])
output.mkdir(parents=True, exist_ok=True)
assert (Path(addon.__file__).parent/'build-info.json').is_file(), addon.__file__


def step():
    global phase, deadline, before
    try:
        if time.monotonic()>deadline:
            raise TimeoutError(f'Installed-package smoke phase {phase}')
        area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
        region = next(r for r in area.regions if r.type == 'WINDOW')
        with bpy.context.temp_override(area=area, region=region):
            if phase == 0:
                bpy.context.scene.mciblender.camera_view = 'FIRST'
                bpy.ops.mciblender.start()
                phase = 1
                return .2
            s = addon.SESSION
            if phase == 5 and s is None:
                (output/'result.json').write_text(json.dumps({
                    'passed': True, 'build': build_info(), 'installed_module': addon.__file__,
                    'checks': ['bundled DLL loaded', 'production JAR connected', 'world geometry and HUD',
                               'real Blender E key opened inventory', 'normal Minecraft save/exit']}, indent=2))
                print('PASS installed package gameplay smoke', flush=True)
                bpy.ops.wm.quit_blender()
                return None
            if not s:
                return .2
            if s.errors:
                raise AssertionError(s.errors)
            env = s.renderer.environment
            if phase == 1 and s.link.alive and s.player and s.player.in_world and len(s.renderer.sections)>1000 and s.renderer.overlay_frame:
                assert Path(s.link.atomic._name).parent == Path(addon.__file__).parent/'bin'
                assert env.get('vanilla') is True
                bpy.ops.mciblender.capture('INVOKE_DEFAULT')
                s.window.event_simulate(type='E', value='PRESS')
                before = time.monotonic()
                phase = 2
            elif phase == 2 and time.monotonic()-before>.2:
                s.window.event_simulate(type='E', value='RELEASE')
                phase = 3
            elif phase == 3 and env.get('screen') == 'InventoryScreen':
                bpy.ops.screen.screenshot(filepath=str(output/'installed-package-inventory.png'))
                s.window.event_simulate(type='E', value='PRESS')
                before = time.monotonic()
                phase = 4
            elif phase == 4 and time.monotonic()-before>.2:
                s.window.event_simulate(type='E', value='RELEASE')
                bpy.ops.mciblender.quit_game()
                deadline = time.monotonic()+45
                phase = 5
    except Exception as exc:
        (output/'result.json').write_text(json.dumps({'passed':False, 'phase':phase, 'error':str(exc)}, indent=2))
        print('FAIL installed package',repr(exc),flush=True)
        return None
    return .2


bpy.app.timers.register(step, first_interval=1)
