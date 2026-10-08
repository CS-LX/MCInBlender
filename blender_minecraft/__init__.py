"""MCInBlender add-on. Importable without bpy for wire-protocol tests."""
bl_info = {'name':'Minecraft in Blender','author':'CS-LX; SkyCraft by chasmlol',
           'version':(0,1,0),'blender':(5,0,0),'location':'3D View > Sidebar > Minecraft',
           'description':'Blender host for the SkyCraft Minecraft bridge','category':'3D View'}

SESSION = None


def register():
    import bpy
    from .operators import CLASSES, Settings
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.mciblender = bpy.props.PointerProperty(type=Settings)


def unregister():
    import bpy
    from .operators import CLASSES, tick
    global SESSION
    if SESSION:
        SESSION.close()
        SESSION = None
    if bpy.app.timers.is_registered(tick):
        bpy.app.timers.unregister(tick)
    del bpy.types.Scene.mciblender
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
