"""Coalesce opaque section triangles without changing transparent draw order."""
from collections import OrderedDict
import struct
import numpy as np

VERTEX = np.dtype([('position','<f4',3), ('uv','<f4',2), ('color','u1',4),
                   ('light','<u4'), ('flags','<u4')])


class SectionBatches:
    def __init__(self, size=4):
        self.size = size
        self.groups = {}
        self.dirty = OrderedDict()

    def update(self, payload):
        x,y,z,count = struct.unpack_from('<iiiI',payload)
        key = (x,y,z)
        group = tuple(v//self.size for v in key)
        records = self.groups.setdefault(group,{})
        vertices = np.frombuffer(payload, dtype=VERTEX, offset=16)
        # WorldExporter emits complete triangles with consistent flags.
        opaque = vertices.reshape(-1,3)[(vertices['flags'][::3] & 2)==0].ravel().copy()
        if len(opaque):
            opaque['position'] += np.asarray([(key[i]-group[i]*self.size)*16 for i in range(3)],dtype=np.float32)
            records[key] = opaque
        else:
            records.pop(key,None)
        self.dirty[group] = None
        if not records:
            self.groups.pop(group,None)

    def pop(self):
        group,_ = self.dirty.popitem(last=False)
        records = self.groups.get(group,{})
        vertices = np.concatenate(list(records.values())) if records else np.empty(0,dtype=VERTEX)
        origin = tuple(v*self.size for v in group)
        return group, struct.pack('<iiiI',*origin,len(vertices))+vertices.tobytes()
