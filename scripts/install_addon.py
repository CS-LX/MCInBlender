"""Run with the target Blender --background --python ... -- ADDON.zip.

Uses normal user preferences and Blender's installer, preserving other add-ons.
"""
import json
from pathlib import Path
import sys
import bpy

args = sys.argv[sys.argv.index('--')+1:]
package = Path(args[0]).resolve()
if not package.is_file() or package.suffix != '.zip':
    raise ValueError('Expected a built add-on ZIP')
addon = 'blender_minecraft'
if addon in bpy.context.preferences.addons:
    bpy.ops.preferences.addon_disable(module=addon)
bpy.ops.preferences.addon_install(filepath=str(package), overwrite=True)
bpy.ops.preferences.addon_enable(module=addon)
if addon not in bpy.context.preferences.addons:
    raise RuntimeError('Add-on failed to enable')
bpy.ops.wm.save_userpref()
module = sys.modules[addon]
from blender_minecraft.paths import build_info, data_root
print('MCIBLENDER_INSTALLED '+json.dumps({'blender': bpy.app.version_string,
      'module': str(Path(module.__file__).resolve()), 'build': build_info(), 'data': str(data_root())}), flush=True)
