"""Upload RGBA bytes through Blender's public GPU API without float expansion.

GPUTexture(data=...) only accepts floats in Blender 5.0. A normalized U8 vertex
attribute can carry the same bytes: one point writes one texel of a persistent
RGBA8 framebuffer. All work must run inside a viewport draw callback.
"""
import gpu
import numpy as np


class ByteImage:
    def __init__(self):
        interface = gpu.types.GPUStageInterfaceInfo('mciblender_byte_image')
        interface.flat('VEC4', 'pixel')
        info = gpu.types.GPUShaderCreateInfo()
        info.vertex_in(0, 'VEC4', 'color')
        info.vertex_out(interface)
        info.push_constant('IVEC2', 'imageSize')
        info.push_constant('INT', 'flipY')
        info.fragment_out(0, 'VEC4', 'fragColor')
        info.vertex_source('''void main(){
            ivec2 p=ivec2(gl_VertexID%imageSize.x,gl_VertexID/imageSize.x);
            if(flipY!=0) p.y=imageSize.y-1-p.y;
            gl_Position=vec4((vec2(p)+0.5)*2.0/vec2(imageSize)-1.0,0.0,1.0);
            gl_PointSize=1.0;
            pixel=color;
        }''')
        info.fragment_source('void main(){fragColor=pixel;}')
        self.shader = gpu.shader.create_from_info(info)
        self.format = gpu.types.GPUVertFormat()
        self.format.attr_add(id='color', comp_type='U8', len=4, fetch_mode='INT_TO_FLOAT_UNIT')
        self.texture = self.framebuffer = None
        self.size = None

    def upload(self, width, height, pixels, *, flip_y=False):
        if width <= 0 or height <= 0 or len(pixels) != width*height*4:
            raise ValueError('Invalid RGBA image dimensions')
        if self.size != (width, height):
            self.texture = gpu.types.GPUTexture((width, height), format='RGBA8')
            self.framebuffer = gpu.types.GPUFrameBuffer(color_slots=self.texture)
            self.size = (width, height)
        # Blender exposes static VBOs: filling an already drawn VBO is forbidden.
        # Only the byte buffer is replaced; the image and framebuffer are reused.
        vertices = gpu.types.GPUVertBuf(format=self.format, len=width*height)
        vertices.attr_fill(id='color', data=np.frombuffer(pixels, dtype=np.uint8).reshape(-1, 4))
        batch = gpu.types.GPUBatch(type='POINTS', buf=vertices)
        viewport = gpu.state.viewport_get()
        blend, depth, mask = gpu.state.blend_get(), gpu.state.depth_test_get(), gpu.state.depth_mask_get()
        try:
            with self.framebuffer.bind():
                gpu.state.viewport_set(0, 0, width, height)
                # Scissor state belongs to this framebuffer; binding restores
                # the caller's framebuffer and its clipping on exit.
                gpu.state.scissor_test_set(False)
                gpu.state.blend_set('NONE')
                gpu.state.depth_test_set('NONE')
                gpu.state.depth_mask_set(False)
                # Works with either fixed or shader-controlled point sizes.
                gpu.state.point_size_set(1)
                self.shader.bind()
                self.shader.uniform_int('imageSize', (width, height))
                self.shader.uniform_int('flipY', int(flip_y))
                batch.draw(self.shader)
        finally:
            gpu.state.viewport_set(*viewport)
            gpu.state.blend_set(blend)
            gpu.state.depth_test_set(depth)
            gpu.state.depth_mask_set(mask)
        return self.texture
