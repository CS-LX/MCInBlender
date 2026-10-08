"""Draw real Minecraft geometry in Blender's viewport and native depth buffer."""
import struct
import time
import json
from collections import Counter, OrderedDict
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
    info = gpu.types.GPUShaderCreateInfo()
    info.push_constant('MAT4','transform')
    info.vertex_in(0,'VEC3','position')
    info.vertex_in(1,'VEC2','uv')
    info.vertex_in(2,'VEC4','color')
    info.vertex_out(interface)
    info.sampler(0,'FLOAT_2D','atlas')
    info.fragment_out(0,'VEC4','fragColor')
    info.vertex_source('void main(){gl_Position=transform*vec4(position,1.0); texCoord=uv; tint=color;}')
    info.fragment_source('''void main(){
        ivec2 size=textureSize(atlas,0);
        ivec2 p=clamp(ivec2(floor(texCoord*vec2(size))),ivec2(0),size-1);
        vec4 c=texelFetch(atlas,p,0)*tint;
        if(c.a<0.08) discard;
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
        self.texture_pixels = {}
        self.sections = {}
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
        self.selection = None
        self.entity_records = []
        self.entity_batches = []
        self.environment = {}

    def accept(self, kind, payload):
        self.counts[kind] += 1
        if kind == 3:
            self.sections.clear()
            self.dynamic.clear()
            self.pending.clear()
            self.solids.clear()
            self.dug.clear()
            self.lights.clear()
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
            if n:
                store[key] = payload
            else:
                store.pop(key,None)
        elif kind == 12:
            self.environment = json.loads(payload.decode('utf8'))
        else:
            self.errors.append(f'Unknown render kind {kind}')

    def create_batches(self, kind, payload):
        origin,batches,raw = P.mesh_payload(kind,payload)
        vertices = np.frombuffer(raw,dtype=DTYPE)
        pos = vertices['position'].copy()
        if len(pos):
            pos[:,1],pos[:,2] = -vertices['position'][:,2],vertices['position'][:,1]
        color = vertices['color'].astype(np.float32)/255
        # SkyCraft carries vanilla block/sky light; retain visibility in unlit Blender scenes.
        light = vertices['light']
        brightness = np.maximum(light & 255,(light >> 8) & 255).astype(np.float32)/15
        color[:,:3] *= np.maximum(0.18,np.minimum(1,brightness))[:,None]
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
                    'position':pos[indices], 'uv':vertices['uv'][indices], 'color':color[indices]})
                result.append((tex,translucent,batch))
        return P.mc_to_blender(origin),result

    def flush(self, budget_ms=10):
        if self.shader is None:
            self.shader = make_shader()
        deadline = time.perf_counter()+budget_ms/1000
        # A new atlas must precede its patches, even under a large mesh backlog.
        for key in list(self.pending):
            if key[0] in ('atlas','texture'):
                kind,payload = self.pending.pop(key)
                ident,w,h,pixels = P.texture_payload(kind,payload)
                self.texture_pixels[ident] = (w,h,bytearray(pixels))
                self.textures[ident] = texture(w,h,pixels)
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
                self.patch_atlas(x,y,pw,ph,p[16:])
            self.atlas_patches.clear()
        while self.pending and time.perf_counter()<deadline:
            key,(kind,payload) = self.pending.popitem(last=False)
            result = self.create_batches(kind,payload)
            if kind == 2:
                if result[1]:
                    self.sections[key[1:]] = result
                else:
                    self.sections.pop(key[1:],None)
            else:
                self.dynamic[kind] = result
        if self.overlay_pending:
            w,h,flags,frame,pixels = self.overlay_pending
            if not flags & 1:
                pixels = np.frombuffer(pixels,dtype=np.uint8).reshape(h,w,4)[::-1].copy().tobytes()
            self.overlay_texture = texture(w,h,pixels)
            self.overlay_frame = frame
            self.overlay_size = (w,h)
            self.overlay_pending = None
        from .entity_geometry import build
        pos,uv,color,solid = build(self.entity_records)
        self.entity_batches = []
        for a,b,translucent in [(0,solid,False),(solid,len(pos),True)]:
            if b>a:
                batch = batch_for_shader(self.shader,'TRIS',{'position':pos[a:b],'uv':uv[a:b],'color':color[a:b]})
                self.entity_batches.append((0,translucent,batch))

    def patch_atlas(self, x, y, width, height, pixels):
        atlas = self.textures[0]
        patch = texture(width,height,pixels)
        shader = gpu.shader.from_builtin('IMAGE')
        x0,y0 = 2*x/atlas.width-1,2*y/atlas.height-1
        x1,y1 = 2*(x+width)/atlas.width-1,2*(y+height)/atlas.height-1
        batch = batch_for_shader(shader,'TRI_FAN',{'pos':[(x0,y0),(x1,y0),(x1,y1),(x0,y1)],
                                                'texCoord':[(0,0),(1,0),(1,1),(0,1)]})
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

    def draw_world(self, context, player):
        self.flush()
        if not self.shader or not player or not player.in_world:
            return
        blend,depth,mask = gpu.state.blend_get(),gpu.state.depth_test_get(),gpu.state.depth_mask_get()
        try:
            gpu.state.depth_test_set('LESS_EQUAL')
            self.shader.bind()
            transform = context.region_data.perspective_matrix
            groups = list(self.sections.values())
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
                    eye = Vector(P.mc_to_blender(player.eye))
                    groups.sort(key=lambda g:(Vector(g[0])-eye).length_squared,reverse=True)
                for origin,batches in groups:
                    self.shader.uniform_float('transform',transform @ Matrix.Translation(origin))
                    for tex,is_transparent,batch in batches:
                        if is_transparent != translucent or tex not in self.textures:
                            continue
                        self.shader.uniform_sampler('atlas',self.textures[tex])
                        batch.draw(self.shader)
            self.draw_selection(context)
        finally:
            gpu.state.blend_set(blend)
            gpu.state.depth_test_set(depth)
            gpu.state.depth_mask_set(mask)

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
