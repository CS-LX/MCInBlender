"""Installed plug-in setup, bundled pack export and optional Prism launch."""
import os
from pathlib import Path
import shutil
import subprocess
import bpy
from bpy.props import StringProperty
from bpy_extras.io_utils import ExportHelper
from .paths import PACKAGE, build_info, data_root


class Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__
    prism_executable: StringProperty(name='Prism Launcher', subtype='FILE_PATH',
        description='Optional: path to prismlauncher.exe for launching the imported instance')
    prism_instance: StringProperty(name='Prism instance ID', default='MCInBlender',
        description='Folder name of the instance imported from the bundled Minecraft pack')

    def draw(self, context):
        layout = self.layout
        info = build_info()
        layout.label(text=f"MCInBlender {info['version']} · {info['channel']} · {info['sha'][:8]}")
        layout.label(text='1. Export and import the Minecraft pack in your launcher.')
        layout.label(text='2. Start Blender Host, then launch that Minecraft instance.')
        layout.operator('mciblender.export_pack', icon='EXPORT')
        layout.prop(self, 'prism_executable')
        layout.prop(self, 'prism_instance')
        layout.operator('mciblender.open_data', icon='FILE_FOLDER')
        layout.operator('wm.url_open', text='Installation and usage guide', icon='HELP').url = (
            'https://github.com/CS-LX/MCInBlender/blob/main/docs/INSTALL.md')


class ExportPack(bpy.types.Operator, ExportHelper):
    bl_idname = 'mciblender.export_pack'
    bl_label = 'Export Minecraft Pack'
    bl_description = 'Save the bundled precompiled pack; import it in Prism, HMCL or another MRPACK-capable launcher'
    filename_ext = '.mrpack'
    filter_glob: StringProperty(default='*.mrpack', options={'HIDDEN'})

    def invoke(self, context, event):
        self.filepath = f"MCInBlender-{build_info()['version']}.mrpack"
        return ExportHelper.invoke(self, context, event)

    def execute(self, context):
        source = PACKAGE/'resources'/'minecraft.mrpack'
        if not source.exists():
            self.report({'ERROR'}, 'Use a Release add-on ZIP; source checkouts do not bundle a Minecraft pack')
            return {'CANCELLED'}
        try:
            shutil.copyfile(source, bpy.path.abspath(self.filepath))
        except OSError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        self.report({'INFO'}, 'Pack saved. Import it in your Minecraft launcher and sign in there.')
        return {'FINISHED'}


class LaunchMinecraft(bpy.types.Operator):
    bl_idname = 'mciblender.launch_minecraft'
    bl_label = 'Launch Minecraft (Prism)'
    bl_description = 'Launch the configured Prism instance; start Blender Host first'

    def execute(self, context):
        from . import SESSION
        if not SESSION or SESSION.closed:
            self.report({'ERROR'}, 'Start Blender Host first')
            return {'CANCELLED'}
        if SESSION.link.alive:
            self.report({'WARNING'}, 'Minecraft is already connected')
            return {'CANCELLED'}
        addon = context.preferences.addons.get(__package__)
        prefs = addon.preferences if addon else None
        path = Path(bpy.path.abspath(prefs.prism_executable)) if prefs and prefs.prism_executable else None
        if not path or not path.is_file() or not prefs.prism_instance.strip():
            self.report({'ERROR'}, 'Set Prism executable and instance ID in add-on preferences, or launch Minecraft yourself')
            return {'CANCELLED'}
        try:
            subprocess.Popen([str(path), '--launch', prefs.prism_instance], cwd=path.parent,
                             creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        except OSError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


class OpenData(bpy.types.Operator):
    bl_idname = 'mciblender.open_data'
    bl_label = 'Open MCInBlender Logs / Data'

    def execute(self, context):
        bpy.ops.wm.path_open(filepath=str(data_root()))
        return {'FINISHED'}


CLASSES = (Preferences, ExportPack, LaunchMinecraft, OpenData)
