"""MCInBlender add-on. Importable without bpy for wire-protocol tests."""
bl_info = {'name':'Minecraft in Blender','author':'CS-LX; SkyCraft by chasmlol',
           'version':(0,1,0),'blender':(5,0,0),'location':'3D View > Sidebar > Minecraft',
           'description':'Blender host for the SkyCraft Minecraft bridge','category':'3D View'}

SESSION = None


def before_save(_):
    # Runtime helpers must not become permanent content of a user's .blend file.
    # The next session tick recreates them after the synchronous save completes.
    if SESSION and not SESSION.closed:
        SESSION.native_lighting.close()


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
    bpy.app.handlers.save_pre.append(before_save)


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
    if before_save in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.remove(before_save)
    del bpy.types.Scene.mciblender
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
