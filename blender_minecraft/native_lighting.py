"""Temporary, editable Blender lights driven by the live Minecraft simulation."""
import math
import time
import bpy
from mathutils import Vector
from . import protocol as P
from .light_sources import nearest_lights, sky_lighting

TAG = 'mciblender_managed_light'
COLLECTION_TAG = 'mciblender_lighting_collection'


class NativeLighting:
    def __init__(self, scene, space):
        self.scene,self.space = scene,space
        self.active = False
        self.collection = None
        self.previous_shading = {}
        self.previous_overlay = {}
        self.overlay_hidden = None
        self.next_update = 0
        self.selection_key = None
        self.selected = []
        self.tracked = set()
        self.summary = {'active':False,'point_lights':0}

    def ensure_collection(self):
        try:
            if self.collection is not None and self.collection.name in bpy.data.collections:
                return
        except ReferenceError:
            pass
        # Removing a collection can leave its runtime objects as orphan data.
        for obj in list(self.tracked):
            try:
                if obj.users==0:
                    self.remove(obj)
            except ReferenceError:
                pass
        self.tracked.clear()
        self.collection = next((c for c in self.scene.collection.children if c.get(COLLECTION_TAG) and not c.library),None)
        if self.collection is None:
            self.collection = bpy.data.collections.new('Minecraft Lighting')
            self.collection[COLLECTION_TAG] = True
            self.scene.collection.children.link(self.collection)

    def enable(self):
        self.ensure_collection()
        shading = self.space.shading
        self.previous_shading = {name:getattr(shading,name) for name in ('type','use_scene_lights','use_scene_world')}
        shading.type = 'MATERIAL'
        shading.use_scene_lights = True
        shading.use_scene_world = True
        overlay = self.space.overlay
        self.previous_overlay = {p.identifier:getattr(overlay,p.identifier) for p in overlay.bl_rna.properties
                                 if p.type=='BOOLEAN' and p.identifier.startswith('show_') and not p.is_readonly}
        self.overlay_hidden = None
        self.active = True
        self.selection_key = None

    @staticmethod
    def assign(target, name, value):
        # Unchanged RNA writes invalidate Eevee's accumulation and shadow caches.
        previous = getattr(target,name)
        if not isinstance(value,(int,float,bool,str)):
            if all(abs(a-b)<1e-5 for a,b in zip(previous,value)):
                return
        elif previous==value or (isinstance(value,float) and abs(previous-value)<1e-5):
            return
        setattr(target,name,value)

    def objects(self):
        return {obj.get(TAG):obj for obj in self.collection.objects if obj.type=='LIGHT' and obj.get(TAG)}

    def update_overlays(self, session):
        # Eevee omits its shared scene-depth output when the master overlay flag
        # is off. Keep that path active, hiding individual editing aids during
        # play so Minecraft still depth-tests against native material geometry.
        overlay = self.space.overlay
        hidden = session.follow_camera or session.captured or not self.previous_overlay['show_overlays']
        if hidden != self.overlay_hidden:
            for name,previous in self.previous_overlay.items():
                if name=='show_overlays':
                    continue
                self.assign(overlay,name,False if hidden else previous)
            self.overlay_hidden = hidden
        self.assign(overlay,'show_overlays',True)

    def light(self, role, kind, existing):
        if role in existing:
            obj = existing[role]
            self.tracked.add(obj)
            return obj
        data = bpy.data.lights.new('Minecraft '+role,kind)
        data[TAG] = True
        obj = bpy.data.objects.new('Minecraft '+role,data)
        obj[TAG] = role
        obj['mc_generated'] = True
        obj.hide_select = True
        self.collection.objects.link(obj)
        existing[role] = obj
        self.tracked.add(obj)
        return obj

    def remove(self,obj):
        self.tracked.discard(obj)
        data = obj.data
        bpy.data.objects.remove(obj,do_unlink=True)
        if data.users==0 and data.get(TAG):
            bpy.data.lights.remove(data)

    def update(self, session):
        enabled = (self.scene.mciblender.native_lighting and session.window.scene==self.scene and
                   session.link.alive and session.player and session.player.in_world)
        if not enabled:
            self.close()
            return
        if not self.active:
            self.enable()
        self.update_overlays(session)
        now = time.monotonic()
        if now<self.next_update:
            return
        self.next_update = now+0.25
        settings = self.scene.mciblender
        renderer = session.renderer
        self.ensure_collection()
        sky = sky_lighting(renderer.environment.get('atmosphere',{}),renderer.lightmap_samples,settings.native_sky_strength)
        existing = self.objects()
        for role,direction,energy in [('Sun',sky['sun_direction'],sky['sun']),('Moon',sky['moon_direction'],sky['moon']),
                                      ('Sky Fill',(0.4,-0.3,1),sky['fill'])]:
            obj = self.light(role,'SUN',existing)
            self.assign(obj,'rotation_euler',(-Vector(direction)).to_track_quat('-Z','Y').to_euler())
            self.assign(obj.data,'energy',energy)
            self.assign(obj.data,'color',sky['color'])
            self.assign(obj.data,'use_shadow',role!='Sky Fill')
            self.assign(obj.data,'angle',math.radians(5))
        # Model bounds choose useful emitters; hidden meshes and generated helpers do not.
        bounds = []
        models = [o for o in self.scene.objects if o.type=='MESH' and not o.get('mc_generated')
                  and o.visible_get(view_layer=session.window.view_layer)]
        eye = self.space.region_3d.view_matrix.inverted().translation
        models.sort(key=lambda o:(o.matrix_world.translation-eye).length_squared)
        for obj in models[:64]:
            corners = [P.blender_to_mc(obj.matrix_world@Vector(p)) for p in obj.bound_box]
            bounds.append((tuple(min(p[i] for p in corners) for i in range(3)),tuple(max(p[i] for p in corners) for i in range(3))))
        focus = P.blender_to_mc(eye)
        key = (renderer.light_revision,tuple(bounds),tuple(round(v) for v in focus),settings.native_light_limit)
        if key!=self.selection_key:
            self.selected = nearest_lights(renderer.lights,bounds,focus,settings.native_light_limit)
            self.selection_key = key
        keep = {'Sun','Moon','Sky Fill'}
        for source in self.selected:
            role = 'Block '+','.join(str(v) for v in source['key'])
            keep.add(role)
            obj = self.light(role,'POINT',existing)
            self.assign(obj,'location',P.mc_to_blender(source['position']))
            self.assign(obj.data,'energy',320*(source['level']/15)**2*settings.native_block_strength)
            self.assign(obj.data,'color',source['color'])
            self.assign(obj.data,'shadow_soft_size',0.25)
            self.assign(obj.data,'use_shadow',True)
            self.assign(obj.data,'use_custom_distance',True)
            self.assign(obj.data,'cutoff_distance',source['level']+1)
        for role,obj in existing.items():
            if role not in keep:
                self.remove(obj)
        self.summary = {'active':True,'point_lights':len(self.selected),'sun_energy':sky['sun'],
                        'moon_energy':sky['moon'],'fill_energy':sky['fill'],'sources':[list(s['key']) for s in self.selected]}

    def close(self):
        if not self.active:
            return
        try:
            valid = self.collection is not None and self.collection.name in bpy.data.collections
        except ReferenceError:
            valid = False
        if valid:
            for obj in list(self.collection.objects):
                if obj.type=='LIGHT' and obj.get(TAG):
                    self.tracked.add(obj)
        for obj in list(self.tracked):
            try:
                self.remove(obj)
            except ReferenceError:
                pass
        self.tracked.clear()
        if valid:
            if not self.collection.objects and not self.collection.children:
                bpy.data.collections.remove(self.collection)
        try:
            overlay = self.space.overlay
            for name,previous in self.previous_overlay.items():
                applied = True if name=='show_overlays' else (False if self.overlay_hidden else previous)
                if getattr(overlay,name)==applied:
                    setattr(overlay,name,previous)
            shading = self.space.shading
            for name,applied in [('type','MATERIAL'),('use_scene_lights',True),('use_scene_world',True)]:
                if getattr(shading,name)==applied:
                    setattr(shading,name,self.previous_shading[name])
        except ReferenceError: # Editor may have been closed before the host is stopped.
            pass
        self.active = False
        self.collection = None
        self.summary = {'active':False,'point_lights':0}
