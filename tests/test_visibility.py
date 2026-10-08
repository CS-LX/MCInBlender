import unittest
import numpy as np
from blender_minecraft.visibility import visible_bounds


class VisibilityTests(unittest.TestCase):
    def setUp(self):
        # 90 degree perspective camera, looking along -Z, near 1 and far 10.
        self.matrix = np.array([[1,0,0,0],[0,1,0,0],[0,0,-11/9,-20/9],[0,0,-1,0]],dtype=np.float32)

    def test_inside_behind_and_beyond_far(self):
        mask = visible_bounds([(0,0,-5),(0,0,5),(0,0,-12)],[(0.1,)*3]*3,self.matrix)
        self.assertEqual(mask.tolist(),[True,False,False])

    def test_keep_bounds_crossing_screen_and_near_plane(self):
        mask = visible_bounds([(5.5,0,-5),(0,0,-0.8),(7,0,-5)],[(1,)*3,(0.3,)*3,(0.1,)*3],self.matrix)
        self.assertEqual(mask.tolist(),[True,True,False])

    def test_uses_view_transform_and_supports_orthographic(self):
        view = np.eye(4)
        view[0,3] = -20
        mask = visible_bounds([(20,0,-5),(0,0,-5)],[(0.1,)*3]*2,self.matrix@view)
        self.assertEqual(mask.tolist(),[True,False])
        self.assertEqual(visible_bounds([(0,0,0),(2,0,0)],[(0.2,)*3]*2,np.eye(4)).tolist(),[True,False])

    def test_empty_world(self):
        self.assertEqual(len(visible_bounds([],[],self.matrix)),0)
