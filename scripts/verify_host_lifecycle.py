"""Run with factory-startup background Blender; never in the user's editor.

Exercises the real load_pre handler, host constructor rollback, native mmap
ownership, timers and start/stop operators with an isolated mapping name.
"""
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
import uuid
import bpy

if '--installed' not in sys.argv:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import blender_minecraft as addon
from blender_minecraft import host, operators
from blender_minecraft.transport import HostLink

if not hasattr(bpy.types.Scene, 'mciblender'):
    addon.register()
name = 'Local\\MCInBlender_file_load_' + uuid.uuid4().hex
links = []


def isolated_link():
    link = HostLink(name)
    links.append(link)
    return link


def start():
    window = bpy.context.window
    area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
    region = next(r for r in area.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(window=window, area=area, region=region):
        assert bpy.ops.mciblender.start() == {'FINISHED'}
        session = addon.SESSION
        assert session and not session.closed and bpy.app.timers.is_registered(operators.tick)
        session.collision.step(bpy.context, budget_ms=0.01)
    return session


def stopped(session):
    assert addon.SESSION is None
    assert session.closed and session.link.closed and not session.link.alive
    assert session.link.address == 0 and not session.draw_handles
    assert not bpy.app.timers.is_registered(operators.tick)


with tempfile.TemporaryDirectory(prefix='mciblender-lifecycle-') as directory, patch.object(host, 'HostLink', isolated_link):
    path = str(Path(directory) / 'another-project.blend')
    bpy.ops.wm.save_as_mainfile(filepath=path)
    for cycle in range(3):
        previous = start()
        # This is the reported sequence: load another project while hosting.
        bpy.ops.wm.open_mainfile(filepath=path)
        stopped(previous)
        assert addon.before_load in bpy.app.handlers.load_pre
        assert addon.before_save in bpy.app.handlers.save_pre
        assert addon.scene_changed in bpy.app.handlers.depsgraph_update_post
        current = start()
        bpy.ops.mciblender.stop()
        bpy.ops.mciblender.stop()
        stopped(current)

    # A stale RNA/cleanup failure must not retain the mapping or global session.
    current = start()
    original_close = current.collision.close
    def failing_close():
        original_close()
        raise ReferenceError('injected stale RNA cleanup failure')
    current.collision.close = failing_close
    bpy.ops.mciblender.stop()
    stopped(current)
    assert any('injected stale RNA' in error for error in current.errors)
    current = start()
    bpy.ops.mciblender.stop()
    stopped(current)

    # Fail after acquiring the native mapping, before publishing SESSION.
    window = bpy.context.window
    area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
    region = next(r for r in area.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(window=window, area=area, region=region):
        with patch.object(host.Session, 'scene_signature', side_effect=RuntimeError('injected startup failure')):
            try:
                host.Session(bpy.context)
            except RuntimeError as exc:
                assert str(exc) == 'injected startup failure'
            else:
                raise AssertionError('Expected startup failure')
    assert links[-1].closed and not links[-1].alive
    current = start()
    bpy.ops.mciblender.stop()
    stopped(current)

    # Switching scenes without loading a file also retires the original host.
    current = start()
    previous_scene = bpy.context.window.scene
    temporary_scene = bpy.data.scenes.new('Changed while hosting')
    bpy.context.window.scene = temporary_scene
    assert operators.tick() is None
    stopped(current)
    bpy.context.window.scene = previous_scene
    bpy.data.scenes.remove(temporary_scene)

    current = start()
    area = current.area
    area.type = 'TEXT_EDITOR'
    assert operators.tick() is None
    stopped(current)
    area.type = 'VIEW_3D'

if 'blender_minecraft' in bpy.context.preferences.addons:
    bpy.ops.preferences.addon_disable(module='blender_minecraft')
else:
    addon.unregister()
assert addon.before_load not in bpy.app.handlers.load_pre
print('HOST_LIFECYCLE_PASS: 3 file reloads, repeated stop/start, failed cleanup/startup, scene/editor changes', flush=True)
