import math
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty, StringProperty
from . import keys


def package():
    from . import __name__ as name
    import sys
    return sys.modules[name]


def tick():
    session = package().SESSION
    if not session or session.closed:
        return None
    try:
        session.tick()
    except Exception as exc:
        session.error(exc)
    return 1/60


def camera_changed(settings, context):
    session = package().SESSION
    if session and not session.syncing_view:
        session.choose_view(settings.camera_view)


class Settings(bpy.types.PropertyGroup):
    spawn: FloatVectorProperty(name='Spawn (Blender meters)',default=(0,0,2),size=3)
    yaw: FloatProperty(name='Yaw',default=0)
    pitch: FloatProperty(name='Pitch',default=12,min=-89,max=89)
    command: StringProperty(name='Minecraft command',default='gamemode creative')
    live_collision: BoolProperty(name='Live Blender collision',default=True)
    show_minecraft: BoolProperty(name='Show live Minecraft world',default=True)
    frustum_culling: BoolProperty(name='Cull offscreen Minecraft sections',default=True)
    environment: BoolProperty(name='Minecraft sky, lighting and weather',default=True)
    native_lighting: BoolProperty(name='Light Blender models from Minecraft',default=False,
        description='Use Material Preview and temporary scene lights for Minecraft daylight and nearby emitting blocks')
    native_sky_strength: FloatProperty(name='Daylight strength',default=1,min=0,max=10)
    native_block_strength: FloatProperty(name='Block light strength',default=1,min=0,max=10)
    native_light_limit: IntProperty(name='Block light limit',default=32,min=0,max=128)
    camera_view: EnumProperty(name='View',items=[('FIRST','First Person','Minecraft first person'),
        ('THIRD_BACK','Third Person — Behind','Follow the player from behind'),
        ('THIRD_FRONT','Third Person — Front','Face the player'),
        ('BLENDER','Blender View','Use the Blender viewport camera; release input to orbit and edit')],
        default='FIRST',update=camera_changed)


class Start(bpy.types.Operator):
    bl_idname = 'mciblender.start'
    bl_label = 'Start Blender Host'

    def execute(self, context):
        if package().SESSION:
            self.report({'WARNING'},'Host already running')
            return {'CANCELLED'}
        import os
        import platform
        if os.name != 'nt' or platform.machine().lower() not in ('amd64', 'x86_64'):
            self.report({'ERROR'}, 'This release supports Windows x64 only')
            return {'CANCELLED'}
        from .host import Session
        try:
            package().SESSION = Session(context)
            bpy.app.timers.register(tick,first_interval=0.05)
        except Exception as exc:
            self.report({'ERROR'},str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


class Stop(bpy.types.Operator):
    bl_idname = 'mciblender.stop'
    bl_label = 'Stop Host'

    def execute(self, context):
        if package().SESSION:
            package().SESSION.close()
            package().SESSION = None
        if bpy.app.timers.is_registered(tick):
            bpy.app.timers.unregister(tick)
        return {'FINISHED'}


class QuitGame(bpy.types.Operator):
    bl_idname = 'mciblender.quit_game'
    bl_label = 'Save & Quit Minecraft'
    bl_description = 'Save the Minecraft world and exit its process; keep the Blender scene open'

    def execute(self, context):
        session = package().SESSION
        if not session or not session.link.alive:
            return {'CANCELLED'}
        try:
            session.link.input(9)
            session.quitting = True
        except BufferError as exc:
            self.report({'ERROR'},str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


class Capture(bpy.types.Operator):
    bl_idname = 'mciblender.capture'
    bl_label = 'Capture Input / Play'
    bl_options = {'BLOCKING','GRAB_CURSOR'}

    def invoke(self, context, event):
        self.session = package().SESSION
        if not self.session or not self.session.link.alive:
            self.report({'WARNING'},'Start the host and Minecraft first')
            return {'CANCELLED'}
        if self.session.captured:
            return {'CANCELLED'}
        if not self.session.collision.initialized:
            self.report({'WARNING'},'Scene collision is still being prepared; see progress in the Minecraft sidebar')
            return {'CANCELLED'}
        self.session.captured = True
        self.session.play_view()
        self.last_screen = None
        self.mouse = (event.mouse_x,event.mouse_y)
        self.window = context.window
        self.timer = context.window_manager.event_timer_add(1/60,window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def finish(self, context):
        if not self.session.closed:
            self.session.link.input(6)
        self.session.captured = False
        if not self.session.closed:
            self.session.edit_view()
        context.window_manager.event_timer_remove(self.timer)
        self.window.cursor_modal_restore()
        return {'FINISHED'}

    def modal(self, context, event):
        s = self.session
        if s.closed or s.quitting or not s.link.alive or event.type == 'WINDOW_DEACTIVATE' or (event.type == 'ESC' and event.shift and event.value == 'PRESS'):
            return self.finish(context)
        screen = bool(s.player and s.player.screen_open)
        if screen != self.last_screen:
            self.window.cursor_modal_restore()
            if not screen:
                self.window.cursor_modal_set('NONE')
            self.last_screen = screen
        if event.type == 'TIMER':
            return {'RUNNING_MODAL'}
        try:
            if event.type == 'MOUSEMOVE':
                x,y = event.mouse_x,event.mouse_y
                if screen:
                    rx = (x-s.region.x)/max(1,s.region.width)
                    ry = 1-(y-s.region.y)/max(1,s.region.height)
                    s.link.input(4,a=int(rx*s.width),b=int(ry*s.height))
                else:
                    dx,dy = x-self.mouse[0],y-self.mouse[1]
                    if abs(dx)<s.region.width/2 and abs(dy)<s.region.height/2:
                        sensitivity = s.player.sensitivity if s.player else 0.5
                        factor = (sensitivity*0.6+0.2)**3*8*0.15
                        s.yaw = (s.yaw+dx*factor)%360
                        s.pitch = max(-89.9,min(89.9,s.pitch-dy*factor))
                    cx,cy = s.region.x+s.region.width//2,s.region.y+s.region.height//2
                    if abs(x-cx)>s.region.width//3 or abs(y-cy)>s.region.height//3:
                        self.window.cursor_warp(cx,cy)
                        x,y = cx,cy
                self.mouse = (x,y)
            elif event.type in ('WHEELUPMOUSE','WHEELDOWNMOUSE'):
                s.link.input(3,a=120 if event.type == 'WHEELUPMOUSE' else -120)
            elif event.type in keys.BUTTONS and event.value in ('PRESS','RELEASE'):
                s.link.input(2,keys.BUTTONS[event.type],int(event.value == 'PRESS'))
            elif event.type in keys.SCANCODES and event.value in ('PRESS','RELEASE'):
                s.link.input(1,keys.SCANCODES[event.type],int(event.value == 'PRESS'))
                if screen and event.value == 'PRESS' and event.unicode and not event.ctrl and not event.oskey:
                    for ch in event.unicode:
                        if ord(ch)>=32:
                            s.link.input(5,a=ord(ch))
            elif screen and event.type == 'TEXTINPUT' and event.unicode:
                for ch in event.unicode:
                    s.link.input(5,a=ord(ch))
        except BufferError as exc:
            s.error(exc)
            return self.finish(context)
        return {'RUNNING_MODAL'}


class Command(bpy.types.Operator):
    bl_idname = 'mciblender.command'
    bl_label = 'Send Command'

    def execute(self, context):
        session = package().SESSION
        if session and session.link.alive:
            session.command(context.scene.mciblender.command)
            return {'FINISHED'}
        return {'CANCELLED'}


class Rebuild(bpy.types.Operator):
    bl_idname = 'mciblender.rebuild'
    bl_label = 'Update Blender Collision'

    def execute(self, context):
        session = package().SESSION
        if session:
            session.refresh_collision()
        return {'FINISHED'}


class CancelCollision(bpy.types.Operator):
    bl_idname = 'mciblender.cancel_collision'
    bl_label = 'Cancel Collision Update'
    bl_description = 'Cancel pending work, keep completed collision, and pause automatic updates until the next manual update'

    def execute(self, context):
        session = package().SESSION
        if session:
            session.collision.cancel()
            session.collision_paused = True
        return {'FINISHED'}


class EditScene(bpy.types.Operator):
    bl_idname = 'mciblender.edit_scene'
    bl_label = 'Edit Blender Scene'
    bl_description = 'Free the viewport camera and restore Blender modeling tools; Minecraft keeps its world'

    def execute(self, context):
        session = package().SESSION
        if session:
            session.link.input(6)
            session.edit_view()
        return {'FINISHED'}


class Demo(bpy.types.Operator):
    bl_idname = 'mciblender.demo'
    bl_label = 'Create Blender Playground'
    bl_description = 'Creates a new scene, preserving the currently open scene'

    def execute(self, context):
        if package().SESSION:
            self.report({'WARNING'},'Stop the host before switching scenes')
            return {'CANCELLED'}
        scene = bpy.data.scenes.new('Minecraft Playground')
        context.window.scene = scene
        scene.world = bpy.data.worlds.new('Playground Sky')
        scene.world.color = (0.14,0.2,0.3)
        def box(name,location,scale,color):
            bpy.ops.mesh.primitive_cube_add(size=1,location=location)
            obj = context.object
            obj.name = name
            obj.scale = scale
            obj.color = (*color,1)
            obj['mc_collision'] = True
            obj['mc_collider'] = 'BOX'
            return obj
        box('Blender Ground',(0,0,-0.5),(64,64,1),(0.22,0.36,0.28))
        box('Blender Pillar',(-5,-8,2),(2,2,4),(0.19,0.55,0.7))
        box('Blender Bridge',(0,-12,3.75),(12,2,0.5),(0.8,0.55,0.2))
        box('Blender Pillar Right',(5,-12,1.75),(1.5,2,3.5),(0.19,0.55,0.7))
        for i in range(6):
            box(f'Blender Stair {i+1}',(5,-5-i,0.25*(i+1)),(2,1,0.5*(i+1)),(0.48,0.5,0.58))
        scene.mciblender.spawn = (0,0,2)
        scene.mciblender.yaw = 0
        scene.mciblender.pitch = 12
        if context.area.type == 'VIEW_3D':
            context.space_data.shading.type = 'SOLID'
            context.space_data.shading.color_type = 'OBJECT'
            context.space_data.shading.light = 'STUDIO'
        return {'FINISHED'}


class Panel(bpy.types.Panel):
    bl_label = 'Minecraft in Blender'
    bl_idname = 'MCIBLENDER_PT_host'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Minecraft'

    def draw(self, context):
        layout = self.layout
        session = package().SESSION
        if not session:
            layout.label(text='Blender is the game host',icon='WORLD')
            layout.operator('mciblender.export_pack',icon='EXPORT')
            layout.operator('mciblender.demo')
            layout.prop(context.scene.mciblender,'spawn')
            layout.operator('mciblender.start',icon='PLAY')
        else:
            layout.label(text='Connected' if session.link.alive else 'Waiting for Minecraft',icon='LINKED')
            collision = session.collision
            progress = collision.status()
            box = layout.box()
            box.label(text='Scene collision',icon='PHYSICS')
            box.label(text=progress['phase'])
            if collision.busy:
                done, total = (collision.objects_done,collision.objects_total) if collision.building else (collision.regions_done,collision.regions_total)
                unit = 'objects' if collision.building else 'regions'
                box.progress(factor=done/max(1,total),type='BAR',text=f'{done}/{total} {unit}')
                if collision.object_name:
                    box.label(text=collision.object_name,icon='MESH_DATA')
                if collision.building and collision.units_total:
                    box.progress(factor=min(1,collision.units_done/collision.units_total),type='BAR',text='Current object')
                box.label(text=f"Elapsed: {progress['elapsed']:.1f}s")
                if not collision.initialized:
                    box.operator('mciblender.stop',text='Cancel Startup',icon='CANCEL')
                else:
                    box.operator('mciblender.cancel_collision',icon='CANCEL')
            if collision.error:
                box.label(text=collision.error,icon='ERROR')
            if session.collision_paused:
                box.label(text='Automatic updates paused. Use Update below.')
            if not session.link.alive:
                layout.operator('mciblender.launch_minecraft',icon='PLAY')
                layout.label(text='Or launch the imported pack yourself')
            layout.label(text=f'{len(session.renderer.sections)} mesh sections')
            layout.prop(context.scene.mciblender,'camera_view')
            layout.operator('mciblender.capture',icon='PLAY')
            layout.label(text='Shift+Esc: return to Blender tools')
            layout.operator('mciblender.edit_scene',icon='EDITMODE_HLT')
            layout.prop(context.scene.mciblender,'live_collision')
            layout.prop(context.scene.mciblender,'show_minecraft')
            layout.prop(context.scene.mciblender,'environment')
            layout.prop(context.scene.mciblender,'native_lighting')
            if context.scene.mciblender.native_lighting:
                box = layout.box()
                box.prop(context.scene.mciblender,'native_sky_strength')
                box.prop(context.scene.mciblender,'native_block_strength')
                box.prop(context.scene.mciblender,'native_light_limit')
            row = layout.row()
            row.enabled = not collision.building
            row.operator('mciblender.rebuild')
            layout.prop(context.scene.mciblender,'command',text='')
            layout.operator('mciblender.command')
            layout.operator('mciblender.stop',icon='PAUSE')
            layout.operator('mciblender.quit_game',icon='QUIT')
            if session.errors:
                layout.operator('mciblender.open_data',icon='ERROR')


CLASSES = (Settings,Start,Stop,QuitGame,Capture,Command,Rebuild,CancelCollision,EditScene,Demo,Panel)
