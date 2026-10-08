"""Real GPU atlas and culling regression; A/B timing in the loaded Blender scene.

Use launch.py --verification performance --world normal --blend FILE.
Results remain local under artifacts/performance/. Leaves the session running.
"""
import json
import struct
import sys
import time
from pathlib import Path
import bpy
import gpu
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import bootstrap_blender
import blender_minecraft as addon
from blender_minecraft.renderer import ViewportRenderer, texture

output = ROOT/'artifacts/performance'
output.mkdir(parents=True,exist_ok=True)
for name in ('complete.json','failed.json','tests.json'):
    (output/name).unlink(missing_ok=True)
results = []
phase = 0
phase_time = time.monotonic()
draw_request = None
handle = None
saved_view = None


def record(name, **evidence):
    results.append({'name':name,'passed':True,'evidence':evidence})
    (output/'tests.json').write_text(json.dumps(results,indent=2))
    print('PASS',name,evidence,flush=True)


def pixels(buffer, width, height):
    buffer.dimensions = (width*height*4,)
    return np.asarray(buffer.to_list(),dtype=np.uint8).reshape(height,width,4)


def draw_checks():
    global draw_request
    if not draw_request or not addon.SESSION or not addon.SESSION.correct_context():
        return
    request,draw_request = draw_request,None
    try:
        s = addon.SESSION
        if request == 'atlas':
            renderer = ViewportRenderer()
            expected = np.arange(16*16*4,dtype=np.uint8).reshape(16,16,4)
            renderer.textures[0] = texture(16,16,expected.tobytes())
            patches = []
            for x,y,w,h in [(0,0,4,3),(6,2,5,6),(12,12,4,4)]:
                tile = np.zeros((h,w,4),dtype=np.uint8)
                tile[:,:,:] = [31+x*7,201-y*5,127,255]
                patches.append(struct.pack('<IIII',x,y,w,h)+tile.tobytes())
                expected[y:y+h,x:x+w] = tile
            renderer.patch_atlas_batch(patches)
            actual = pixels(renderer.textures[0].read(),16,16)
            assert np.array_equal(expected,actual), f'Atlas pixels differ: {np.abs(actual.astype(int)-expected).max()}'
            record('Batched GPU atlas upload preserves exact RGBA pixels and untouched texels',tiles=len(patches))
        else:
            offscreen = gpu.types.GPUOffScreen(640,400)
            images = []
            viewport = gpu.state.viewport_get()
            try:
                with offscreen.bind():
                    gpu.state.viewport_set(0,0,640,400)
                    for enabled in (False,True):
                        gpu.state.active_framebuffer_get().clear(color=(0,0,0,0),depth=1)
                        s.renderer.draw_world(bpy.context,s.player,show_selection=False,culling=enabled,upload_overlay=False)
                        raw = gpu.state.active_framebuffer_get().read_color(0,0,640,400,4,0,'UBYTE')
                        images.append(pixels(raw,640,400))
                difference = np.abs(images[0].astype(int)-images[1].astype(int))
                assert np.count_nonzero(images[0][:,:,3])>1000, 'Empty comparison image'
                assert difference.max()<=1, f'Culling changed visible pixels: {difference.max()}, count {np.count_nonzero(difference)}'
                record('Culling preserves rendered pixels: '+request,max_channel_difference=int(difference.max()),
                       visible_sections=s.renderer.performance['visible_sections'],cached_sections=len(s.renderer.sections))
            finally:
                gpu.state.viewport_set(*viewport)
                offscreen.free()
    except Exception as exc:
        fail(exc)


def fail(exc):
    global phase
    phase = -1
    (output/'failed.json').write_text(json.dumps({'error':repr(exc),'results':results},indent=2))
    print('FAIL performance verification',repr(exc),flush=True)


def frame():
    global phase,phase_time,draw_request,saved_view
    try:
        s = addon.SESSION
        now = time.monotonic()
        elapsed = now-phase_time
        if phase<0:
            return None
        if elapsed>180:
            raise TimeoutError(f'Performance phase {phase}')
        if not s or not s.player or not s.player.in_world or not s.renderer.sections:
            return 0.25
        if s.errors:
            raise AssertionError(s.errors)
        rv = s.space.region_3d
        if phase == 0:
            if elapsed<65 or len(s.renderer.pending)>8:
                return 0.25
            saved_view = (rv.view_perspective,rv.view_rotation.copy(),rv.view_location.copy(),rv.view_distance)
            s.scene.mciblender.camera_view = 'BLENDER'
            draw_request = 'atlas'
        elif phase == 1:
            if draw_request:
                return 0.25
            draw_request = 'perspective'
        elif phase == 2:
            if draw_request:
                return 0.25
            rv.view_perspective = 'ORTHO'
        elif phase == 3:
            if elapsed<1:
                return 0.25
            draw_request = 'orthographic'
        elif phase == 4:
            if draw_request:
                return 0.25
            rv.view_perspective,rv.view_rotation,rv.view_location,rv.view_distance = saved_view
            s.scene.mciblender.frustum_culling = False
            s.renderer.frame_samples.clear()
        elif phase == 5:
            if elapsed<18:
                return 0.25
            record('Culling disabled timing sample',**s.renderer.profile())
            s.scene.mciblender.frustum_culling = True
            s.renderer.frame_samples.clear()
        elif phase == 6:
            if elapsed<18:
                return 0.25
            record('Culling enabled timing sample',**s.renderer.profile())
            (output/'complete.json').write_text(json.dumps({'passed':len(results),'results':results},indent=2))
            bpy.types.SpaceView3D.draw_handler_remove(handle,'WINDOW')
            return None
        phase += 1
        phase_time = now
        s.area.tag_redraw()
        return 0.25
    except Exception as exc:
        fail(exc)
        return None


handle = bpy.types.SpaceView3D.draw_handler_add(draw_checks,(),'WINDOW','POST_VIEW')
bpy.app.timers.register(frame,first_interval=2)
