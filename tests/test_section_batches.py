import struct
import unittest
import numpy as np
from blender_minecraft.section_batches import SectionBatches, VERTEX


def section(key, flags=(0,2)):
    v=np.zeros(len(flags)*3,dtype=VERTEX)
    v['position']=np.tile([(0,0,0),(1,0,0),(0,1,0)],(len(flags),1))
    v['flags']=np.repeat(flags,3)
    v['color']=(200,150,100,255)
    v['light']=15
    return struct.pack('<iiiI',*key,len(v))+v.tobytes()


class SectionBatchTests(unittest.TestCase):
    def test_merge_keeps_world_coordinates_and_only_opaque_triangles(self):
        cache=SectionBatches()
        cache.update(section((-1,1,0)))
        cache.update(section((-2,2,1)))
        group,payload=cache.pop()
        self.assertEqual(group,(-1,0,0))
        x,y,z,n=struct.unpack_from('<iiiI',payload)
        self.assertEqual((x,y,z,n),(-4,0,0,6))
        v=np.frombuffer(payload,dtype=VERTEX,offset=16)
        np.testing.assert_array_equal(v['position'][[0,3]]+np.array([x,y,z])*16,
                                      [(-16,16,0),(-32,32,16)])
        self.assertTrue(np.all(v['flags']==0))
        self.assertTrue(np.all(v['color']==(200,150,100,255)))

    def test_replacement_and_deletion_do_not_leave_stale_geometry(self):
        cache=SectionBatches()
        cache.update(section((0,0,0)))
        cache.update(section((0,0,0),(0,0,0)))
        _,payload=cache.pop()
        self.assertEqual(struct.unpack_from('<I',payload,12)[0],9)
        cache.update(section((0,0,0),(2,)))
        _,payload=cache.pop()
        self.assertEqual(struct.unpack_from('<I',payload,12)[0],0)
        self.assertFalse(cache.groups)

    def test_separate_cells_and_coalesced_updates(self):
        cache=SectionBatches()
        cache.update(section((0,0,0)))
        cache.update(section((1,0,0)))
        cache.update(section((4,0,0)))
        self.assertEqual(len(cache.dirty),2)
        self.assertEqual(cache.pop()[0],(0,0,0))
        self.assertEqual(cache.pop()[0],(1,0,0))
