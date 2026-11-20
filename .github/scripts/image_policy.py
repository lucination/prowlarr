"""Pure release admission; event payloads never supply commands or checkout refs."""
import json
import os
import re

REPOSITORY = 'lucination/prowlarr'


def latest_allowed(candidate, current_main):
    return bool(re.fullmatch('[0-9a-f]{40}', candidate)) and candidate == current_main


def verify_index(index, expected):
    manifests = index.get('manifests', [])
    actual = {}
    for manifest in manifests:
        platform = manifest.get('platform', {})
        arch = platform.get('architecture')
        if platform.get('os') != 'linux' or arch in actual:
            raise ValueError('unexpected or duplicate platform')
        actual[arch] = manifest.get('digest')
    if set(expected) != {'amd64', 'arm64'} or actual != expected:
        raise ValueError('index differs from native-smoked digests')


def select(event_name, event, main_sha, ref):
    if not re.fullmatch('[0-9a-f]{40}', main_sha):
        raise ValueError('invalid main SHA')
    if event.get('repository', {}).get('full_name') != REPOSITORY:
        return None
    if event_name == 'workflow_dispatch':
        return main_sha if ref == 'refs/heads/main' else None
    run = event.get('workflow_run', {})
    if (event_name != 'workflow_run' or run.get('conclusion') != 'success'
            or run.get('head_branch') != 'main'
            or run.get('head_repository', {}).get('full_name') != REPOSITORY
            or run.get('pull_requests') != []):
        return None
    if run.get('name') == 'Mirror CI' and run.get('event') in ('push', 'workflow_dispatch'):
        return main_sha if run.get('head_sha') == main_sha else None
    if run.get('name') == 'Sync stable upstream' and run.get('event') in ('schedule', 'workflow_dispatch'):
        # Sync's workflow head is the control commit, NOT the validated merge.
        # Resolve current main and revalidate that exact immutable object.
        # No-op syncs must not rebuild an already-published immutable SHA daily.
        return main_sha if run.get('head_sha') != main_sha else None
    return None


if __name__ == '__main__':
    with open(os.environ['GITHUB_EVENT_PATH']) as source:
        event = json.load(source)
    sha = select(os.environ['GITHUB_EVENT_NAME'], event, os.environ['MAIN_SHA'], os.environ['GITHUB_REF'])
    with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
        output.write(f'sha={sha or ""}\n')
