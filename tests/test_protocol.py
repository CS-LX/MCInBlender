import os
from pathlib import Path
import struct
import sys
import unittest
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from blender_minecraft import protocol as P
from blender_minecraft.transport import HostLink


class GeometryTests(unittest.TestCase):
    def test_coordinate_roundtrip_and_handedness(self):
        self.assertEqual(P.blender_to_mc(P.mc_to_blender((3,7,-2))),(3,7,-2))
        self.assertEqual(P.mc_to_blender((0,1,0)),(0,0,1))
        self.assertEqual(P.mc_to_blender((0,0,1)),(0,-1,0))

    def test_rejects_truncated_mesh_and_out_of_bounds_batch(self):
        with self.assertRaises(P.ProtocolError):
            P.mesh_payload(2,struct.pack('<iiiI',0,0,0,3)+bytes(32))
        payload = struct.pack('<II4I',1,3,0,3,3,0)+bytes(96)
        with self.assertRaises(P.ProtocolError):
            P.mesh_payload(5,payload)

    def test_section_and_scene_origins(self):
        origin,batches,verts = P.mesh_payload(2,struct.pack('<iiiI',-2,4,6,3)+bytes(96))
        self.assertEqual(origin,(-32,64,96))
        payload = struct.pack('<dddII4I',1,2,3,1,3,4,0,3,1)+bytes(96)
        origin,batches,verts = P.mesh_payload(6,payload)
        self.assertEqual(origin,(1,2,3))
        self.assertEqual(batches,[(4,0,3,1)])


@unittest.skipUnless(os.name == 'nt','Windows shared memory')
class TransportTests(unittest.TestCase):
    def setUp(self):
        self.name = 'Local\\MCInBlender_test_'+uuid.uuid4().hex
        self.link = HostLink(self.name)

    def tearDown(self):
        self.link.close()

    def test_exclusive_host_ownership(self):
        with self.assertRaises(RuntimeError):
            HostLink(self.name)

    def test_host_is_offline_until_initial_state_is_ready(self):
        self.assertEqual(self.link.atomic_load64(0x10),0)
        self.link.state(position=(2,75,3),teleport=9)
        self.link.heartbeat()
        self.assertGreater(self.link.atomic_load64(0x10),0)
        raw = self.link.snapshot(P.SKY,0x40)
        self.assertEqual(struct.unpack_from('<ddd',raw,0x10),(2,75,3))
        self.assertEqual(struct.unpack_from('<I',raw,0x30)[0],9)

    def test_input_backpressure_preserves_unread_events(self):
        self.link.input(1,26,1)
        self.assertEqual(struct.unpack_from('<HHiii',self.link.m,P.INPUT+0x80),(1,26,1,0,0))
        self.link.store64(P.INPUT,4096)
        before = self.link.m[P.INPUT+0x80:P.INPUT+0x90]
        with self.assertRaises(BufferError):
            self.link.input(1,4,1)
        self.assertEqual(before,self.link.m[P.INPUT+0x80:P.INPUT+0x90])

    def test_render_ring_wrap_and_malformed_record(self):
        size = P.RENDER_BYTES-0x80
        self.link.store64(P.RENDER+0x40,size-16)
        struct.pack_into('<II',self.link.m,P.RENDER+0x80+size-16,0,0)
        struct.pack_into('<II4s',self.link.m,P.RENDER+0x80,3,4,b'abcd')
        self.link.store64(P.RENDER,size+16)
        self.assertEqual(list(self.link.render_messages()),[(3,b'abcd')])
        self.assertEqual(self.link.atomic_load64(P.RENDER+0x40),size+16)
        struct.pack_into('<II',self.link.m,P.RENDER+0x80+16,2,size)
        self.link.store64(P.RENDER,size+32)
        with self.assertRaises(P.ProtocolError):
            list(self.link.render_messages())

    def test_collision_backpressure_and_wrap(self):
        size = P.COLLISION_BYTES-0x80
        self.link.store64(P.COLLISION,size-8)
        self.link.store64(P.COLLISION+0x40,size-8)
        self.assertTrue(self.link.send_collision(1,struct.pack('<I',42)))
        self.assertEqual(struct.unpack_from('<II',self.link.m,P.COLLISION+0x80+size-8),(0,0))
        self.assertEqual(struct.unpack_from('<III',self.link.m,P.COLLISION+0x80),(1,4,42))
        self.link.store64(P.COLLISION+0x40,16)
        self.assertFalse(self.link.send_collision(1,b'1234'))

    def test_overlay_ownership_exchange(self):
        for back,value in [(1,23),(0,54),(2,89)]:
            at = P.OVERLAY_HEADERS+back*0x40
            struct.pack_into('<III',self.link.m,at,2,2,1)
            struct.pack_into('<Q',self.link.m,at+0x10,value)
            start = P.PIXELS+back*P.SLOT_BYTES
            self.link.m[start:start+16] = bytes([value])*16
            self.link.atomic.mc_exchange32(self.link.address+P.OVERLAY,back|4)
            overlay = self.link.overlay()
            self.assertEqual(overlay,(2,2,1,value,bytes([value])*16))
            self.assertIsNone(self.link.overlay())


if __name__ == '__main__':
    unittest.main()
