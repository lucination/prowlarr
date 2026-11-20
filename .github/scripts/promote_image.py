"""Publish only two native-smoked digests, never overwrite an immutable SHA tag."""
import json
import os
import re
import subprocess
from image_policy import latest_allowed, verify_index

IMAGE = 'ghcr.io/lucination/prowlarr'


def command(*args):
    return subprocess.check_output(args, text=True).strip()


def inspect(ref):
    return json.loads(command('docker', 'buildx', 'imagetools', 'inspect', ref, '--raw'))


def main():
    sha = os.environ['CANDIDATE_SHA']
    if not re.fullmatch('[0-9a-f]{40}', sha):
        raise ValueError('invalid source revision')
    expected = {arch: os.environ[arch.upper() + '_DIGEST'] for arch in ('amd64', 'arm64')}
    if any(not re.fullmatch('sha256:[0-9a-f]{64}', digest) for digest in expected.values()):
        raise ValueError('invalid native digest')
    immutable = f'{IMAGE}:sha-{sha}'
    # Distinguish a registry 404 from auth/network errors. Never create/overwrite on
    # an ambiguous inspect failure. Match only explicit manifest-unknown or the
    # CLI's exact missing-target diagnostic, never a DNS/auth "not found" substring.
    existing = subprocess.run(['docker', 'buildx', 'imagetools', 'inspect', immutable, '--raw'],
                              capture_output=True, text=True)
    if existing.returncode == 0:
        verify_index(json.loads(existing.stdout), expected)
    elif existing.stderr.strip() in {
            'manifest unknown', f'ERROR: {immutable}: manifest unknown',
            f'{immutable}: manifest unknown', f'ERROR: {immutable}: not found',
            f'{immutable}: not found'}:
        command('docker', 'buildx', 'imagetools', 'create', '--annotation',
                'index:org.opencontainers.image.source=https://github.com/lucination/prowlarr',
                '--annotation', f'index:org.opencontainers.image.revision={sha}',
                '-t', immutable, *(f'{IMAGE}@{digest}' for digest in expected.values()))
        verify_index(inspect(immutable), expected)
    else:
        raise RuntimeError('immutable tag lookup failed; refusing publication')
    current = command('gh', 'api', 'repos/lucination/prowlarr/git/ref/heads/main', '--jq', '.object.sha')
    if not latest_allowed(sha, current):
        print('Immutable image verified; current main advanced, latest withheld.')
        return
    command('docker', 'buildx', 'imagetools', 'create', '-t', IMAGE + ':latest', immutable)
    verify_index(inspect(IMAGE + ':latest'), expected)
    print(f'Published and read back {immutable} and latest for {sha}')


if __name__ == '__main__':
    main()
