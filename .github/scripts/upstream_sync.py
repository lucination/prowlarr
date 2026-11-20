"""Validate upstream in an isolated candidate before a non-forced main update."""

import argparse
from pathlib import Path
import subprocess
import tempfile


def git(*args, cwd=None):
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", default="https://github.com/Prowlarr/Prowlarr.git")
    parser.add_argument("--validate", nargs=argparse.REMAINDER, required=True)
    args = parser.parse_args()
    if not args.validate:
        parser.error("a validation command is required")
    if git("status", "--porcelain"):
        raise RuntimeError("synchronization requires a clean checkout")
    git("fetch", "--no-tags", "origin", "+refs/heads/main:refs/remotes/origin/main")
    git("fetch", "--no-tags", args.upstream, "+refs/heads/master:refs/remotes/sync-upstream/master")
    expected = git("rev-parse", "refs/remotes/origin/main")
    if git("rev-parse", "HEAD") != expected:
        raise RuntimeError("main moved since checkout; retry from current main")
    upstream = git("rev-parse", "refs/remotes/sync-upstream/master")
    if subprocess.run(["git", "merge-base", "--is-ancestor", upstream, expected]).returncode == 0:
        print("upstream master already current")
        return
    with tempfile.TemporaryDirectory(prefix="prowlarr-sync-") as directory:
        candidate = Path(directory) / "candidate"
        git("worktree", "add", "--detach", str(candidate), expected)
        try:
            git("merge", "--no-ff", "--no-edit", upstream, cwd=candidate)
            published = git("rev-parse", "HEAD", cwd=candidate)
            subprocess.run(args.validate, cwd=candidate, check=True)
            if git("rev-parse", "HEAD", cwd=candidate) != published or git("status", "--porcelain", cwd=candidate):
                raise RuntimeError("validation changed the candidate; refusing untested publication")
            if git("ls-remote", "--exit-code", "origin", "refs/heads/main").split()[0] != expected:
                raise RuntimeError("main moved during validation; retry from current main")
            # Verify the push advertisement too: a fetch/preflight alone races.
            # receive-pack atomically compares this advertised old object ID.
            # Together these checks provide CAS without ever forcing main.
            hooks = Path(directory) / "hooks"
            hooks.mkdir()
            guard = hooks / "pre-push"
            guard.write_text(
                "#!/bin/sh\n"
                "while read local_ref local_oid remote_ref remote_oid; do\n"
                f"  if [ \"$remote_ref\" != refs/heads/main ] || [ \"$remote_oid\" != {expected} ]; then\n"
                "    echo 'main moved during validation; refusing stale publication' >&2\n"
                "    exit 1\n"
                "  fi\n"
                "done\n"
            )
            guard.chmod(0o700)
            git("merge-base", "--is-ancestor", expected, published)
            git("-c", "core.hooksPath=" + str(hooks), "push", "origin", published + ":refs/heads/main")
            remote_tip = git("ls-remote", "--exit-code", "origin", "refs/heads/main").split()[0]
            if remote_tip != published:
                raise RuntimeError("published main tip could not be verified")
            print("published validated upstream candidate " + published)
        finally:
            git("worktree", "remove", "--force", str(candidate))


if __name__ == "__main__":
    main()
