"""Exercise the real synchronization executable against local bare repositories."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("upstream_sync.py")


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = dict(os.environ, GIT_AUTHOR_NAME="Sync Test", GIT_AUTHOR_EMAIL="test@example.invalid",
                        GIT_COMMITTER_NAME="Sync Test", GIT_COMMITTER_EMAIL="test@example.invalid")
        self.upstream = self.root / "upstream.git"
        self.origin = self.root / "origin.git"
        self.seed = self.root / "seed"
        self.repo = self.root / "mirror"
        self.git(self.root, "init", "--bare", "--initial-branch=master", str(self.upstream))
        self.git(self.root, "clone", str(self.upstream), str(self.seed))
        self.commit(self.seed, "upstream.txt", "base\n")
        self.git(self.seed, "push", "origin", "HEAD:master")
        self.git(self.root, "clone", "--bare", str(self.upstream), str(self.origin))
        self.git(self.origin, "branch", "main", "master")
        self.git(self.origin, "symbolic-ref", "HEAD", "refs/heads/main")
        self.git(self.root, "clone", str(self.origin), str(self.repo))
        self.commit(self.repo, "custom.txt", "customization\n")
        self.git(self.repo, "push", "origin", "main")
        self.before = self.tip()

    def git(self, cwd, *args):
        return subprocess.check_output(["git", *args], cwd=cwd, env=self.env, text=True, stderr=subprocess.STDOUT).strip()

    def commit(self, repo, name, content):
        (repo / name).write_text(content)
        self.git(repo, "add", name)
        self.git(repo, "commit", "-m", "Update " + name)

    def tip(self):
        return self.git(self.origin, "rev-parse", "refs/heads/main")

    def update(self, name="upstream.txt", content="new upstream\n"):
        self.commit(self.seed, name, content)
        self.git(self.seed, "push", "origin", "HEAD:master")

    def sync(self, validation="true"):
        return subprocess.run([sys.executable, str(SCRIPT), "--upstream", str(self.upstream),
                               "--validate", "bash", "-c", validation], cwd=self.repo,
                              env=self.env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    def test_unchanged_does_not_publish(self):
        result = self.sync("exit 99")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.tip(), self.before)
        self.assertIn("already current", result.stdout)

    def test_update_validates_candidate_and_preserves_customization(self):
        self.update()
        result = self.sync("test \"$(cat custom.txt)\" = customization && test \"$(cat upstream.txt)\" = 'new upstream'")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotEqual(self.tip(), self.before)
        self.assertEqual(self.git(self.origin, "show", "main:custom.txt"), "customization")
        self.git(self.origin, "merge-base", "--is-ancestor", self.before, "main")
        upstream_tip = self.git(self.upstream, "rev-parse", "master")
        self.git(self.origin, "merge-base", "--is-ancestor", upstream_tip, "main")

    def test_failing_validation_does_not_publish(self):
        self.update()
        result = self.sync("exit 42")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.tip(), self.before)

    def test_conflict_does_not_publish(self):
        self.commit(self.repo, "upstream.txt", "private conflicting change\n")
        self.git(self.repo, "push", "origin", "main")
        before = self.tip()
        self.update()
        result = self.sync()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.tip(), before)

    def test_stale_main_is_rejected(self):
        self.update()
        # Simulate a developer publishing while candidate validation is running.
        validation = "git -C '{}' commit --allow-empty -m concurrent && git -C '{}' push origin main".format(self.repo, self.repo)
        result = self.sync(validation)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("main moved", result.stdout)
        self.assertEqual(self.tip(), self.git(self.repo, "rev-parse", "HEAD"))
        self.assertEqual(self.git(self.origin, "show", "main:upstream.txt"), "base")

    def test_changed_candidate_is_not_published(self):
        self.update()
        result = self.sync("echo untested >> custom.txt")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.tip(), self.before)

    def test_stale_ancestor_tip_is_also_rejected(self):
        self.update()
        ancestor = self.git(self.repo, "rev-parse", "HEAD^")
        result = self.sync("git --git-dir='{}' update-ref refs/heads/main {} {}".format(self.origin, ancestor, self.before))
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.tip(), ancestor)

    def test_tip_race_after_preflight_is_rejected(self):
        self.update()
        ancestor = self.git(self.repo, "rev-parse", "HEAD^")
        receiver = self.root / "concurrent-receive-pack"
        receiver.write_text("#!/bin/sh\ngit --git-dir='{}' update-ref refs/heads/main {} {}\nexec git-receive-pack \"$@\"\n".format(self.origin, ancestor, self.before))
        receiver.chmod(0o700)
        self.git(self.repo, "config", "remote.origin.receivepack", str(receiver))

        result = self.sync()

        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("main moved", result.stdout)
        self.assertEqual(self.tip(), ancestor)


if __name__ == "__main__":
    unittest.main()
