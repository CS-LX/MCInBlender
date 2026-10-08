import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    'control_inbox', Path(__file__).resolve().parents[1]/'blender_minecraft/control_inbox.py')
control_inbox = importlib.util.module_from_spec(spec)
spec.loader.exec_module(control_inbox)


class ControlInboxTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.inbox = Path(self.directory.name)
        self.events = []
        for name in ('01-press', '02-release'):
            (self.inbox/(name+'.json')).write_text(json.dumps(name), encoding='utf8')

    def drain(self):
        control_inbox.drain(self.inbox, self.events.append)

    def test_read_lock_preserves_input_order(self):
        original = Path.read_text

        def locked(path, *args, **kwargs):
            if path.name == '01-press.json':
                raise PermissionError('temporary sharing violation')
            return original(path, *args, **kwargs)

        with patch.object(Path, 'read_text', locked):
            self.drain()
        self.assertEqual(self.events, [])
        self.drain()
        self.assertEqual(self.events, ['01-press', '02-release'])

    def test_claim_lock_defers_dispatch(self):
        with patch.object(Path, 'rename', side_effect=PermissionError('sharing violation')):
            self.drain()
        self.assertEqual(self.events, [])
        self.drain()
        self.assertEqual(self.events, ['01-press', '02-release'])

    def test_cleanup_lock_does_not_repeat_actions(self):
        with patch.object(Path, 'unlink', side_effect=PermissionError('sharing violation')):
            self.drain()
        self.assertEqual(len(list(self.inbox.glob('*.claimed'))), 2)
        self.drain()
        self.assertEqual(self.events, ['01-press', '02-release'])
        self.assertEqual(list(self.inbox.iterdir()), [])

    def test_malformed_json_raises_once_then_queue_continues(self):
        (self.inbox/'01-press.json').write_text('{', encoding='utf8')
        with self.assertRaises(json.JSONDecodeError):
            self.drain()
        self.drain()
        self.assertEqual(self.events, ['02-release'])

    def test_failed_dispatch_is_not_repeated(self):
        def fail(data):
            self.events.append(data)
            raise ValueError('unsupported action')

        with self.assertRaisesRegex(ValueError, 'unsupported action'):
            control_inbox.drain(self.inbox, fail)
        self.drain()
        self.assertEqual(self.events, ['01-press', '02-release'])


if __name__ == '__main__':
    unittest.main()
