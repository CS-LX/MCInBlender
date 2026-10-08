"""Load the working add-on in a separate Blender instance; never edits user startup files."""
import sys
import os
from pathlib import Path
import bpy
bpy.context.preferences.view.show_splash = False

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import blender_minecraft
blender_minecraft.register()


def start():
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    region = next(r for r in area.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(area=area,region=region):
        if os.environ.get('MCIBLENDER_USE_CURRENT_SCENE'):
            pass # Preserve the loaded file's models, materials, modifiers and scene.
        elif os.environ.get('MCIBLENDER_WORLD') == 'normal':
            scene = bpy.data.scenes.new('Minecraft Survival')
            bpy.context.window.scene = scene
            area.spaces.active.shading.background_type = 'VIEWPORT'
            area.spaces.active.shading.background_color = (0.35,0.55,0.8)
        else:
            bpy.ops.mciblender.demo()
        bpy.ops.mciblender.start()
    area.spaces.active.show_region_ui = True
    for ui in area.regions:
        if ui.type == 'UI' and hasattr(ui,'active_panel_category'):
            ui.active_panel_category = 'Minecraft'
    print('MCInBlender host ready',flush=True)
    return None


bpy.app.timers.register(start,first_interval=1)
