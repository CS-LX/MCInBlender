import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('release_metadata', Path(__file__).resolve().parents[1]/'scripts/release_metadata.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)
SHA = '0123456789abcdef0123456789abcdef01234567'


class ReleaseMetadataTests(unittest.TestCase):
    def test_main_commit_is_unique_prerelease(self):
        info = release.metadata('1.2.3.4', SHA)
        self.assertEqual(info['tag'], 'ci-v1.2.3.4+g01234567')
        self.assertIn('-ci-', info['stem'])
        self.assertEqual(info['mod_version'], '1.2.3+rev.4.g01234567')

    def test_four_part_matching_tag_is_stable(self):
        info = release.metadata('1.2.3.4', SHA, 'refs/tags/v1.2.3.4')
        self.assertEqual(info['channel'], 'release')
        self.assertIn('-release-v1.2.3.4-', info['stem'])
        self.assertEqual(info['mod_version'], '1.2.3+rev.4')

    def test_invalid_or_mismatched_tag_cannot_publish(self):
        for ref in ('refs/tags/v1.2.3', 'refs/tags/v1.2.3.5', 'refs/tags/v1.2.3.4-alpha',
                    'refs/heads/feature/example', 'refs/pull/1/merge'):
            with self.subTest(ref=ref), self.assertRaises(ValueError):
                release.metadata('1.2.3.4', SHA, ref)

    def test_version_and_sha_cannot_inject_paths(self):
        for version in ('1.2.3', '01.2.3.4', '../1.2.3.4', '1.2.3.4\n'):
            with self.subTest(version=version), self.assertRaises(ValueError):
                release.metadata(version, SHA)
        with self.assertRaises(ValueError):
            release.metadata('1.2.3.4', '../bad')
