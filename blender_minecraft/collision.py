"""Export evaluated Blender scene geometry to SkyCraft's host collision stream."""
import math
import struct
from collections import defaultdict, deque
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from .protocol import blender_to_mc

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

    def rebuild(self, context, incremental=False):
        previous = self.sent.copy() if incremental else set()
        if not incremental:
            self.epoch += 1
        self.triangles.clear()
        self.boxes.clear()
        self.mesh_volumes.clear()
        self.sent.clear()
        self.queue.clear()
        self.object_count = 0
        graph = context.evaluated_depsgraph_get()
        for original in context.scene.objects:
            if original.type != 'MESH' or original.get('mc_generated') or not original.get('mc_collision',True):
                continue
            if original.hide_get():
                continue
            obj = original.evaluated_get(graph)
            mesh = obj.to_mesh()
            try:
                mesh.calc_loop_triangles()
                points = [blender_to_mc(obj.matrix_world @ v.co) for v in mesh.vertices]
                if not points:
                    continue
                self.object_count += 1
                # Exact triangles govern the player. Opt-in box colliders additionally provide
                # efficient sub-voxel volumes to fluids, mobs, item drops and ray picking.
                if original.get('mc_collider') == 'BOX':
                    lo = tuple(min(p[a] for p in points) for a in range(3))
                    hi = tuple(max(p[a] for p in points) for a in range(3))
                    self.boxes.append((lo,hi))
                else:
                    # Closed evaluated meshes provide volume; open surfaces get a
                    # thin shell. This includes modifiers and animated transforms.
                    indices = [tuple(t.vertices) for t in mesh.loop_triangles]
                    if indices:
                        edge_counts = defaultdict(int)
                        for triangle in indices:
                            for a,b in zip(triangle,triangle[1:]+triangle[:1]):
                                edge_counts[tuple(sorted((a,b)))] += 1
                        closed = all(n==2 for n in edge_counts.values())
                        volume = sum(Vector(points[a]).dot(Vector(points[b]).cross(Vector(points[c]))) for a,b,c in indices)
                        if closed and volume<0:
                            indices = [(a,c,b) for a,b,c in indices]
                        tree = BVHTree.FromPolygons(points,indices,all_triangles=True)
                        lo = tuple(min(p[a] for p in points)-0.0625 for a in range(3))
                        hi = tuple(max(p[a] for p in points)+0.0625 for a in range(3))
                        self.mesh_volumes.append((lo,hi,tree,closed))
                for tri in mesh.loop_triangles:
                    pts = [points[i] for i in tri.vertices]
                    lo = [math.floor(min(p[a] for p in pts)/8) for a in range(3)]
                    hi = [math.floor(max(p[a] for p in pts)/8) for a in range(3)]
                    # Prevent a gigantic outlier in an unrelated modeling scene from allocating
                    # millions of buckets. Such scenes need a local collider export first.
                    if math.prod(hi[a]-lo[a]+1 for a in range(3)) > 100000:
                        raise ValueError(f'Collider {original.name} is too large; use meter-scale local scene geometry')
                    packed = struct.pack('<9fI',*(c for p in pts for c in p),0)
                    for x in range(lo[0],hi[0]+1):
                        for y in range(lo[1],hi[1]+1):
                            for z in range(lo[2],hi[2]+1):
                                self.triangles[x,y,z].append(packed)
            finally:
                obj.to_mesh_clear()
        if not incremental:
            self.queue.append((1,struct.pack('<I',self.epoch)))
        self.refresh_regions = previous

    def nearby(self, position, radius=3):
        center = tuple(math.floor(v/8) for v in position)
        regions = [(x,y,z) for x in range(center[0]-radius,center[0]+radius+1)
                   for y in range(center[1]-2,center[1]+3)
                   for z in range(center[2]-radius,center[2]+radius+1)]
        regions = list(set(regions) | getattr(self,'refresh_regions',set()))
        self.refresh_regions = set()
        regions.sort(key=lambda r:sum((r[a]-center[a])**2 for a in range(3)))
        for key in regions:
            if key in self.sent:
                continue
            self.sent.add(key)
            lo = tuple(v*8 for v in key)
            hi = tuple(v+7 for v in lo)
            tris = self.triangles.get(key,[])
            head = struct.pack('<6iII',*lo,*hi,self.epoch,len(tris))
            self.queue.append((3,head+b''.join(tris)))
            cells = {}
            for box_lo,box_hi in self.boxes:
                low = [max(lo[a],math.floor(box_lo[a])) for a in range(3)]
                high = [min(hi[a],math.ceil(box_hi[a])-1) for a in range(3)]
                for x in range(low[0],high[0]+1):
                    for y in range(low[1],high[1]+1):
                        for z in range(low[2],high[2]+1):
                            bits = cells.setdefault((x,y,z),[0]*8)
                            mins = [max(0,math.ceil((box_lo[a]-(x,y,z)[a])*8-0.5)) for a in range(3)]
                            maxs = [min(7,math.floor((box_hi[a]-(x,y,z)[a])*8-0.5)) for a in range(3)]
                            for iy in range(mins[1],maxs[1]+1):
                                for iz in range(mins[2],maxs[2]+1):
                                    for ix in range(mins[0],maxs[0]+1):
                                        bits[iy] |= 1 << (iz*8+ix)
            for bounds_lo,bounds_hi,tree,closed in self.mesh_volumes:
                low = [max(lo[a],math.floor(bounds_lo[a])) for a in range(3)]
                high = [min(hi[a],math.ceil(bounds_hi[a])-1) for a in range(3)]
                for x in range(low[0],high[0]+1):
                    for y in range(low[1],high[1]+1):
                        for z in range(low[2],high[2]+1):
                            center = Vector((x+0.5,y+0.5,z+0.5))
                            point,normal,face,distance = tree.find_nearest(center)
                            if point is None:
                                continue
                            inside = closed and (center-point).dot(normal)<0
                            if distance>0.974:
                                if inside:
                                    cells[x,y,z] = list(FULL)
                                continue
                            bits = cells.setdefault((x,y,z),[0]*8)
                            for iy in range(8):
                                for iz in range(8):
                                    for ix in range(8):
                                        sample = Vector((x+(ix+0.5)/8,y+(iy+0.5)/8,z+(iz+0.5)/8))
                                        p,n,face,d = tree.find_nearest(sample)
                                        if p is not None and (d<=0.1083 or (closed and (sample-p).dot(n)<0)):
                                            bits[iy] |= 1 << (iz*8+ix)
            entries = [struct.pack('<iiiI8Q',*p,0,*bits) for p,bits in cells.items() if any(bits)]
            head = struct.pack('<6iII',*lo,*hi,self.epoch,len(entries))
            self.queue.append((2,head+b''.join(entries)))

    def flush(self, link, maximum=32):
        for _ in range(min(maximum,len(self.queue))):
            kind,payload = self.queue[0]
            if not link.send_collision(kind,payload):
                break
            self.queue.popleft()
