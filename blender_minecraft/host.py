"""Blender's main-thread host session, with viewport rendering and diagnostic state."""
import json
import math
import os
from pathlib import Path
import struct
import time
import traceback
from collections import deque
import bpy
import blf
from mathutils import Vector
from . import protocol as P
from .transport import HostLink
from .renderer import ViewportRenderer
from .collision import SceneCollision


class Session:
    def __init__(self, context):
        self.area = context.area
        self.window = context.window
        self.region = next(r for r in self.area.regions if r.type == 'WINDOW')
        self.space = self.area.spaces.active
        self.scene = context.scene
        self.original = (self.space.region_3d.view_rotation.copy(),self.space.region_3d.view_location.copy(),
                         self.space.region_3d.view_distance,self.space.region_3d.view_perspective,
                         self.space.lens,self.space.overlay.show_overlays)
        self.renderer = ViewportRenderer()
        self.collision = SceneCollision()
        self.collision.rebuild(context)
        self.link = HostLink()
        self.position = P.blender_to_mc(context.scene.mciblender.spawn)
        self.requested_position = self.position
        self.yaw,self.pitch = context.scene.mciblender.yaw,context.scene.mciblender.pitch
        self.teleport = 0 # Initial connection adopts vanilla position; explicit teleports start at 1.
        self.player = None
        self.captured = False
        self.follow_camera = context.scene.mciblender.camera_view != 'BLENDER'
        self.syncing_view = False
        self.camera_request = None
        self.camera_request_time = 0
        self.editor_view = None
        self.collision_dirty = False
        self.last_collision_update = 0
        self.collision_rebuilds = 0
        self.collider_signature = self.scene_signature()
        self.last_scene_poll = 0
        self.closed = False
        self.started = time.monotonic()
        self.events = []
        self.errors = []
        self.tick_count = 0
        self.last_snapshot = 0
        self.capture_name = None
        self.commands = deque()
        self.command_stage = 0
        self.command_time = 0
        self.width,self.height = 1280,720
        self.draw_handles = [bpy.types.SpaceView3D.draw_handler_add(self.draw_world,(),'WINDOW','POST_VIEW'),
                             bpy.types.SpaceView3D.draw_handler_add(self.draw_overlay,(),'WINDOW','POST_PIXEL')]
        self.space.overlay.show_overlays = not self.follow_camera
        self.space.clip_end = max(1000,self.space.clip_end)
        self.collision.nearby(self.position)
        self.camera_request = {'FIRST':0,'THIRD_BACK':1,'THIRD_FRONT':2,'BLENDER':1}[context.scene.mciblender.camera_view]

    def correct_context(self):
        return bpy.context.area == self.area and bpy.context.region == self.region and bpy.context.scene == self.scene

    def error(self, exc):
        text = ''.join(traceback.format_exception(exc))
        if text not in self.errors:
            self.errors.append(text)
            print('MCInBlender:',text,flush=True)

    def tick(self):
        if self.closed:
            return
        self.tick_count += 1
        from .diagnostics import controls
        controls(self)
        if self.closed:
            return
        scale = min(1,1920/max(1,self.region.width),1080/max(1,self.region.height))
        self.width = max(64,round(self.region.width*scale))
        self.height = max(64,round(self.region.height*scale))
        self.link.state(self.requested_position,self.yaw,self.pitch,self.width,self.height,self.teleport,self.collision.epoch)
        self.link.heartbeat()
        player = self.link.player()
        if player:
            self.player = player
        self.dispatch_commands()
        self.dispatch_camera()
        if time.monotonic()-self.last_scene_poll>0.5:
            self.last_scene_poll = time.monotonic()
            signature = self.scene_signature()
            if signature != self.collider_signature:
                self.collider_signature = signature
                self.collision_dirty = True
        if self.player and self.player.in_world:
            self.position = self.player.position
            if self.follow_camera:
                self.update_camera()
        if self.window.scene == self.scene and self.collision_dirty and self.scene.mciblender.live_collision and time.monotonic()-self.last_collision_update>0.25:
            self.refresh_collision()
        self.collision.nearby(self.position)
        self.collision.flush(self.link)
        for kind,payload in self.link.render_messages():
            self.renderer.accept(kind,payload)
        overlay = self.link.overlay()
        if overlay:
            self.renderer.overlay_pending = overlay
        self.events.extend(self.link.events())
        self.events = self.events[-200:]
        raw = self.link.snapshot(P.ENTITIES,0x40+160*96)
        if raw:
            count,selected = struct.unpack_from('<II',raw,4)
            self.renderer.selection = struct.unpack_from('<6f',raw,12) if selected else None
            self.renderer.entity_records = [raw[0x40+i*96:0x40+(i+1)*96] for i in range(min(160,count))]
        self.area.tag_redraw()
        if time.monotonic()-self.last_snapshot>2:
            self.last_snapshot = time.monotonic()
            self.write_diagnostics()

    def refresh_collision(self):
        with bpy.context.temp_override(window=self.window,area=self.area,region=self.region):
            self.collision.rebuild(bpy.context,incremental=True)
        self.collision.nearby(self.position)
        self.collision_dirty = False
        self.last_collision_update = time.monotonic()
        self.collision_rebuilds += 1

    def scene_signature(self):
        # Deletion, visibility and custom collision toggles may not emit a mesh
        # geometry update, so detect those without re-evaluating all meshes.
        return tuple((o.as_pointer(),o.hide_get(),bool(o.get('mc_collision',True)),o.get('mc_collider','MESH'))
                     for o in self.scene.objects if o.type == 'MESH' and not o.get('mc_generated'))

    def play_view(self):
        rv = self.space.region_3d
        if not self.follow_camera:
            self.editor_view = (rv.view_rotation.copy(),rv.view_location.copy(),rv.view_distance,rv.view_perspective,self.space.lens)
        self.follow_camera = self.scene.mciblender.camera_view != 'BLENDER'
        self.space.overlay.show_overlays = False
        self.space.show_gizmo = False

    def choose_view(self, mode):
        if mode == 'BLENDER':
            self.edit_view()
        else:
            self.play_view()
        self.camera_request = {'FIRST':0,'THIRD_BACK':1,'THIRD_FRONT':2,'BLENDER':1}[mode]

    def dispatch_camera(self):
        if not self.player or not self.player.in_world:
            return
        if self.camera_request is not None:
            if self.player.camera_mode == self.camera_request:
                self.camera_request = None
            elif not self.player.screen_open and time.monotonic()>=self.camera_request_time:
                self.link.input(1,62,1)
                self.link.input(1,62,0)
                self.camera_request_time = time.monotonic()+0.25
        elif self.follow_camera and self.scene.mciblender.camera_view != 'BLENDER':
            self.syncing_view = True
            try:
                self.scene.mciblender.camera_view = ('FIRST','THIRD_BACK','THIRD_FRONT')[self.player.camera_mode]
            finally:
                self.syncing_view = False

    def edit_view(self):
        if not self.follow_camera:
            return
        self.follow_camera = False
        rv = self.space.region_3d
        if self.editor_view:
            rv.view_rotation,rv.view_location,rv.view_distance,rv.view_perspective,self.space.lens = self.editor_view
        else:
            # Keep the same eye/orientation, with an orbit pivot in front of it.
            forward = rv.view_rotation @ Vector((0,0,-1))
            rv.view_location += forward*(8-rv.view_distance)
            rv.view_distance = 8
        self.space.overlay.show_overlays = True
        self.space.show_gizmo = True

    def update_camera(self):
        player = self.player
        eye = Vector(P.mc_to_blender(player.eye))
        yaw,pitch = math.radians(self.yaw),math.radians(self.pitch)
        forward = Vector((-math.sin(yaw)*math.cos(pitch),-math.cos(yaw)*math.cos(pitch),-math.sin(pitch)))
        if player.camera_mode == 1:
            eye -= forward*player.camera_distance
        elif player.camera_mode == 2:
            eye += forward*player.camera_distance
            forward.negate()
        rv = self.space.region_3d
        rv.view_perspective = 'PERSP'
        rv.view_rotation = forward.to_track_quat('-Z','Y')
        rv.view_distance = 0.01
        rv.view_location = eye+forward*0.01
        # Blender's viewport uses a 32 mm sensor across the longer viewport axis.
        aspect = self.region.width/max(1,self.region.height)
        self.space.lens = 16/(math.tan(math.radians(max(10,min(150,player.fov)))/2)*max(1,aspect))

    def command(self, text):
        self.commands.append(text.lstrip('/'))

    def dispatch_commands(self):
        if not self.commands or not self.player or not self.player.in_world or self.player.flags & 32:
            return
        now = time.monotonic()
        if now < self.command_time:
            return
        def key(code):
            self.link.input(1,code,1)
            self.link.input(1,code,0)
        if self.command_stage == 0:
            if self.player.screen_open:
                key(41)
                self.command_time = now+0.25
                return
            key(56)
            self.command_stage = 1
            self.command_time = now+0.2
        elif self.command_stage == 1:
            if not self.player.screen_open:
                self.command_stage = 0
                return
            for char in self.commands[0]:
                self.link.input(5,a=ord(char))
            self.command_stage = 2
            self.command_time = now+0.15
        elif self.command_stage == 2:
            key(40)
            self.commands.popleft()
            self.command_stage = 0
            self.command_time = now+0.3

    def draw_world(self):
        if not self.correct_context() or self.closed:
            return
        try:
            if self.scene.mciblender.show_minecraft:
                self.renderer.draw_world(bpy.context,self.player,show_selection=self.follow_camera,
                                         culling=self.scene.mciblender.frustum_culling,
                                         upload_overlay=self.follow_camera or self.captured)
            else:
                self.renderer.flush(upload_overlay=self.follow_camera or self.captured)
        except Exception as exc:
            self.error(exc)

    def draw_overlay(self):
        if not self.correct_context() or self.closed:
            return
        try:
            if self.follow_camera or self.captured:
                self.renderer.draw_overlay(bpy.context)
            blf.size(0,14)
            blf.position(0,16,self.region.height-26,0)
            blf.color(0,0.7,0.95,1,1)
            status = 'PLAYING | Shift+Esc edits Blender scene' if self.captured else ('BLENDER EDIT | Minecraft continues simulating' if not self.follow_camera else 'Click Play or Edit Scene')
            if not self.link.alive:
                status = 'Waiting for Minecraft bridge...'
            blf.draw(0,'MCInBlender | '+status)
            if self.errors:
                blf.position(0,16,self.region.height-48,0)
                blf.color(0,1,0.2,0.2,1)
                blf.draw(0,'Bridge error — see diagnostics / Blender console')
            if self.capture_name:
                from .diagnostics import capture
                name,self.capture_name = self.capture_name,None
                capture(self.region,name)
        except Exception as exc:
            self.error(exc)

    def write_diagnostics(self):
        target = Path(__file__).resolve().parents[1]/'logs'/'host-status.json'
        target.parent.mkdir(exist_ok=True)
        data = {'host':'Blender','blender_version':bpy.app.version_string,'alive':self.link.alive,
                'ticks':self.tick_count,'sections':len(self.renderer.sections),
                'textures':len(self.renderer.textures),'render_messages':dict(self.renderer.counts),
                'overlay_frame':self.renderer.overlay_frame,'overlay_size':self.renderer.overlay_size,
                'collision_objects':self.collision.object_count,'pending_collision':len(self.collision.queue),
                'position':self.position,'yaw':self.yaw,'pitch':self.pitch,
                'player':self.player.__dict__ if self.player else None,'errors':self.errors,
                'events':self.events[-20:]}
        data['environment'] = self.renderer.environment
        data['commands_pending'] = len(self.commands)
        data['input_captured'] = self.captured
        data['host_pid'] = os.getpid()
        data['viewport_region'] = [self.region.x,self.region.y,self.region.width,self.region.height]
        data['editor_mode'] = not self.follow_camera
        data['camera_view'] = self.scene.mciblender.camera_view
        data['collision_rebuilds'] = self.collision_rebuilds
        data['performance'] = self.renderer.profile()
        keys = self.renderer.sections.keys()
        data['section_extent'] = [[min(k[i] for k in keys),max(k[i] for k in keys)] for i in range(3)] if keys else None
        data['section_records'] = {'lights':len(self.renderer.lights),'solids':len(self.renderer.solids),'dug':len(self.renderer.dug)}
        data['entity_kinds'] = dict(__import__('collections').Counter(struct.unpack_from('<I',r)[0] for r in self.renderer.entity_records))
        temp = target.with_suffix('.tmp')
        temp.write_text(json.dumps(data,indent=2),encoding='utf8')
        temp.replace(target)

    def close(self):
        if self.closed:
            return
        self.closed = True
        for handle in self.draw_handles:
            bpy.types.SpaceView3D.draw_handler_remove(handle,'WINDOW')
        self.link.close()
        if self.follow_camera:
            rv = self.space.region_3d
            rv.view_rotation,rv.view_location,rv.view_distance,rv.view_perspective,self.space.lens,self.space.overlay.show_overlays = self.original
        self.area.tag_redraw()
