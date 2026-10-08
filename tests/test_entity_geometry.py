"""Protocol-generated entities must retain dimensions, UVs and projectile orientation."""
import struct
import unittest
from blender_minecraft.entity_geometry import build


def record(kind, position=(1,2,3), yaw=0, pitch=0, scale=0.5):
    return struct.pack('<II21fI',kind,42,*position,yaw,pitch,scale,1,1,1,
                       0,0,1,1,0,0,1,1,0,0,1,1,0)


class EntityGeometryTests(unittest.TestCase):
    def test_item_sprite_size_and_axes(self):
        positions,uvs,colors,solid = build([record(2)])
        self.assertEqual(len(positions),6)
        self.assertEqual(solid,6)
        self.assertAlmostEqual(float(positions[:,0].max()-positions[:,0].min()),0.5)
        self.assertAlmostEqual(float(positions[:,2].max()-positions[:,2].min()),0.5)
        self.assertTrue((positions[:,1] == -3).all())

    def test_blocks_and_cracks_have_six_faces_and_separate_blend_pass(self):
        positions,uvs,colors,solid = build([record(5),record(4)])
        self.assertEqual(len(positions),72)
        self.assertEqual(solid,36)
        self.assertAlmostEqual(float(positions[:36,0].max()-positions[:36,0].min()),0.5)

    def test_vertical_arrow_has_finite_geometry(self):
        import numpy as np
        positions,_,_,solid = build([record(1,pitch=90)])
        self.assertEqual(solid,18)
        self.assertTrue(np.isfinite(positions).all())


if __name__ == '__main__':
    unittest.main()
