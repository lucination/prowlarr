"""Publication adapter fixtures: observations are synthetic, never registry proof."""
import contextlib
import io
import json
import os
import unittest
from unittest.mock import patch
from subprocess import CompletedProcess
import promote_image as release

SHA = 'a' * 40
DIGESTS = {'amd64': 'sha256:' + '1' * 64, 'arm64': 'sha256:' + '2' * 64}
INDEX = {'manifests': [{'digest': digest, 'platform': {'os': 'linux', 'architecture': arch}}
                       for arch, digest in DIGESTS.items()]}
ENV = {'CANDIDATE_SHA': SHA, 'AMD64_DIGEST': DIGESTS['amd64'], 'ARM64_DIGEST': DIGESTS['arm64']}


class PromotionTests(unittest.TestCase):
    def exercise(self, existing, current=SHA):
        effects = []

        def command(*args):
            effects.append(args)
            if args[0] == 'gh':
                return current
            if '--raw' in args:
                return json.dumps(INDEX)
            return ''

        with patch.dict(os.environ, ENV), patch.object(release.subprocess, 'run', return_value=existing), \
                patch.object(release, 'command', side_effect=command), contextlib.redirect_stdout(io.StringIO()):
            release.main()
        return effects

    def test_late_success_publishes_immutable_but_not_latest(self):
        calls = self.exercise(CompletedProcess([], 1, '', 'manifest unknown'), 'b' * 40)
        creates = [call for call in calls if 'create' in call]
        self.assertEqual(len(creates), 1)
        self.assertIn(release.IMAGE + ':sha-' + SHA, creates[0])
        self.assertTrue(any(call[0] == 'gh' for call in calls))

    def test_existing_immutable_is_reused_without_overwrite(self):
        calls = self.exercise(CompletedProcess([], 0, json.dumps(INDEX), ''))
        creates = [call for call in calls if 'create' in call]
        self.assertEqual(len(creates), 1)
        self.assertIn(release.IMAGE + ':latest', creates[0])
        self.assertEqual(calls[0][0], 'gh', 'current-main fence must precede latest write')
        self.assertIn('--raw', calls[-1], 'exact written target must be read back')

    def test_immutable_conflict_never_writes(self):
        bad = {'manifests': INDEX['manifests'][:1]}
        with self.assertRaises(ValueError):
            self.exercise(CompletedProcess([], 0, json.dumps(bad), ''))

    def test_ambiguous_lookup_does_not_publish(self):
        for error in ['unauthorized', 'network timeout', 'denied: permission denied']:
            with self.subTest(error=error), self.assertRaises(RuntimeError):
                self.exercise(CompletedProcess([], 1, '', error))


if __name__ == '__main__':
    unittest.main()
