"""Draw real Minecraft geometry in Blender's viewport and native depth buffer."""
import struct
import time
import json
from collections import Counter, OrderedDict, deque
import numpy as np
import bpy
import gpu
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector
from . import protocol as P

DTYPE = np.dtype([('position','<f4',3), ('uv','<f4',2), ('color','u1',4), ('light','<u4'), ('flags','<u4')])


def make_shader():
    interface = gpu.types.GPUStageInterfaceInfo('mciblender_varyings')
    interface.smooth('VEC2','texCoord')
    interface.smooth('VEC4','tint')
    interface.smooth('VEC2','fogDistance')
    info = gpu.types.GPUShaderCreateInfo()
    info.push_constant('MAT4','transform')
    info.push_constant('VEC3','worldOrigin')
    info.push_constant('VEC3','cameraPosition')
    info.push_constant('VEC3','fogColor')
    info.push_constant('VEC4','fogRanges')
    info.vertex_in(0,'VEC3','position')
    info.vertex_in(1,'VEC2','uv')
    info.vertex_in(2,'VEC4','color')
    info.vertex_in(3,'VEC2','lightLevels')
    info.vertex_out(interface)
    info.sampler(0,'FLOAT_2D','atlas')
    info.sampler(1,'FLOAT_2D','lightmap')
    info.fragment_out(0,'VEC4','fragColor')
    info.vertex_source('''void main(){
        gl_Position=transform*vec4(position,1.0); texCoord=uv;
        tint=color*vec4(texelFetch(lightmap,clamp(ivec2(lightLevels),ivec2(0),ivec2(15)),0).rgb,1.0);
        vec3 delta=position+worldOrigin-cameraPosition;
        fogDistance=vec2(length(delta),length(delta.xy));
    }''')
    info.fragment_source('''void main(){
        ivec2 size=textureSize(atlas,0);
        ivec2 p=clamp(ivec2(floor(texCoord*vec2(size))),ivec2(0),size-1);
        vec4 c=texelFetch(atlas,p,0)*tint;
        if(c.a<0.08) discard;
        float fog=max(smoothstep(fogRanges.x,fogRanges.y,fogDistance.x),smoothstep(fogRanges.z,fogRanges.w,fogDistance.y));
        c.rgb=mix(c.rgb,fogColor,fog);
        fragColor=c;
    }''')
    return gpu.shader.create_from_info(info)


def texture(width, height, pixels):
    data = np.frombuffer(pixels, dtype=np.uint8).astype(np.float32) / 255
    return gpu.types.GPUTexture((width,height), format='RGBA8', data=gpu.types.Buffer('FLOAT',data.size,data))


class ViewportRenderer:
    def __init__(self):
        self.shader = None
        self.textures = {}
        self.lightmap = None
        self.lightmap_pending = None
        self.lightmap_samples = None
        self.fullbright = None
        self.environment_textures = {}
        self.atmosphere = None
        self.texture_pixels = {}
        self.sections = {}
        self.section_bounds = {}
        self.bounds_dirty = True
        self.section_keys = ()
        self.bounds_centers = self.bounds_sizes = np.empty((0,3),dtype=np.float32)
        self.dynamic = {}
        self.pending = OrderedDict()
        self.atlas_patches = []
        self.overlay_pending = None
        self.overlay_texture = None
        self.overlay_frame = 0
        self.overlay_size = (0,0)
        self.counts = Counter()
        self.errors = []
        self.solids, self.dug, self.lights = {}, {}, {}
        self.light_revision = 0
        self.selection = None
        self.entity_records = []
        self.entity_batches = []
        self.environment = {}
        self.performance = {}
        self.frame_samples = deque(maxlen=180)

    def accept(self, kind, payload):
        self.counts[kind] += 1
        if kind == 3:
            self.sections.clear()
            self.section_bounds.clear()
            self.bounds_dirty = True
            self.dynamic.clear()
            self.pending.clear()
            self.solids.clear()
            self.dug.clear()
            self.lights.clear()
            self.light_revision += 1
            self.entity_records.clear()
            self.entity_batches.clear()
            self.selection = None
            self.atlas_patches.clear()
            self.textures.clear()
            self.texture_pixels.clear()
        elif kind == 1:
            self.pending[('atlas',0)] = (kind,payload)
        elif kind == 4:
            self.pending[('texture',struct.unpack_from('<I',payload)[0])] = (kind,payload)
        elif kind == 2:
            self.pending[('section',*struct.unpack_from('<iii',payload))] = (kind,payload)
        elif kind in (5,6,9):
            self.pending[('dynamic',kind)] = (kind,payload)
        elif kind == 7:
            self.atlas_patches.append(payload)
        elif kind in (8,10,11):
            key = struct.unpack_from('<iii',payload)
            n, = struct.unpack_from('<I',payload,12)
            store = {8:self.lights, 10:self.solids, 11:self.dug}[kind]
            if kind == 8 and store.get(key) != (payload if n else None):
                self.light_revision += 1
            if n:
                store[key] = payload
            else:
                store.pop(key,None)
        elif kind == 12:
            self.environment = json.loads(payload.decode('utf8'))
        elif kind == 13:
            if len(payload)!=16*16*4:
                raise P.ProtocolError('Invalid lightmap size')
            self.lightmap_pending = payload
        elif kind == 14:
            self.pending[('environment',struct.unpack_from('<I',payload)[0])] = (kind,payload)
        else:
            self.errors.append(f'Unknown render kind {kind}')

    def create_batches(self, kind, payload):
        origin,batches,raw = P.mesh_payload(kind,payload)
        vertices = np.frombuffer(raw,dtype=DTYPE)
        pos = vertices['position'].copy()
        if len(pos):
            pos[:,1],pos[:,2] = -vertices['position'][:,2],vertices['position'][:,1]
        color = vertices['color'].astype(np.float32)/255
        shades = self.environment.get('atmosphere',{}).get('faceShade',(0.5,1.0,0.8,0.8,0.6,0.6))
        normals = np.minimum((vertices['flags']>>4)&7,6)
        color[:,:3] *= np.asarray((1.0,*shades),dtype=np.float32)[normals,None]
        light = vertices['light']
        light_levels = np.stack((light&255,(light>>8)&255),axis=1).astype(np.float32)
        result = []
        for tex,first,count,flags in batches:
            if not count:
                continue
            tri_flags = vertices['flags'][first:first+count:3]
            for translucent in (False,True):
                mask = ((tri_flags & 2) != 0) | bool(flags & 1)
                indices = np.arange(first,first+count).reshape(-1,3)[mask == translucent].ravel()
                if not len(indices):
                    continue
                batch = batch_for_shader(self.shader,'TRIS',{
                    'position':pos[indices], 'uv':vertices['uv'][indices], 'color':color[indices],
                    'lightLevels':light_levels[indices]})
                result.append((tex,translucent,batch))
        offset = np.asarray(P.mc_to_blender(origin),dtype=np.float32)
        if len(pos):
            low,high = pos.min(axis=0),pos.max(axis=0)
            bounds = ((low+high)/2+offset,(high-low)/2)
        else:
            bounds = (offset,np.zeros(3,dtype=np.float32))
        return tuple(offset),result,bounds

    def flush(self, budget_ms=10, upload_overlay=True):
        flush_start = time.perf_counter()
        if self.shader is None:
            self.shader = make_shader()
            self.fullbright = texture(16,16,bytes([255])*(16*16*4))
        deadline = time.perf_counter()+budget_ms/1000
        # A new atlas must precede its patches, even under a large mesh backlog.
        for key in list(self.pending):
            if key[0] in ('atlas','texture','environment'):
                kind,payload = self.pending.pop(key)
                ident,w,h,pixels = P.texture_payload(4 if kind==14 else kind,payload)
                if kind==14:
                    self.environment_textures[ident] = texture(w,h,pixels)
                    continue
                self.texture_pixels[ident] = (w,h,bytearray(pixels))
                self.textures[ident] = texture(w,h,pixels)
        if self.lightmap_pending is not None:
            self.lightmap = texture(16,16,self.lightmap_pending)
            pixels = np.frombuffer(self.lightmap_pending,dtype=np.uint8).reshape(16,16,4)
            self.lightmap_samples = {'dark':pixels[0,0].tolist(),'sky':pixels[15,0].tolist(),'block':pixels[0,15].tolist()}
            self.lightmap_pending = None
        atlas_start = time.perf_counter()
        if self.atlas_patches and 0 in self.texture_pixels:
            w,h,pixels = self.texture_pixels[0]
            patches = {struct.unpack_from('<II',p):p for p in self.atlas_patches}
            for p in patches.values():
                x,y,pw,ph = struct.unpack_from('<IIII',p)
                if x+pw>w or y+ph>h or len(p)!=16+pw*ph*4:
                    raise P.ProtocolError('Invalid atlas patch')
                for row in range(ph):
                    begin = ((y+row)*w+x)*4
                    pixels[begin:begin+pw*4] = p[16+row*pw*4:16+(row+1)*pw*4]
            self.patch_atlas_batch(list(patches.values()))
            self.atlas_patches.clear()
        self.performance['atlas_ms'] = (time.perf_counter()-atlas_start)*1000
        mesh_start = time.perf_counter()
        while self.pending and time.perf_counter()<deadline:
            key,(kind,payload) = self.pending.popitem(last=False)
            result = self.create_batches(kind,payload)
            if kind == 2:
                if result[1]:
                    self.sections[key[1:]] = result[:2]
                    self.section_bounds[key[1:]] = result[2]
                else:
                    self.sections.pop(key[1:],None)
                    self.section_bounds.pop(key[1:],None)
                self.bounds_dirty = True
            else:
                self.dynamic[kind] = result[:2]
        self.performance['mesh_upload_ms'] = (time.perf_counter()-mesh_start)*1000
        overlay_start = time.perf_counter()
        if self.overlay_pending and upload_overlay:
            w,h,flags,frame,pixels = self.overlay_pending
            if not flags & 1:
                pixels = np.frombuffer(pixels,dtype=np.uint8).reshape(h,w,4)[::-1].copy().tobytes()
            self.overlay_texture = texture(w,h,pixels)
            self.overlay_frame = frame
            self.overlay_size = (w,h)
            self.overlay_pending = None
        self.performance['overlay_upload_ms'] = (time.perf_counter()-overlay_start)*1000
        from .entity_geometry import build
        pos,uv,color,solid = build(self.entity_records)
        self.entity_batches = []
        for a,b,translucent in [(0,solid,False),(solid,len(pos),True)]:
            if b>a:
                batch = batch_for_shader(self.shader,'TRIS',{'position':pos[a:b],'uv':uv[a:b],'color':color[a:b],
                                                           'lightLevels':[(0,15)]*(b-a)})
                self.entity_batches.append((0,translucent,batch))
        self.performance['flush_ms'] = (time.perf_counter()-flush_start)*1000

    def patch_atlas_batch(self, patches):
        from .atlas_upload import pack_patches
        atlas = self.textures[0]
        sheet,positions,uvs = pack_patches(patches,atlas.width,atlas.height)
        if sheet is None:
            return
        height,width = sheet.shape[:2]
        patch = texture(width,height,sheet.tobytes())
        shader = gpu.shader.from_builtin('IMAGE')
        batch = batch_for_shader(shader,'TRIS',{'pos':positions,'texCoord':uvs})
        viewport = gpu.state.viewport_get()
        blend,depth,mask = gpu.state.blend_get(),gpu.state.depth_test_get(),gpu.state.depth_mask_get()
        frame = gpu.types.GPUFrameBuffer(color_slots=atlas)
        try:
            with frame.bind(), gpu.matrix.push_pop(), gpu.matrix.push_pop_projection():
                gpu.state.viewport_set(0,0,atlas.width,atlas.height)
                gpu.state.blend_set('NONE')
                gpu.state.depth_test_set('NONE')
                gpu.state.depth_mask_set(False)
                gpu.matrix.load_matrix(Matrix.Identity(4))
                gpu.matrix.load_projection_matrix(Matrix.Identity(4))
                shader.bind()
                shader.uniform_sampler('image',patch)
                batch.draw(shader)
        finally:
            gpu.state.viewport_set(*viewport)
            gpu.state.blend_set(blend)
            gpu.state.depth_test_set(depth)
            gpu.state.depth_mask_set(mask)

    def draw_world(self, context, player, show_selection=True, culling=True, upload_overlay=True, environment=True):
        frame_start = time.perf_counter()
        draw_calls = 0
        visible_sections = 0
        self.flush(upload_overlay=upload_overlay)
        if not self.shader or not player or not player.in_world:
            return
        blend,depth,mask = gpu.state.blend_get(),gpu.state.depth_test_get(),gpu.state.depth_mask_get()
        try:
            atmosphere = self.environment.get('atmosphere',{}) if environment else {}
            eye = context.region_data.view_matrix.inverted().translation
            if atmosphere:
                if self.atmosphere is None:
                    from .atmosphere import AtmosphereRenderer
                    self.atmosphere = AtmosphereRenderer()
                self.atmosphere.draw_sky(context,atmosphere,self.environment_textures)
            gpu.state.depth_test_set('LESS_EQUAL')
            self.shader.bind()
            self.shader.uniform_sampler('lightmap',(self.lightmap if environment else None) or self.fullbright)
            self.shader.uniform_float('cameraPosition',eye)
            self.shader.uniform_float('fogColor',atmosphere.get('fogColor',(0,0,0)))
            self.shader.uniform_float('fogRanges',tuple(atmosphere.get(k,d) for k,d in
                [('fogStart',1e8),('fogEnd',1e9),('distanceStart',1e8),('distanceEnd',1e9)]))
            transform = context.region_data.perspective_matrix
            if self.bounds_dirty:
                self.section_keys = tuple(self.section_bounds)
                self.bounds_centers = np.asarray([self.section_bounds[k][0] for k in self.section_keys],dtype=np.float32).reshape(-1,3)
                self.bounds_sizes = np.asarray([self.section_bounds[k][1] for k in self.section_keys],dtype=np.float32).reshape(-1,3)
                self.bounds_dirty = False
            if culling:
                from .visibility import visible_bounds
                mask_visible = visible_bounds(self.bounds_centers,self.bounds_sizes,transform)
                groups = [self.sections[self.section_keys[i]] for i in np.flatnonzero(mask_visible)]
            else:
                groups = list(self.sections.values())
            visible_sections = len(groups)
            if self.entity_batches:
                groups.append(((0,0,0),self.entity_batches))
            if 6 in self.dynamic:
                groups.append(self.dynamic[6])
            if 5 in self.dynamic and player and player.camera_mode:
                groups.append((P.mc_to_blender(player.position),self.dynamic[5][1]))
            for translucent in (False,True):
                gpu.state.blend_set('ALPHA' if translucent else 'NONE')
                gpu.state.depth_mask_set(not translucent)
                # Sort section-level transparent geometry back to front.
                if translucent and player:
                    eye = context.region_data.view_matrix.inverted().translation
                    groups.sort(key=lambda g:(Vector(g[0])-eye).length_squared,reverse=True)
                for origin,batches in groups:
                    self.shader.uniform_float('transform',transform @ Matrix.Translation(origin))
                    self.shader.uniform_float('worldOrigin',origin)
                    for tex,is_transparent,batch in batches:
                        if is_transparent != translucent or tex not in self.textures:
                            continue
                        self.shader.uniform_sampler('atlas',self.textures[tex])
                        batch.draw(self.shader)
                        draw_calls += 1
            if atmosphere:
                self.atmosphere.draw_weather(context,atmosphere,self.environment_textures,self.lightmap or self.fullbright)
            if show_selection:
                self.draw_selection(context)
        finally:
            gpu.state.blend_set(blend)
            gpu.state.depth_test_set(depth)
            gpu.state.depth_mask_set(mask)
            self.performance.update(draw_calls=draw_calls,visible_sections=visible_sections,cached_sections=len(self.sections))
            self.frame_samples.append((time.perf_counter(),(time.perf_counter()-frame_start)*1000,self.performance.copy()))

    def profile(self):
        if len(self.frame_samples)<2:
            return self.performance.copy()
        duration = self.frame_samples[-1][0]-self.frame_samples[0][0]
        result = {key:round(sum(p[2].get(key,0) for p in self.frame_samples)/len(self.frame_samples),3)
                  for key in self.performance}
        result['draw_total_ms'] = round(sum(p[1] for p in self.frame_samples)/len(self.frame_samples),3)
        result['viewport_fps'] = round((len(self.frame_samples)-1)/max(duration,0.001),2)
        result['pending_meshes'] = len(self.pending)
        return result

    def draw_selection(self, context):
        if self.selection is None:
            return
        lo = [c-0.003 for c in self.selection[:3]]
        hi = [c+0.003 for c in self.selection[3:]]
        corners = [P.mc_to_blender(tuple(hi[a] if i&(1<<a) else lo[a] for a in range(3))) for i in range(8)]
        edges = [(0,1),(2,3),(4,5),(6,7),(0,2),(1,3),(4,6),(5,7),(0,4),(1,5),(2,6),(3,7)]
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        batch = batch_for_shader(shader,'LINES',{'pos':[corners[i] for edge in edges for i in edge]})
        width = gpu.state.line_width_get()
        try:
            gpu.state.line_width_set(2)
            gpu.state.blend_set('ALPHA')
            gpu.state.depth_mask_set(False)
            with gpu.matrix.push_pop(),gpu.matrix.push_pop_projection():
                gpu.matrix.load_matrix(context.region_data.view_matrix)
                gpu.matrix.load_projection_matrix(context.region_data.window_matrix)
                shader.bind()
                shader.uniform_float('color',(0,0,0,0.65))
                batch.draw(shader)
        finally:
            gpu.state.line_width_set(width)

    def draw_overlay(self, context):
        if not self.overlay_texture:
            return
        shader = gpu.shader.from_builtin('IMAGE')
        w,h = context.region.width,context.region.height
        batch = batch_for_shader(shader,'TRI_FAN',{'pos':[(0,0),(w,0),(w,h),(0,h)],'texCoord':[(0,0),(1,0),(1,1),(0,1)]})
        blend,depth,mask = gpu.state.blend_get(),gpu.state.depth_test_get(),gpu.state.depth_mask_get()
        try:
            gpu.state.depth_test_set('NONE')
            gpu.state.depth_mask_set(False)
            gpu.state.blend_set('ALPHA_PREMULT')
            shader.bind()
            shader.uniform_sampler('image',self.overlay_texture)
            batch.draw(shader)
        finally:
            gpu.state.blend_set(blend)
            gpu.state.depth_test_set(depth)
            gpu.state.depth_mask_set(mask)
