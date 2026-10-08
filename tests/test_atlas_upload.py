import struct
import unittest
import numpy as np
from blender_minecraft.atlas_upload import pack_patches
from blender_minecraft.protocol import ProtocolError


def patch(x,y,w,h,color):
    return struct.pack('<IIII',x,y,w,h)+bytes(color)*w*h


class AtlasUploadTests(unittest.TestCase):
    def test_shelf_packing_keeps_exact_pixels_and_target_rectangles(self):
        a = patch(4,2,2,3,(255,0,0,255))
        b = patch(10,6,3,1,(0,255,0,128))
        image,positions,uv = pack_patches([a,b],16,16,max_width=4)
        self.assertEqual(image.shape,(4,4,4))
        self.assertTrue(np.all(image[:3,:2]==(255,0,0,255)))
        self.assertTrue(np.all(image[3,:3]==(0,255,0,128)))
        self.assertEqual(positions[0],(-0.5,-0.75))
        self.assertEqual(positions[6],(0.25,-0.25))
        self.assertEqual(uv[6],(0,0.75))

    def test_rejects_corrupt_and_out_of_bounds_tiles(self):
        for raw in [b'bad',patch(15,0,2,1,(0,0,0,0)),patch(0,0,1,1,(0,0,0,0))[:-1]]:
            with self.assertRaises(ProtocolError):
                pack_patches([raw],16,16)

    def test_empty_batch(self):
        self.assertIsNone(pack_patches([],16,16)[0])
