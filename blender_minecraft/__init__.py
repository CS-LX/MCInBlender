"""MCInBlender add-on. Importable without bpy for wire-protocol tests."""
bl_info = {'name':'Minecraft in Blender','author':'CS-LX; SkyCraft by chasmlol',
           'version':(0,1,0),'blender':(5,0,0),'location':'3D View > Sidebar > Minecraft',
           'description':'Blender host for the SkyCraft Minecraft bridge','category':'3D View'}

SESSION = None


def scene_changed(scene, depsgraph):
    session = SESSION
    if not session or session.closed or scene != session.scene:
        return
    import bpy
    for update in depsgraph.updates:
        item = update.id.original
        if isinstance(item,bpy.types.Mesh) or (isinstance(item,bpy.types.Object) and item.type == 'MESH'
            and not item.get('mc_generated') and item.get('mc_collision',True)):
            if update.is_updated_geometry or update.is_updated_transform:
                session.collision_dirty = True
                break


def register():
    import bpy
    from .operators import CLASSES, Settings
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.mciblender = bpy.props.PointerProperty(type=Settings)
    bpy.app.handlers.depsgraph_update_post.append(scene_changed)


def unregister():
    import bpy
    from .operators import CLASSES, tick
    global SESSION
    if SESSION:
        SESSION.close()
        SESSION = None
    if bpy.app.timers.is_registered(tick):
        bpy.app.timers.unregister(tick)
    if scene_changed in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(scene_changed)
    del bpy.types.Scene.mciblender
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
