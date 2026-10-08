"""Live Minecraft -> native Eevee lighting, framebuffer and lifecycle checks.

Run launch.py --only blender --world normal --blend FILE --verification lighting.
Uses a white native sphere and an isolated test-world block near the fusion arena.
"""
import json
import sys
import time
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector
from bpy_extras.view3d_utils import location_3d_to_region_2d

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import bootstrap_blender
import blender_minecraft as addon
from blender_minecraft.native_lighting import TAG,COLLECTION_TAG

output = ROOT/'artifacts/lighting'
output.mkdir(parents=True,exist_ok=True)
for name in ('complete.json','failed.json','tests.json'):
    (output/name).unlink(missing_ok=True)
results,samples = [],{}
sphere = None


def record(name,**evidence):
    results.append({'name':name,'passed':True,'evidence':evidence})
    (output/'tests.json').write_text(json.dumps(results,indent=2))
    print('PASS',name,evidence,flush=True)


def wait(predicate,timeout=60):
    start = time.monotonic()
    while not predicate():
        if time.monotonic()-start>timeout:
            raise TimeoutError(f'Lighting check after {len(results)} completed tests')
        yield


def delay(seconds):
    start = time.monotonic()
    yield from wait(lambda:time.monotonic()-start>=seconds,seconds+5)


def command(s,text):
    s.command(text)
    yield from wait(lambda:not s.commands and s.renderer.environment.get('screen')=='')
    yield from delay(1)


def sample(name):
    # Let native Eevee shaders and temporal sampling settle after scene changes.
    yield from delay(4)
    path = str(output/(name+'.png'))
    bpy.ops.screen.screenshot(filepath=path)
    s = addon.SESSION
    point = location_3d_to_region_2d(s.region,s.space.region_3d,sphere.location)
    assert point is not None
    # POST_PIXEL's active framebuffer contains overlays only in Eevee. Read the
    # final window composite, which also includes the native material pass.
    image = bpy.data.images.load(path,check_existing=False)
    try:
        w,h = image.size
        raw = np.empty(w*h*4,dtype=np.float32)
        image.pixels.foreach_get(raw)
        x,y = s.region.x+round(point.x),s.region.y+round(point.y)
        samples[name] = (raw.reshape(h,w,4)[y-8:y+9,x-8:x+9,:3].mean(axis=(0,1))*255).tolist()
    finally:
        bpy.data.images.remove(image)


def signature(scene):
    return [{'name':o.name,'matrix':[list(r) for r in o.matrix_world],
             'vertices':len(o.data.vertices) if o.type=='MESH' else None,
             'modifiers':[(m.name,m.type) for m in o.modifiers],
             'materials':[m.material.name if m.material else None for m in o.material_slots]}
            for o in sorted(scene.objects,key=lambda o:o.name) if not o.get(TAG)]


def checks():
    global sphere
    yield from wait(lambda:addon.SESSION and addon.SESSION.player and addon.SESSION.player.in_world and
                    addon.SESSION.renderer.environment.get('screen')=='' and
                    addon.SESSION.renderer.lightmap_samples and len(addon.SESSION.renderer.sections)>200,120)
    s = addon.SESSION
    s.scene.mciblender.camera_view = 'BLENDER'
    with bpy.context.temp_override(window=s.window,area=s.area,region=s.region):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=48,ring_count=24,radius=0.7,location=(19.5,-0.5,103.2))
        sphere = bpy.context.object
        sphere.name = 'Native lighting test sphere'
        bpy.ops.object.shade_smooth()
    material = bpy.data.materials.new('Native lighting test white')
    material.diffuse_color = (0.65,0.65,0.65,1)
    material.use_nodes = True
    material.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value = (0.65,0.65,0.65,1)
    material.node_tree.nodes.get('Principled BSDF').inputs['Roughness'].default_value = 0.65
    sphere.data.materials.append(material)
    original = signature(s.scene)
    world = s.scene.world
    world_color = tuple(world.color) if world else None
    shading = s.space.shading
    shading.type = 'SOLID'
    shading.use_scene_lights = False
    shading.use_scene_world = False
    rv = s.space.region_3d
    target,eye = Vector((19.5,-0.5,102.5)),Vector((24,-10,106))
    rv.view_rotation = (target-eye).to_track_quat('-Z','Y')
    rv.view_location = target
    rv.view_distance = (target-eye).length
    rv.view_perspective = 'PERSP'
    s.space.overlay.show_overlays = False
    s.space.lens = 48
    yield from command(s,'weather clear')
    yield from command(s,'setblock 18 104 2 minecraft:air')
    yield from command(s,'fill 21 103 5 22 105 5 minecraft:air')
    yield from command(s,'time set noon')
    s.scene.mciblender.native_lighting = True
    yield from wait(lambda:s.native_lighting.active and s.native_lighting.summary.get('sun_energy',0)>1)
    yield from sample('day')
    assert shading.type=='MATERIAL' and shading.use_scene_lights and shading.use_scene_world
    assert s.space.overlay.show_overlays and not s.space.overlay.show_extras
    assert sum(samples['day'])>60,samples['day']
    assert signature(s.scene)==original
    record('Minecraft day lights native model without replacing its material',rgb=samples['day'],**s.native_lighting.summary)

    yield from command(s,'time set midnight')
    yield from wait(lambda:s.native_lighting.summary.get('sun_energy',1)==0 and
                    s.native_lighting.summary.get('moon_energy',0)>0)
    yield from sample('night')
    assert sum(samples['day'])>sum(samples['night'])*1.2,(samples['day'],samples['night'])
    record('Native framebuffer follows the actual Minecraft day/night transition',day=samples['day'],night=samples['night'])

    yield from command(s,'setblock 18 104 2 minecraft:glowstone')
    yield from wait(lambda:[18,104,2] in s.native_lighting.summary.get('sources',[]))
    yield from sample('warm-block')
    assert sum(samples['warm-block'])>sum(samples['night'])*1.1,(samples['warm-block'],samples['night'])
    record('Placing a Minecraft emitter visibly illuminates the native model',night=samples['night'],warm=samples['warm-block'])

    yield from command(s,'setblock 18 104 2 minecraft:soul_lantern')
    yield from wait(lambda: s.native_lighting.objects()['Block 18,104,2'].data.color[2]>
                    s.native_lighting.objects()['Block 18,104,2'].data.color[0])
    yield from sample('cool-block')
    record('Changing emitter updates native light color',rgb=samples['cool-block'],
           light_color=list(s.native_lighting.objects()['Block 18,104,2'].data.color))

    yield from command(s,'setblock 18 104 2 minecraft:air')
    yield from wait(lambda:[18,104,2] not in s.native_lighting.summary.get('sources',[]))
    yield from sample('removed-block')
    assert abs(sum(samples['removed-block'])-sum(samples['night']))<50,(samples['removed-block'],samples['night'])
    record('Removing emitter removes native point light',rgb=samples['removed-block'])

    # Deleting generated helpers in the Outliner must recover without reference errors.
    bpy.data.collections.remove(s.native_lighting.collection)
    yield from delay(1)
    assert s.native_lighting.collection.name in bpy.data.collections
    assert len(s.native_lighting.objects())>=3
    record('Deleted helper collection recovers on the next update')

    path = output/'Native Models and Minecraft Lighting.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(path),copy=True)
    with bpy.data.libraries.load(str(path),link=False) as (source,destination):
        assert not any(name.startswith('Minecraft Sun') or name.startswith('Minecraft Moon') or
                       name.startswith('Minecraft Block ') for name in source.objects),source.objects
        assert sphere.name in source.objects
    yield from wait(lambda:s.native_lighting.active)
    assert signature(s.scene)==original
    assert s.scene.world==world and (tuple(world.color) if world else None)==world_color
    record('Scene save excludes runtime light helpers and preserves native data',file=str(path))

    yield from command(s,'time set noon')
    yield from command(s,'fill 21 103 5 22 105 5 minecraft:red_wool')
    yield from sample('occluded-native')
    red,green,blue = samples['occluded-native']
    assert red>green*1.6 and red>blue*1.6,samples['occluded-native']
    yield from command(s,'fill 21 103 5 22 105 5 minecraft:air')
    yield from sample('uncovered-native')
    assert samples['uncovered-native'][0]<samples['uncovered-native'][1]*1.3,samples['uncovered-native']
    record('Minecraft wall and native material model share correct depth',
           wall=samples['occluded-native'],model=samples['uncovered-native'])

    saved_view = (rv.view_rotation.copy(),rv.view_location.copy(),rv.view_distance,rv.view_perspective,s.space.lens)
    for mode,expected in [('FIRST',0),('THIRD_BACK',1),('THIRD_FRONT',2)]:
        s.scene.mciblender.camera_view = mode
        yield from wait(lambda:s.player.camera_mode==expected and s.space.overlay.show_overlays and
                        not s.space.overlay.show_extras)
        yield from delay(2)
        bpy.ops.screen.screenshot(filepath=str(output/(mode.lower()+'.png')))
        assert s.renderer.performance.get('draw_calls',0)>20
    s.scene.mciblender.camera_view = 'BLENDER'
    rv.view_rotation,rv.view_location,rv.view_distance,rv.view_perspective,s.space.lens = saved_view
    yield from delay(1)
    record('All follow cameras retain Minecraft rendering in Material Preview')

    s.scene.mciblender.native_lighting = False
    yield from wait(lambda:not s.native_lighting.active)
    assert not any(o.get(TAG) for o in s.scene.objects)
    assert shading.type=='SOLID' and not shading.use_scene_lights and not shading.use_scene_world
    assert not s.space.overlay.show_overlays
    assert signature(s.scene)==original
    record('Disabling restores viewport preferences and leaves native models intact')

    s.scene.mciblender.native_lighting = True
    yield from wait(lambda:s.native_lighting.active)
    sections_before = len(s.renderer.sections)
    with bpy.context.temp_override(window=s.window,area=s.area,region=s.region):
        bpy.ops.mciblender.stop()
        assert not any(o.get(TAG) for o in s.scene.objects)
        assert shading.type=='SOLID'
        bpy.ops.mciblender.start()
    yield from wait(lambda:addon.SESSION and addon.SESSION.native_lighting.active)
    yield from wait(lambda:0 in addon.SESSION.renderer.textures and len(addon.SESSION.renderer.environment_textures)==5
                    and len(addon.SESSION.renderer.sections)>=sections_before*0.95,90)
    yield from wait(lambda:addon.SESSION.renderer.performance.get('draw_calls',0)>100)
    assert signature(addon.SESSION.scene)==original
    record('Stopping and reconnecting restores full world, atlas and temporary lights',
           sections_before=sections_before,sections_after=len(addon.SESSION.renderer.sections),
           textures=len(addon.SESSION.renderer.textures))
    yield from command(addon.SESSION,'time set noon')
    (output/'complete.json').write_text(json.dumps({'passed':len(results),'samples':samples,'results':results},indent=2))
    print('PASS native lighting verification',flush=True)


workflow = checks()


def frame():
    try:
        if addon.SESSION and addon.SESSION.errors:
            raise AssertionError(addon.SESSION.errors)
        next(workflow)
        return 0.2
    except StopIteration:
        return None
    except Exception as exc:
        (output/'failed.json').write_text(json.dumps({'error':repr(exc),'results':results,'samples':samples},indent=2))
        import traceback
        traceback.print_exc()
        return None


bpy.app.timers.register(frame,first_interval=2)
