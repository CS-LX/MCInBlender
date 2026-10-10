"""Native mapping regression: never pass freed pointers back to mc_atomic."""
import mmap
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blender_minecraft import protocol as P
from blender_minecraft.transport import HostLink


@unittest.skipUnless(os.name == 'nt', 'Windows shared memory')
class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.name = 'Local\\MCInBlender_lifecycle_' + uuid.uuid4().hex

    def test_closed_reads_never_reach_native_dll_and_can_restart(self):
        link = HostLink(self.name)
        link.close()
        link.close()
        self.assertTrue(link.closed)
        self.assertFalse(link.alive)
        self.assertEqual(link.address, 0)
        self.assertIsNone(link.m)
        for operation in (lambda: link.atomic_load64(0x18), link.heartbeat,
                          link.state, link.overlay, lambda: link.snapshot(P.MC, 8),
                          lambda: link.input(6), lambda: list(link.render_messages())):
            with self.assertRaisesRegex(RuntimeError, 'closed'):
                operation()
        replacement = HostLink(self.name)
        replacement.close()

    def test_mapping_failure_releases_owner_mutex(self):
        with patch('blender_minecraft.transport.mmap.mmap', side_effect=OSError('mapping failed')):
            with self.assertRaisesRegex(OSError, 'mapping failed'):
                HostLink(self.name)
        replacement = HostLink(self.name)
        replacement.close()

    def test_close_failure_still_releases_mapping_and_mutex(self):
        link = HostLink(self.name)
        with patch.object(link, 'input', side_effect=RuntimeError('queue failed')):
            with self.assertRaisesRegex(RuntimeError, 'queue failed'):
                link.close()
        self.assertFalse(link.alive)
        self.assertEqual(link.address, 0)
        replacement = HostLink(self.name)
        replacement.close()

    def test_generation_changes_while_client_holds_same_mapping(self):
        old = HostLink(self.name)
        client = mmap.mmap(-1, P.SIZE, tagname=self.name)
        generation = old.generation
        try:
            old.close()
            replacement = HostLink(self.name)
            try:
                self.assertNotEqual(replacement.generation, generation)
                replacement.store64(0x18, replacement.k32.GetTickCount64())
                replacement.store64(P.CLIENT_GENERATION, generation)
                self.assertFalse(replacement.alive)
                replacement.store64(P.CLIENT_GENERATION, replacement.generation)
                self.assertTrue(replacement.alive)
            finally:
                replacement.close()
        finally:
            old.close()
            client.close()


if __name__ == '__main__':
    unittest.main()
