"""Publication adapter fixtures: observations are synthetic, never registry proof."""
import contextlib
import io
import json
import os
import unittest
from unittest.mock import patch
from subprocess import CompletedProcess
import promote_image as release
import check_image_assembly as preview

SHA = 'a' * 40
DIGESTS = {'amd64': 'sha256:' + '1' * 64, 'arm64': 'sha256:' + '2' * 64}
INDEX = {'manifests': [{'digest': digest, 'platform': {'os': 'linux', 'architecture': arch}}
                       for arch, digest in DIGESTS.items()]}
ENV = {'CANDIDATE_SHA': SHA, 'AMD64_DIGEST': DIGESTS['amd64'], 'ARM64_DIGEST': DIGESTS['arm64']}


class PromotionTests(unittest.TestCase):
    def exercise(self, existing, current=SHA, effects=None):
        effects = [] if effects is None else effects

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

    def test_exact_buildx_missing_target_can_create_first_publication(self):
        error = f'ERROR: {release.IMAGE}:sha-{SHA}: not found\n'
        calls = self.exercise(CompletedProcess([], 1, '', error))
        creates = [call for call in calls if 'create' in call]
        self.assertEqual(len(creates), 2)
        self.assertIn(release.IMAGE + ':sha-' + SHA, creates[0])

    def test_docker_manifest_assembly_uses_shared_command_without_annotations(self):
        calls = self.exercise(CompletedProcess([], 1, '', 'manifest unknown'))
        creates = [call for call in calls if 'create' in call]
        self.assertEqual(creates[0], release.assembly_command(SHA, DIGESTS))
        self.assertNotIn('--annotation', creates[0], 'Docker manifest lists cannot carry index annotations')

    def test_registry_probe_adds_only_dry_run_to_shipped_assembly_command(self):
        result = CompletedProcess([], 0, json.dumps(INDEX), '')
        with patch.object(preview.subprocess, 'run', return_value=result) as invoke, \
                contextlib.redirect_stdout(io.StringIO()):
            preview.check(SHA, DIGESTS['amd64'], DIGESTS['arm64'])
        shipped = release.assembly_command(SHA, DIGESTS)
        self.assertEqual(invoke.call_args.args[0], (*shipped[:4], '--dry-run', *shipped[4:]))

    def test_immutable_conflict_never_writes(self):
        bad = {'manifests': INDEX['manifests'][:1]}
        effects = []
        with self.assertRaises(ValueError):
            self.exercise(CompletedProcess([], 0, json.dumps(bad), ''), effects=effects)
        self.assertEqual(effects, [])

    def test_ambiguous_lookup_does_not_publish(self):
        for error in ['unauthorized', 'network timeout', 'denied: permission denied',
                      'lookup ghcr.io: host not found', 'denied: package not found']:
            effects = []
            with self.subTest(error=error), self.assertRaises(RuntimeError):
                self.exercise(CompletedProcess([], 1, '', error), effects=effects)
            self.assertEqual(effects, [])


if __name__ == '__main__':
    unittest.main()
