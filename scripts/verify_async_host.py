"""Isolated UI/timer smoke; never connects to the user's Minecraft session."""
import json
import os
from pathlib import Path
import sys
import time
import traceback
import bpy
bpy.context.preferences.view.show_splash = False

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import blender_minecraft as addon
from blender_minecraft import host
from blender_minecraft.transport import HostLink

host.HostLink = lambda: HostLink(name='Local\\MCInBlender_AsyncSmoke_'+str(os.getpid()))
addon.register()
# Draw the real panel in the default visible tab of this isolated test window.
# Region.active_panel_category is read-only in Blender 5.
from blender_minecraft.operators import Panel
bpy.utils.unregister_class(Panel)
Panel.bl_category = 'Item'
bpy.utils.register_class(Panel)
area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
region = next(r for r in area.regions if r.type == 'WINDOW')
window = bpy.context.window
output = ROOT/'artifacts/async-host'
output.mkdir(parents=True, exist_ok=True)
(output/'result.json').unlink(missing_ok=True)
phase = 0
started = time.monotonic()
last = started
gaps = []
result = {}

# A moderately dense mesh makes progress observable across multiple UI frames.
with bpy.context.temp_override(window=window, area=area, region=region):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=5, radius=8)
    base = bpy.context.object
    for i in range(12):
        obj = base.copy()
        obj.location.x = i*20
        bpy.context.scene.collection.objects.link(obj)
    area.spaces.active.show_region_ui = True
    area.spaces.active.shading.type = 'SOLID'


def check():
    global phase, last, started
    try:
        now = time.monotonic()
        with bpy.context.temp_override(window=window, area=area, region=region):
            if phase == 0:
                before = time.perf_counter()
                assert bpy.ops.mciblender.start() == {'FINISHED'}
                result['start_ms'] = round((time.perf_counter()-before)*1000, 2)
                assert addon.SESSION.collision.building
                assert result['start_ms'] < 1000, result
                started = last = time.monotonic()
                phase = 1
            elif phase == 1:
                gaps.append(now-last)
                last = now
                if now-started > 0.7:
                    result['progress'] = addon.SESSION.collision.status()
                    assert result['progress']['busy']
                    assert addon.SESSION.tick_count > 5
                    bpy.ops.screen.screenshot(filepath=str(output/'progress.png'))
                    before = time.perf_counter()
                    assert bpy.ops.mciblender.stop() == {'FINISHED'}
                    result['stop_ms'] = round((time.perf_counter()-before)*1000, 2)
                    assert addon.SESSION is None
                    phase = 2
            elif phase == 2:
                assert bpy.ops.mciblender.start() == {'FINISHED'}
                assert bpy.ops.mciblender.cancel_collision() == {'FINISHED'}
                assert addon.SESSION.collision.cancelled
                assert addon.SESSION.collision_paused
                assert bpy.ops.mciblender.rebuild() == {'FINISHED'}
                assert addon.SESSION.collision.building and not addon.SESSION.collision_paused
                assert bpy.ops.mciblender.stop() == {'FINISHED'}
                for obj in list(bpy.data.objects):
                    bpy.data.objects.remove(obj, do_unlink=True)
                bpy.ops.mesh.primitive_cube_add(size=1)
                assert bpy.ops.mciblender.start() == {'FINISHED'}
                started = time.monotonic()
                phase = 3
            elif phase == 3:
                assert now-started < 15, 'Collision export kept restarting after completion'
                if addon.SESSION.collision.busy or now-started < 2:
                    return 0.03
                assert not addon.SESSION.errors, addon.SESSION.errors
                assert addon.SESSION.collision_rebuilds <= 1
                result['settled_rebuilds'] = addon.SESSION.collision_rebuilds
                assert bpy.ops.mciblender.stop() == {'FINISHED'}
                result['max_ui_timer_gap_ms'] = round(max(gaps)*1000, 2)
                assert result['max_ui_timer_gap_ms'] < 750, result
                result['passed'] = True
                (output/'result.json').write_text(json.dumps(result, indent=2))
                print('ASYNC_HOST_PASS '+json.dumps(result), flush=True)
                bpy.ops.wm.quit_blender()
                return None
        return 0.03
    except Exception:
        result['error'] = traceback.format_exc()
        (output/'result.json').write_text(json.dumps(result, indent=2))
        print(result['error'], flush=True)
        bpy.ops.wm.quit_blender()
        return None


bpy.app.timers.register(check, first_interval=1)
