import math
import struct
import unittest
from blender_minecraft.light_sources import nearest_lights, sky_lighting
from blender_minecraft.protocol import ProtocolError


def record(key, lights):
    return struct.pack('<iiiI',*key,len(lights))+b''.join(struct.pack('<4BI',*row) for row in lights)


class NativeLightSelectionTests(unittest.TestCase):
    def test_negative_section_coordinates_color_and_kind(self):
        key = (-2,6,-1)
        found = nearest_lights({key:record(key,[(15,4,15,14,0xA366AAFF)])},
                               [((-18,100,-2),(-16,102,0))],(-18,102,2))
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]['key'],(-17,100,-1))
        self.assertEqual(found[0]['position'],(-16.5,100.5,-0.5))
        self.assertEqual(found[0]['color'],(1,170/255,102/255))
        self.assertEqual(found[0]['kind'],3) # Hazard bits must not affect light kind.

    def test_reaches_model_bounds_not_just_its_center_and_caps_selection(self):
        key = (0,0,0)
        payload = record(key,[(0,0,0,15,0xFFFFFF),(10,0,0,15,0xFFFFFF),(15,15,15,1,0xFFFFFF)])
        # The first light reaches the near edge of a very long native mesh.
        bounds = [((0,2,0),(1000,3,1))]
        selected = nearest_lights({key:payload},bounds,(0,0,0),1)
        self.assertEqual([s['key'] for s in selected],[(0,0,0)])
        self.assertEqual(len(nearest_lights({key:payload},bounds,(0,0,0))),2)
        self.assertEqual(nearest_lights({key:payload},[],(0,0,0)),[])
        self.assertEqual(nearest_lights({key:payload},bounds,(0,0,0),0),[])

    def test_corrupt_nearby_records_fail_instead_of_misplacing_lights(self):
        key = (0,0,0)
        bounds = [((0,0,0),(1,1,1))]
        for payload in (b'bad',record(key,[(16,0,0,15,0)]),record(key,[(0,0,0,16,0)]),
                        record((1,0,0),[]),record(key,[(0,0,0,15,0)])[:-1]):
            with self.subTest(payload=payload),self.assertRaises(ProtocolError):
                nearest_lights({key:payload},bounds,(0,0,0))
        self.assertEqual(nearest_lights({key:record(key,[])},bounds,(0,0,0)),[])

    def test_day_night_and_sunless_dimension_use_actual_palette(self):
        day = sky_lighting({'skybox':'OVERWORLD','sunAngle':0,'moonAngle':math.pi},
                           {'sky':[255,255,255,255]})
        night = sky_lighting({'skybox':'OVERWORLD','sunAngle':math.pi,'moonAngle':0},
                             {'sky':[71,71,129,255]})
        self.assertGreater(day['sun'],night['moon']*3)
        self.assertEqual(day['moon'],0)
        self.assertEqual(night['sun'],0)
        self.assertGreater(night['color'][2],night['color'][0])
        nether = sky_lighting({'skybox':'NONE'},{'dark':[70,25,25,255]},2)
        self.assertEqual((nether['sun'],nether['moon']),(0,0))
        self.assertGreater(nether['fill'],0)
        self.assertGreater(nether['color'][0],nether['color'][1])
