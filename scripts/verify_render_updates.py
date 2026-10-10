"""GPU regression checks; call run() from a Blender draw callback."""
import struct
from types import SimpleNamespace
import numpy as np
import gpu
from mathutils import Matrix
from blender_minecraft.renderer import ViewportRenderer, DTYPE, texture


def read(tex):
    raw=tex.read()
    raw.dimensions=(tex.width*tex.height*4,)
    return np.asarray(raw.to_list(),dtype=np.uint8).reshape(tex.height,tex.width,4)


def run():
    r=ViewportRenderer()
    previous_texture=None
    for frame,(w,h,flags) in enumerate(((9,7,1),(9,7,1),(9,7,0),(6,4,1)),1):
        pixels=np.random.default_rng(frame).integers(0,256,(h,w,4),dtype=np.uint8)
        r.overlay_pending=(w,h,flags,frame,pixels.tobytes())
        # Upload from a clipped editor with a nonzero viewport origin. The
        # owned FBO must not inherit that clipping or alter the caller's state.
        viewport,scissor=gpu.state.viewport_get(),gpu.state.scissor_get()
        try:
            gpu.state.viewport_set(7,11,31,29)
            gpu.state.scissor_set(13,17,3,2)
            gpu.state.scissor_test_set(True)
            r.upload_overlay()
            assert gpu.state.viewport_get()==(7,11,31,29)
            assert gpu.state.scissor_get()==(13,17,3,2)
        finally:
            gpu.state.viewport_set(*viewport)
            gpu.state.scissor_set(*scissor)
            gpu.state.scissor_test_set(False)
        assert r.byte_overlay, r.errors
        if frame in (2,3):
            assert r.overlay_texture is previous_texture
        previous_texture=r.overlay_texture
        np.testing.assert_array_equal(read(r.overlay_texture),pixels if flags else pixels[::-1])
    # Minecraft can publish another frame with identical HUD pixels. Reuse the
    # completed image while still acknowledging the newest frame number.
    r.overlay_uploader.upload=lambda *args,**kwargs: (_ for _ in ()).throw(AssertionError('duplicate upload'))
    r.overlay_pending=(w,h,flags,frame+1,pixels.tobytes())
    r.upload_overlay()
    assert r.byte_overlay and r.overlay_frame==frame+1
    # A backend failure must retain the legacy path instead of losing the HUD.
    pixels[:]=0
    r.overlay_pending=(w,h,flags,frame+2,pixels.tobytes())
    r.upload_overlay()
    assert not r.byte_overlay and r.errors
    np.testing.assert_array_equal(read(r.overlay_texture),pixels)
    r.pending[('section',0,0,0)]=(2,b'invalid payload must not be uploaded while hidden')
    r.accept(14,struct.pack('<IIII',0,1,1,0)+bytes((25,50,75,255)))
    r.flush(world_visible=False)
    assert len(r.pending)==1 and r.performance['mesh_upload_ms']==0
    np.testing.assert_array_equal(read(r.environment_textures[0]),np.array([[[25,50,75,255]]],dtype=np.uint8))

    # Compare the final pixels, including translucency, across cell boundaries.
    renderers=[ViewportRenderer(),ViewportRenderer()]
    renderers[0].batch_sections=False
    for renderer in renderers:
        renderer.textures[0]=texture(1,1,bytes((255,255,255,255)))
        for key in ((-1,0,0),(0,0,0),(1,0,0)):
            v=np.zeros(6,dtype=DTYPE)
            v['position']=[(0,0,0),(12,0,0),(0,0,12),(1,-1,1),(11,-1,1),(1,-1,11)]
            v['color'][:3]=(40,190,90,255)
            v['color'][3:]=(200,70,30,128)
            v['flags'][3:]=2
            v['light']=15
            renderer.accept(2,struct.pack('<iiiI',*key,len(v))+v.tobytes())
        while renderer.pending or renderer.section_batches.dirty:
            renderer.flush(budget_ms=1000,upload_overlay=False)
    context=SimpleNamespace(region_data=SimpleNamespace(
        perspective_matrix=Matrix.Diagonal((1/40,1/40,1/40,1)),view_matrix=Matrix.Identity(4),
        is_perspective=True))
    player=SimpleNamespace(in_world=True,position=(0,0,0),camera_mode=0)
    off=gpu.types.GPUOffScreen(128,128)
    old=gpu.state.viewport_get()
    outputs=[]
    try:
        with off.bind():
            gpu.state.viewport_set(0,0,128,128)
            r.environment={'atmosphere':{'skyColor':(0.2,0.5,0.8),'fogColor':(0.1,0.2,0.3),
                                         'skybox':'OVERWORLD'}}
            for key in (0,1,4):
                r.environment_textures[key]=texture(1,1,bytes(4))
            for environment in (False,True):
                gpu.state.active_framebuffer_get().clear(color=(0,0,0,0),depth=1)
                r.draw_world(context,player,show_selection=False,world_visible=False,environment=environment)
                raw=gpu.state.active_framebuffer_get().read_color(0,0,128,128,4,0,'UBYTE')
                raw.dimensions=(128*128*4,)
                assert bool(np.count_nonzero(raw.to_list()))==environment
            for renderer in renderers:
                gpu.state.active_framebuffer_get().clear(color=(0,0,0,0),depth=1)
                renderer.draw_world(context,player,show_selection=False,environment=False)
                raw=gpu.state.active_framebuffer_get().read_color(0,0,128,128,4,0,'UBYTE')
                raw.dimensions=(128*128*4,)
                outputs.append(np.asarray(raw.to_list(),dtype=np.uint8))
        assert np.count_nonzero(outputs[0])>100
        np.testing.assert_array_equal(*outputs)
        # Delete one cell, then compare again through the same update path.
        for renderer in renderers:
            renderer.accept(2,struct.pack('<iiiI',0,0,0,0))
            while renderer.pending or renderer.section_batches.dirty:
                renderer.flush(budget_ms=1000,upload_overlay=False)
        with off.bind():
            gpu.state.viewport_set(0,0,128,128)
            outputs=[]
            for renderer in renderers:
                gpu.state.active_framebuffer_get().clear(color=(0,0,0,0),depth=1)
                renderer.draw_world(context,player,show_selection=False,environment=False)
                raw=gpu.state.active_framebuffer_get().read_color(0,0,128,128,4,0,'UBYTE')
                raw.dimensions=(128*128*4,)
                outputs.append(np.asarray(raw.to_list(),dtype=np.uint8))
            np.testing.assert_array_equal(*outputs)
    finally:
        gpu.state.viewport_set(*old)
        off.free()
    return {'overlay_pixels':'exact including reuse, flip, resize, clipping and fallback',
            'hidden_upload':'terrain skipped; sky toggle independent',
            'batched_pixels':'exact including transparency and deletion'}
