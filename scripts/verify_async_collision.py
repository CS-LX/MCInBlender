"""Blender regression for bounded export, cancellation and collision replacement.

Run in a factory-startup background process, never in the user's editor.
Pass --profile-scene after -- to profile the already opened file read-only.
"""
import json
from pathlib import Path
import struct
import sys
import time
import bpy

ROOT = Path(__file__).resolve().parents[1]
if '--installed' not in sys.argv:
    sys.path.insert(0, str(ROOT))
from blender_minecraft.collision import SceneCollision, FULL


class Receiver:
    def __init__(self):
        self.regions = {}
        self.blocked = False

    def send_collision(self, kind, payload):
        if self.blocked:
            return False
        if kind == 1:
            self.regions.clear()
        else:
            self.regions[kind, struct.unpack_from('<3i', payload)] = bytes(payload)
        return True


def drain(collision, receiver, timeout=45):
    start = last_print = time.monotonic()
    calls, longest = 0, 0
    phases = set()
    while collision.busy:
        before = time.perf_counter()
        collision.step(bpy.context, budget_ms=4)
        elapsed = time.perf_counter()-before
        longest = max(longest, elapsed)
        calls += 1
        collision.flush(receiver)
        phases.add(collision.phase)
        assert not collision.error, collision.error
        now = time.monotonic()
        assert now-start < timeout, collision.status()
        if now-last_print > 1:
            print('COLLISION_PROGRESS '+json.dumps(collision.status(), ensure_ascii=False), flush=True)
            last_print = now
    return {'steps': calls, 'max_step_ms': round(longest*1000, 2),
            'seconds': round(time.monotonic()-start, 2), 'phases': sorted(phases)}


def profile():
    collision, receiver = SceneCollision(), Receiver()
    start = time.perf_counter()
    collision.rebuild(bpy.context)
    queued_ms = (time.perf_counter()-start)*1000
    collision.nearby((0, 0, 2))
    results = drain(collision, receiver, timeout=360)
    results.update({'file': bpy.data.filepath, 'objects': collision.object_count,
                    'queue_ms': round(queued_ms, 2), 'status': collision.status()})
    print('ASYNC_SCENE_PROFILE '+json.dumps(results, ensure_ascii=False), flush=True)
    collision.close()


def regression():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.ops.mesh.primitive_cube_add(size=2, location=(2, -2, 2))
    cube = bpy.context.object
    collision, receiver = SceneCollision(), Receiver()
    collision.rebuild(bpy.context)
    assert not collision.initialized and collision.object_count == 0
    collision.nearby((2, 2, 2))
    initial = drain(collision, receiver)
    assert initial['steps'] > 1, 'Work must yield before finishing the volume'
    assert collision.object_count == 1
    assert collision.mesh_volumes[0][3], 'Closed cube must retain solid volume'
    tri = receiver.regions[3, (0, 0, 0)]
    assert struct.unpack_from('<I', tri, 28)[0] == 12
    cells = receiver.regions[2, (0, 0, 0)]
    records = [struct.unpack_from('<iiiI8Q', cells, at) for at in range(32, len(cells), 80)]
    assert next(r[4:] for r in records if r[:3] == (1, 1, 1)) == FULL

    # Cancelling a rebuild must keep the committed snapshot and live packets.
    old_triangles = collision.triangles
    collision.rebuild(bpy.context, incremental=True)
    collision.step(bpy.context, budget_ms=0.001)
    collision.cancel()
    assert not collision.building and collision.triangles is old_triangles
    assert collision.cancelled

    # Evaluated meshes must not be referenced after a yield: edit the original
    # between callbacks, then explicitly export the latest evaluated geometry.
    cube.location.x += 16
    bpy.context.view_layer.update()
    collision.rebuild(bpy.context, incremental=True)
    collision.nearby((18, 2, 2))
    moved = drain(collision, receiver)
    assert struct.unpack_from('<I', receiver.regions[3, (0, 0, 0)], 28)[0] == 0
    assert struct.unpack_from('<I', receiver.regions[2, (0, 0, 0)], 28)[0] == 0
    assert struct.unpack_from('<I', receiver.regions[3, (16, 0, 0)], 28)[0] == 12

    # A second update after cancelling a partially sent refresh must still
    # remove older regions that the first refresh had not reached yet.
    cube.location.x += 16
    bpy.context.view_layer.update()
    collision.rebuild(bpy.context, incremental=True)
    collision.nearby((34, 2, 2))
    while collision.building:
        collision.step(bpy.context, budget_ms=0.001)
    collision.cancel()
    assert (2, 0, 0) in collision.refresh_regions
    cube.location.x += 16
    bpy.context.view_layer.update()
    collision.rebuild(bpy.context, incremental=True)
    collision.nearby((50, 2, 2))
    drain(collision, receiver)
    assert struct.unpack_from('<I', receiver.regions[3, (16, 0, 0)], 28)[0] == 0

    # Deleting an object between export batches must not dereference its
    # temporary evaluated mesh. A subsequent update removes that snapshot.
    bpy.ops.mesh.primitive_cube_add(size=1, location=(50, -2, 2))
    transient = bpy.context.object
    transient.name = 'A transient collider'
    transient_name = transient.name
    collision.rebuild(bpy.context, incremental=True)
    for _ in range(200):
        collision.step(bpy.context, budget_ms=0.001)
        if collision.phase == 'Transforming vertices' and collision.object_name == transient_name:
            break
    assert collision.phase == 'Transforming vertices' and collision.object_name == transient_name
    bpy.data.objects.remove(transient, do_unlink=True)
    bpy.context.view_layer.update()
    drain(collision, receiver)
    collision.rebuild(bpy.context, incremental=True)
    drain(collision, receiver)
    assert collision.object_count == 1

    # Backpressure is bounded, so a disconnected client cannot make a timer
    # build an unbounded queue of multi-megabyte packets.
    receiver.blocked = True
    collision.queue.extend([(2, b'pending')]*16)
    before = len(collision.queue)
    collision.step(bpy.context)
    assert len(collision.queue) == before
    receiver.blocked = False
    collision.queue.clear()

    # A geometry error should be visible and preserve the last good snapshot.
    old_triangles = collision.triangles
    cube.scale = (1000000, 1000000, 1000000)
    cube['mc_collider'] = 'BOX'
    bpy.context.view_layer.update()
    collision.rebuild(bpy.context, incremental=True)
    for _ in range(100):
        collision.step(bpy.context)
        if collision.error:
            break
    assert collision.error and 'too large' in collision.error
    assert collision.triangles is old_triangles
    assert not collision.building
    collision.close()
    assert not collision.busy
    print('ASYNC_COLLISION_PASS '+json.dumps({'initial': initial, 'moved': moved}), flush=True)


if '--profile-scene' in sys.argv:
    profile()
else:
    regression()
