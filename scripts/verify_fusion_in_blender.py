"""Blender-side live regression for modeling, collision and four camera choices.

Launch with launch.py --only blender --world normal --verification fusion while
the isolated Minecraft normal-world development client is running.
"""
import json
import sys
import time
from pathlib import Path
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import bootstrap_blender
import blender_minecraft as addon
from blender_minecraft import protocol as P

results = []
phase = 0
started = time.monotonic()
phase_started = started
obj = None
editor_location = None
command_offset = 0
free_view = None
walk_start = None
output = ROOT/'artifacts'/'fusion'
output.mkdir(parents=True,exist_ok=True)


def record(name, **evidence):
    results.append({'name':name,'passed':True,'evidence':evidence})
    (output/'tests.json').write_text(json.dumps(results,indent=2))
    print('PASS',name,evidence,flush=True)


def frame():
    global phase,phase_started,obj,editor_location,command_offset,free_view,walk_start
    try:
        s = addon.SESSION
        now = time.monotonic()
        if now-phase_started>90:
            raise TimeoutError(f'Fusion verification phase {phase} timed out')
        if not s or not s.player or not s.player.in_world or not s.renderer.sections:
            return 0.2
        if s.errors:
            raise AssertionError(s.errors)
        with bpy.context.temp_override(window=s.window,area=s.area,region=s.region):
            scene = bpy.context.scene
            if phase == 0:
                assert s.renderer.environment.get('vanilla'), 'Requires the normal-world development session'
                s.edit_view()
                rv = s.space.region_3d
                rv.view_location += Vector((3,4,5))
                rv.view_distance = 12
                editor_location = rv.view_location.copy()
                phase += 1
            elif phase == 1 and now-phase_started>1:
                assert (s.space.region_3d.view_location-editor_location).length<0.0001
                assert s.space.overlay.show_overlays and s.space.show_gizmo
                s.play_view()
                phase += 1
            elif phase == 2 and now-phase_started>1:
                assert (s.space.region_3d.view_location-editor_location).length>0.1
                s.edit_view()
                assert (s.space.region_3d.view_location-editor_location).length<0.0001
                record('Blender free view and tools survive play/edit round trip',editor_location=list(editor_location))
                bpy.ops.mesh.primitive_cube_add(size=1,location=P.mc_to_blender((10.5,101.5,0.5)))
                obj = bpy.context.object
                obj.name = 'Blender Live Modeling Platform'
                obj.scale = (4,4,1)
                obj['mc_collider'] = 'BOX'
                obj.color = (0.08,0.55,0.85,1)
                mat = bpy.data.materials.new('Blender Platform Blue')
                mat.diffuse_color = obj.color
                mat.use_nodes = True
                mat.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value = obj.color
                obj.data.materials.append(mat)
                s.command('gamemode survival')
                s.requested_position = (10.5,106,0.5)
                s.teleport += 1
                phase += 1
            elif phase == 3 and now-phase_started>2:
                if abs(s.position[1]-102)>0.05 or not s.player.flags&4:
                    return 0.2
                assert s.collision_rebuilds>0
                record('New native Blender mesh automatically becomes Minecraft ground',position=s.position,rebuilds=s.collision_rebuilds)
                obj.location.x += 9
                phase += 1
            elif phase == 4 and now-phase_started>2:
                if abs(s.position[1]-100)>0.05 or not s.player.flags&4:
                    return 0.2
                record('Moving native Blender mesh updates collision without restarting',position=s.position,rebuilds=s.collision_rebuilds)
                # A real Blender modifier remains editable and evaluates before collision export.
                bevel = obj.modifiers.new('Editable Blender Bevel','BEVEL')
                bevel.width = 0.15
                bevel.segments = 3
                del obj['mc_collider'] # default MESH: evaluated mesh volume, not an AABB proxy
                s.requested_position = (19.5,106,0.5)
                s.teleport += 1
                phase += 1
            elif phase == 5 and now-phase_started>2:
                if abs(s.position[1]-102)>0.05 or not s.player.flags&4:
                    return 0.2
                assert s.collision.mesh_volumes
                record('Evaluated Blender modifier mesh supports player collision',position=s.position,mesh_volumes=len(s.collision.mesh_volumes))
                s.command('kill @e[type=minecraft:cow,tag=mciblender_model_test]')
                s.command('summon minecraft:cow 19.5 105 0.5 {Tags:["mciblender_model_test"]}')
                phase += 1
            elif phase == 6 and now-phase_started>4:
                command_offset = (ROOT/'logs'/'minecraft-build.log').stat().st_size
                s.command('data get entity @e[type=minecraft:cow,tag=mciblender_model_test,limit=1] Pos')
                phase += 1
            elif phase == 7 and now-phase_started>2:
                with (ROOT/'logs'/'minecraft-build.log').open(encoding='utf8',errors='replace') as f:
                    f.seek(command_offset)
                    response = f.read()
                import re
                match = re.search(r'following entity data: \[([\d.-]+)d, ([\d.-]+)d, ([\d.-]+)d\]',response)
                if not match:
                    return 0.2
                cow_y = float(match.group(2))
                assert abs(cow_y-102)<0.2,match.group(0)
                record('Minecraft cow stands on generic Blender mesh volume',cow_y=cow_y,model_top=102)
                scene.mciblender.camera_view = 'THIRD_BACK'
                phase += 1
            elif phase == 8 and now-phase_started>1:
                if s.player.camera_mode!=1:
                    return 0.2
                assert s.follow_camera
                scene.mciblender.camera_view = 'THIRD_FRONT'
                phase += 1
            elif phase == 9 and now-phase_started>1:
                if s.player.camera_mode!=2:
                    return 0.2
                scene.mciblender.camera_view = 'FIRST'
                phase += 1
            elif phase == 10 and now-phase_started>1:
                if s.player.camera_mode!=0:
                    return 0.2
                scene.mciblender.camera_view = 'BLENDER'
                rv = s.space.region_3d
                eye = Vector(P.mc_to_blender((27,112,-12)))
                target = Vector(P.mc_to_blender((12,100.5,3)))
                rv.view_rotation = (target-eye).to_track_quat('-Z','Y')
                rv.view_location = target
                rv.view_distance = (target-eye).length
                s.space.lens = 38
                free_view = rv.view_location.copy()
                bpy.ops.mciblender.capture('INVOKE_DEFAULT')
                walk_start = Vector(s.position)
                s.yaw,s.pitch = 0,10
                s.window.event_simulate(type='W',value='PRESS')
                phase += 1
            elif phase == 11 and now-phase_started>0.7:
                s.window.event_simulate(type='W',value='RELEASE')
                phase += 1
            elif phase == 12 and now-phase_started>1:
                assert (s.space.region_3d.view_location-free_view).length<0.0001
                assert not s.follow_camera and s.captured
                assert (Vector(s.position)-walk_start).length>0.3
                record('All four view choices; Minecraft playable from fixed Blender camera',camera_modes=[1,2,0],blender_view=True,
                       moved=(Vector(s.position)-walk_start).length)
                s.window.event_simulate(type='ESC',value='PRESS',shift=True)
                phase += 1
            elif phase == 13 and now-phase_started>2:
                assert not s.captured and not s.follow_camera
                assert s.link.alive and s.player.in_world
                bpy.ops.wm.save_as_mainfile(filepath=str(output/'Blender Models in Minecraft.blend'))
                bpy.ops.screen.screenshot(filepath=str(output/'blender-models-in-minecraft.png'))
                record('Blender model editing and Minecraft gameplay coexist',position=s.position,alive=True,
                       blend=str(output/'Blender Models in Minecraft.blend'))
                (output/'complete.json').write_text(json.dumps({'passed':True,'checks':len(results)}))
                return None
            else:
                return 0.2
        phase_started = time.monotonic()
        return 0.2
    except Exception as exc:
        import traceback
        results.append({'phase':phase,'passed':False,'error':traceback.format_exc()})
        (output/'tests.json').write_text(json.dumps(results,indent=2))
        print('FUSION VERIFICATION FAILED',traceback.format_exc(),flush=True)
        return None


bpy.app.timers.register(frame,first_interval=2)
