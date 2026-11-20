"""Read-only registry regression for the exact shipped promotion assembly command.

Usage: python3 .github/scripts/check_image_assembly.py SHA AMD64_DIGEST ARM64_DIGEST
Uses existing Docker credentials if required; never logs in or writes tags.
"""
import json
import re
import subprocess
import sys
from image_policy import verify_index
from promote_image import assembly_command


def check(sha, amd64_digest, arm64_digest):
    expected = {'amd64': amd64_digest, 'arm64': arm64_digest}
    if not re.fullmatch('[0-9a-f]{40}', sha) or any(
            not re.fullmatch('sha256:[0-9a-f]{64}', digest) for digest in expected.values()):
        raise ValueError('expected exact source SHA and two registry digests')
    args = assembly_command(sha, expected)
    # The production arguments are unchanged except for the mandatory dry-run.
    dry_run = (*args[:4], '--dry-run', *args[4:])
    result = subprocess.run(dry_run, capture_output=True, text=True)
    if result.returncode:
        sys.stderr.write(result.stderr)
        raise SystemExit(result.returncode)
    verify_index(json.loads(result.stdout), expected)
    sys.stdout.write(result.stdout)


if __name__ == '__main__':
    check(*sys.argv[1:])
