import importlib.util
from pathlib import Path
import unittest
import copy
import image_policy as policy

SHA = 'a' * 40
NEW = 'b' * 40


def event(name='Mirror CI', trigger='push'):
    return {'repository': {'full_name': 'lucination/prowlarr'}, 'workflow_run': {
        'conclusion': 'success', 'head_branch': 'main', 'head_sha': SHA,
        'head_repository': {'full_name': 'lucination/prowlarr'}, 'pull_requests': [],
        'name': name, 'event': trigger}}


class AdmissionTests(unittest.TestCase):
    def test_failed_run_never_selects_source(self):
        path = Path(__file__).with_name('image_policy.py')
        self.assertTrue(path.exists(), 'publication must have executable admission policy')
        spec = importlib.util.spec_from_file_location('policy', path)
        policy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(policy)
        self.assertIsNone(policy.select('workflow_run', {'repository': {'full_name': 'lucination/prowlarr'}, 'workflow_run': {'conclusion': 'failure'}}, 'a' * 40, 'refs/heads/main'))

    def test_event_provenance(self):
        self.assertEqual(policy.select('workflow_run', event(), SHA, 'refs/heads/main'), SHA)
        for key, value in [('event', 'pull_request'), ('head_branch', 'feature'),
                           ('conclusion', 'cancelled'), ('name', 'Unrelated'),
                           ('pull_requests', [{'number': 1}]),
                           ('head_repository', {'full_name': 'fork/prowlarr'})]:
            bad = event()
            bad['workflow_run'][key] = value
            with self.subTest(key=key):
                self.assertIsNone(policy.select('workflow_run', bad, SHA, 'refs/heads/main'))
        fork = event()
        fork['repository']['full_name'] = 'fork/prowlarr'
        self.assertIsNone(policy.select('workflow_run', fork, SHA, 'refs/heads/main'))

    def test_sync_resolves_postmerge_main_not_control_sha(self):
        self.assertEqual(policy.select('workflow_run', event('Sync stable upstream', 'schedule'), NEW, 'refs/heads/main'), NEW)
        self.assertIsNone(policy.select('workflow_run', event(), NEW, 'refs/heads/main'))

    def test_manual_dispatch_only_default_main(self):
        for ref in ['refs/heads/topic', 'refs/tags/main', SHA]:
            self.assertIsNone(policy.select('workflow_dispatch', event(), SHA, ref))
        self.assertEqual(policy.select('workflow_dispatch', event(), SHA, 'refs/heads/main'), SHA)

    def test_late_completion_cannot_promote_latest(self):
        self.assertTrue(hasattr(policy, 'latest_allowed'), 'latest requires a final current-main fence')
        self.assertFalse(policy.latest_allowed(SHA, NEW))
        self.assertTrue(policy.latest_allowed(SHA, SHA))

    def test_index_requires_exact_native_digests(self):
        self.assertTrue(hasattr(policy, 'verify_index'), 'index must bind both native-smoked digests')
        manifests = [{'digest': 'sha256:' + c * 64, 'platform': {'os': 'linux', 'architecture': arch}}
                     for c, arch in [('1', 'amd64'), ('2', 'arm64')]]
        expected = {'amd64': manifests[0]['digest'], 'arm64': manifests[1]['digest']}
        policy.verify_index({'manifests': manifests}, expected)
        for bad in [manifests[:1], manifests + [manifests[0]], list(reversed(copy.deepcopy(manifests)))]:
            if len(bad) == 2:
                bad[0]['digest'] = 'sha256:' + '3' * 64
            with self.assertRaises(ValueError):
                policy.verify_index({'manifests': bad}, expected)


if __name__ == '__main__':
    unittest.main()
