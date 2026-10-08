"""Time-sliced scene export. Blender data is accessed only on the main thread."""
import math
import struct
import time
from collections import defaultdict, deque
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

FULL = (0xFFFFFFFFFFFFFFFF,) * 8


class SceneCollision:
    def __init__(self):
        self.epoch = 1
        self.queue = deque()
        self.triangles = defaultdict(list)
        self.boxes = []
        self.mesh_volumes = []
        self.sent = set()
        self.object_count = 0
        self.initialized = False
        self.cancelled = False
        self.error = None
        self._build = self._region_job = None
        self._regions = deque()
        self._center = self._position = None
        self.refresh_regions = set()
        self.started = self.finished = time.monotonic()
        self.phase = 'Waiting'
        self.object_name = ''
        self.objects_done = self.objects_total = 0
        self.units_done = self.units_total = 0
        self.regions_done = self.regions_total = 0

    @property
    def building(self):
        return self._build is not None

    @property
    def busy(self):
        return self.building or self._region_job is not None or bool(self._regions) or bool(self.queue)

    def status(self):
        return {'phase': self.phase, 'busy': self.busy, 'building': self.building,
                'cancelled': self.cancelled, 'error': self.error, 'object': self.object_name,
                'objects_done': self.objects_done, 'objects_total': self.objects_total,
                'units_done': self.units_done, 'units_total': self.units_total,
                'regions_done': self.regions_done, 'regions_total': self.regions_total,
                'elapsed': round((time.monotonic() if self.busy else self.finished)-self.started, 1)}

    def rebuild(self, context, incremental=False):
        """Queue work only. Retain the old snapshot until extraction finishes."""
        if self.building:
            return False
        self._stop_jobs()
        self.cancelled = False
        self.error = None
        self.started = time.monotonic()
        self.phase = 'Queued scene export'
        self.object_name = ''
        self.objects_done = self.units_done = self.units_total = 0
        self.objects_total = len(context.scene.objects)
        self._build = self._rebuild(context.scene, incremental)
        return True

    def _stop_jobs(self):
        for job in (self._build, self._region_job):
            if job is not None:
                job.close()
        self._build = self._region_job = None
        self._regions.clear()

    def cancel(self):
        self._stop_jobs()
        self.cancelled = True
        self.phase = 'Cancelled - completed collision retained'
        self.finished = time.monotonic()

    def close(self):
        self._stop_jobs()
        self.queue.clear()

    def _rebuild(self, scene, incremental):
        triangles, boxes, volumes = defaultdict(list), [], []
        object_count = 0
        objects = list(scene.objects)
        self.objects_total = len(objects)
        yield
        for number, original in enumerate(objects):
            self.objects_done = number
            try:
                eligible = (original.type == 'MESH' and not original.get('mc_generated')
                            and original.get('mc_collision', True) and not original.hide_get())
            except ReferenceError:
                eligible = False
            if not eligible:
                yield
                continue
            self.object_name = original.name
            self.phase = 'Reading evaluated mesh'
            self.units_done = self.units_total = 0
            yield  # Display the object name before entering Blender's mesh API.
            import bpy
            try:
                graph = bpy.context.evaluated_depsgraph_get()
                obj = original.evaluated_get(graph)
                is_box = original.get('mc_collider') == 'BOX'
            except ReferenceError:
                continue
            mesh = obj.to_mesh()
            try:
                mesh.calc_loop_triangles()
                coords = np.empty(len(mesh.vertices)*3, dtype=np.float32)
                faces = np.empty(len(mesh.loop_triangles)*3, dtype=np.int32)
                mesh.vertices.foreach_get('co', coords)
                mesh.loop_triangles.foreach_get('vertices', faces)
                matrix = np.array(obj.matrix_world, dtype=np.float64)
            finally:
                obj.to_mesh_clear()
            # Only owned arrays survive a yield: dependency-graph updates may
            # invalidate evaluated IDs while Blender processes the next event.
            del mesh, obj, graph
            yield
            if not len(coords):
                continue
            object_count += 1
            points, indices = [], []
            coords, faces = coords.reshape(-1, 3), faces.reshape(-1, 3)
            low, high = np.full(3, np.inf), np.full(3, -np.inf)
            self.phase = 'Transforming vertices'
            self.units_total = len(coords)
            for start in range(0, len(coords), 4096):
                world = coords[start:start+4096] @ matrix[:3, :3].T + matrix[:3, 3]
                world = world[:, (0, 2, 1)] * (1, 1, -1)
                low, high = np.minimum(low, world.min(axis=0)), np.maximum(high, world.max(axis=0))
                points.extend(world.tolist())
                self.units_done = min(start+4096, len(coords))
                yield
            for start in range(0, len(faces), 4096):
                indices.extend(faces[start:start+4096].tolist())
                yield
            if is_box:
                boxes.append((tuple(low), tuple(high)))
            elif indices:
                self.phase = 'Checking mesh volume'
                self.units_total = len(indices)
                edge_counts = defaultdict(int)
                volume = 0.0
                for i, (a, b, c) in enumerate(indices):
                    for u, v in ((a, b), (b, c), (c, a)):
                        edge_counts[min(u, v), max(u, v)] += 1
                    pa, pb, pc = points[a], points[b], points[c]
                    volume += (pa[0]*(pb[1]*pc[2]-pb[2]*pc[1])
                               + pa[1]*(pb[2]*pc[0]-pb[0]*pc[2])
                               + pa[2]*(pb[0]*pc[1]-pb[1]*pc[0]))
                    if i % 256 == 0:
                        self.units_done = i
                        yield
                closed = True
                for i, count in enumerate(edge_counts.values()):
                    if count != 2:
                        closed = False
                        break
                    if i % 4096 == 0:
                        yield
                if closed and volume < 0:
                    for i, triangle in enumerate(indices):
                        triangle[1], triangle[2] = triangle[2], triangle[1]
                        if i % 4096 == 0:
                            yield
                del edge_counts
                self.phase = 'Building mesh collision tree'
                self.units_done = self.units_total
                yield
                tree = BVHTree.FromPolygons(points, indices, all_triangles=True)
                volumes.append((tuple(low-0.0625), tuple(high+0.0625), tree, closed))
                yield
            self.phase = 'Indexing player collision'
            self.units_total = len(indices)
            bucket_count = 0
            for i, triangle in enumerate(indices):
                pts = [points[v] for v in triangle]
                lo = [math.floor(min(p[a] for p in pts)/8) for a in range(3)]
                hi = [math.floor(max(p[a] for p in pts)/8) for a in range(3)]
                if math.prod(hi[a]-lo[a]+1 for a in range(3)) > 100000:
                    raise ValueError(f'Collider {self.object_name} is too large; use meter-scale local scene geometry')
                packed = struct.pack('<9fI', *(c for p in pts for c in p), 0)
                for x in range(lo[0], hi[0]+1):
                    for y in range(lo[1], hi[1]+1):
                        for z in range(lo[2], hi[2]+1):
                            triangles[x, y, z].append(packed)
                            bucket_count += 1
                            if bucket_count % 512 == 0:
                                yield
                if i % 128 == 0:
                    self.units_done = i
                    yield
            yield
        self.objects_done = self.objects_total
        self.units_done = self.units_total
        previous = self.sent | self.refresh_regions if incremental else set()
        self.triangles, self.boxes, self.mesh_volumes = triangles, boxes, volumes
        self.object_count = object_count
        self.sent.clear()
        self.queue.clear()
        if not incremental:
            self.epoch += 1
            self.queue.append((1, struct.pack('<I', self.epoch)))
        self.refresh_regions = previous
        self.initialized = True
        self._center = None
        self.object_name = ''
        self.phase = 'Preparing nearby collision'

    def nearby(self, position, radius=3):
        """Schedule regions; no voxel sampling happens in the caller."""
        self._position = tuple(position)
        if not self.initialized or self.building or self.cancelled or self.error:
            return
        center = tuple(math.floor(v/8) for v in position)
        if center == self._center:
            return  # Refresh regions are already included in the current queue.
        self._center = center
        if self._region_job is not None:
            self._region_job.close()
            self._region_job = None
        regions = {(x, y, z) for x in range(center[0]-radius, center[0]+radius+1)
                   for y in range(center[1]-2, center[1]+3)
                   for z in range(center[2]-radius, center[2]+radius+1)} | self.refresh_regions
        regions -= self.sent
        self._regions = deque(sorted(regions, key=lambda r: sum((r[a]-center[a])**2 for a in range(3))))
        self.regions_done, self.regions_total = 0, len(self._regions)
        if self._regions:
            if self.phase == 'Ready':
                self.started = time.monotonic()
            self.phase = 'Preparing nearby collision'

    def step(self, context, budget_ms=6):
        """Spend a small budget, then let Blender process UI events."""
        deadline = time.perf_counter()+budget_ms/1000
        try:
            while time.perf_counter() < deadline:
                if self._build is not None:
                    try:
                        next(self._build)
                    except StopIteration:
                        self._build = None
                        if self._position is not None:
                            self.nearby(self._position)
                    continue
                if self.cancelled or self.error:
                    break
                if len(self.queue) >= 16:
                    self.phase = 'Waiting for Minecraft to receive collision'
                    break
                if self._region_job is None:
                    if not self._regions:
                        if self.phase != 'Ready' and not self.queue:
                            self.finished = time.monotonic()
                        self.phase = 'Sending collision' if self.queue else 'Ready'
                        break
                    self._region_job = self._voxelize(self._regions.popleft())
                try:
                    next(self._region_job)
                except StopIteration:
                    self._region_job = None
                    self.regions_done += 1
        except Exception as exc:
            self.error = f'{self.phase}: {self.object_name}: {exc}'
            self._stop_jobs()
            self.phase = 'Collision update failed'
            self.finished = time.monotonic()

    def _voxelize(self, key):
        lo = tuple(v*8 for v in key)
        hi = tuple(v+7 for v in lo)
        tris = self.triangles.get(key, [])
        self.phase = 'Sampling nearby collision'
        self.units_done, self.units_total = 0, 512
        cells = {}
        work = 0
        for box_lo, box_hi in self.boxes:
            low = [max(lo[a], math.floor(box_lo[a])) for a in range(3)]
            high = [min(hi[a], math.ceil(box_hi[a])-1) for a in range(3)]
            for x in range(low[0], high[0]+1):
                for y in range(low[1], high[1]+1):
                    for z in range(low[2], high[2]+1):
                        bits = cells.setdefault((x, y, z), [0]*8)
                        mins = [max(0, math.ceil((box_lo[a]-(x, y, z)[a])*8-0.5)) for a in range(3)]
                        maxs = [min(7, math.floor((box_hi[a]-(x, y, z)[a])*8-0.5)) for a in range(3)]
                        row = ((1 << max(0, maxs[0]-mins[0]+1))-1) << mins[0]
                        for iy in range(mins[1], maxs[1]+1):
                            for iz in range(mins[2], maxs[2]+1):
                                bits[iy] |= row << (iz*8)
                        work += 1
                        if work % 16 == 0:
                            yield
            yield
        for bounds_lo, bounds_hi, tree, closed in self.mesh_volumes:
            low = [max(lo[a], math.floor(bounds_lo[a])) for a in range(3)]
            high = [min(hi[a], math.ceil(bounds_hi[a])-1) for a in range(3)]
            for x in range(low[0], high[0]+1):
                for y in range(low[1], high[1]+1):
                    for z in range(low[2], high[2]+1):
                        center = Vector((x+0.5, y+0.5, z+0.5))
                        point, normal, face, distance = tree.find_nearest(center)
                        if point is not None:
                            inside = closed and (center-point).dot(normal) < 0
                            if distance > 0.974:
                                if inside:
                                    cells[x, y, z] = list(FULL)
                            else:
                                bits = cells.setdefault((x, y, z), [0]*8)
                                for iy in range(8):
                                    for iz in range(8):
                                        for ix in range(8):
                                            sample = Vector((x+(ix+0.5)/8, y+(iy+0.5)/8, z+(iz+0.5)/8))
                                            p, n, face, d = tree.find_nearest(sample)
                                            if p is not None and (d <= 0.1083 or (closed and (sample-p).dot(n) < 0)):
                                                bits[iy] |= 1 << (iz*8+ix)
                                    yield  # At most 64 nearest-surface queries per batch.
                        self.units_done = (x-lo[0])*64+(y-lo[1])*8+z-lo[2]+1
                        work += 1
                        if work % 16 == 0:
                            yield
            yield
        payload = bytearray(struct.pack('<6iII', *lo, *hi, self.epoch, len(tris)))
        for start in range(0, len(tris), 1024):
            payload.extend(b''.join(tris[start:start+1024]))
            yield
        entries = []
        for i, (p, bits) in enumerate(cells.items()):
            if any(bits):
                entries.append(struct.pack('<iiiI8Q', *p, 0, *bits))
            if i % 64 == 0:
                yield
        head = struct.pack('<6iII', *lo, *hi, self.epoch, len(entries))
        self.queue.append((3, payload))
        self.queue.append((2, head+b''.join(entries)))
        self.sent.add(key)
        self.refresh_regions.discard(key)

    def flush(self, link, maximum=8):
        for _ in range(min(maximum, len(self.queue))):
            kind, payload = self.queue[0]
            if not link.send_collision(kind, payload):
                break
            self.queue.popleft()
        if self.initialized and not self.busy and not self.cancelled and not self.error and self.phase != 'Ready':
            self.phase = 'Ready'
            self.finished = time.monotonic()
