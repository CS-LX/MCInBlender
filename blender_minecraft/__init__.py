"""MCInBlender add-on. Importable without bpy for wire-protocol tests."""
bl_info = {'name':'Minecraft in Blender','author':'CS-LX; SkyCraft by chasmlol',
           'version':(0,1,0),'blender':(5,0,0),'location':'3D View > Sidebar > Minecraft',
           'description':'Blender host for the SkyCraft Minecraft bridge','category':'3D View'}

SESSION = None


def stop_session(expected=None):
    """Detach callbacks first; cleanup must not leave a half-closed host live."""
    import bpy
    from .operators import tick
    global SESSION
    session = SESSION
    if expected is not None and session is not expected:
        return
    SESSION = None
    try:
        if bpy.app.timers.is_registered(tick):
            bpy.app.timers.unregister(tick)
    finally:
        if session:
            session.close()


def before_load(_):
    # load_pre runs while the scene, area and any evaluated meshes are valid.
    # Blender discards nonpersistent timers on load, but Python globals survive.
    stop_session()


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
    from .distribution import CLASSES as DISTRIBUTION_CLASSES
    for cls in (*DISTRIBUTION_CLASSES, *CLASSES):
        bpy.utils.register_class(cls)
    bpy.types.Scene.mciblender = bpy.props.PointerProperty(type=Settings)
    for handlers, callback in ((bpy.app.handlers.depsgraph_update_post, scene_changed),
                               (bpy.app.handlers.save_pre, before_save),
                               (bpy.app.handlers.load_pre, before_load)):
        bpy.app.handlers.persistent(callback)
        if callback not in handlers:
            handlers.append(callback)


def unregister():
    import bpy
    from .operators import CLASSES
    from .distribution import CLASSES as DISTRIBUTION_CLASSES
    stop_session()
    if scene_changed in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(scene_changed)
    if before_save in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.remove(before_save)
    if before_load in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(before_load)
    del bpy.types.Scene.mciblender
    for cls in reversed((*DISTRIBUTION_CLASSES, *CLASSES)):
        bpy.utils.unregister_class(cls)
