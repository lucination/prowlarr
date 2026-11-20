"""Exercise the actual native image, isolated from all external networks/state."""
import json
import re
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET


def run(*args, **kwargs):
    return subprocess.check_output(args, text=True, **kwargs).strip()


def smoke(image, revision, arch):
    info = json.loads(run('docker', 'image', 'inspect', image))[0]
    assert info['Architecture'] == arch, info['Architecture']
    assert info['Config']['User'] == '9696:9696'
    labels = info['Config']['Labels']
    assert labels['org.opencontainers.image.revision'] == revision
    assert labels['org.opencontainers.image.source'] == 'https://github.com/lucination/prowlarr'
    name = 'prowlarr-smoke-' + uuid.uuid4().hex[:12]
    volume = name + '-config'
    run('docker', 'volume', 'create', volume)
    try:
        run('docker', 'run', '-d', '--name', name, '--network', 'none', '--cpus', '2', '--memory', '1536m',
            '-v', volume + ':/config', image)

        def request(path, key=None, data=None, status=False):
            args = ['docker', 'exec', name, 'curl', '--disable', '--noproxy', '*', '--max-time', '5', '-sS']
            if status:
                args += ['-o', '/dev/null', '-w', '%{http_code}']
            else:
                args += ['--fail']
            if key:
                args += ['-H', 'X-Api-Key: ' + key]
            if data is not None:
                args += ['-X', 'PUT', '-H', 'Content-Type: application/json', '--data-binary', json.dumps(data)]
            return run(*args, 'http://127.0.0.1:9696' + path)

        def ready():
            for _ in range(120):
                state = json.loads(run('docker', 'inspect', name))[0]['State']
                if state.get('Health', {}).get('Status') == 'healthy':
                    return
                if not state['Running']:
                    raise AssertionError('application exited')
                time.sleep(2)
            raise AssertionError('image did not become healthy')

        ready()
        xml = run('docker', 'exec', name, 'cat', '/config/config.xml')
        key = ET.fromstring(xml).findtext('ApiKey')
        assert key and len(key) == 32
        assert request('/api/v1/system/status', status=True) == '401', 'API must require authentication'
        status = json.loads(request('/api/v1/system/status', key))
        assert status['appData'] == '/config', status
        assert status['packageUpdateMechanism'].lower() == 'docker', status
        package = dict(line.split('=', 1) for line in run('docker', 'exec', name, 'cat', '/app/package_info').splitlines())
        assert status['version'] == package['PackageVersion'], status
        # Bootstrap page must include and serve the real compiled frontend.
        html = request('/login')
        assets = re.findall(r'(?:src|href)="([^"]+\.(?:js|css)(?:\?[^\"]*)?)"', html)
        assert assets, 'no frontend assets in page'
        for asset in assets:
            assert len(request('/' + asset.lstrip('/'))) > 100, asset
        host = json.loads(request('/api/v1/config/host', key))
        host['instanceName'] = name
        request('/api/v1/config/host', key, host)
        assert json.loads(request('/api/v1/config/host', key))['instanceName'] == name
        ui = json.loads(request('/api/v1/config/ui', key))
        ui['showRelativeDates'] = not ui['showRelativeDates']
        request('/api/v1/config/ui', key, ui)
        run('docker', 'restart', '--time', '30', name)
        ready()
        assert ET.fromstring(run('docker', 'exec', name, 'cat', '/config/config.xml')).findtext('ApiKey') == key
        assert json.loads(request('/api/v1/config/host', key))['instanceName'] == name
        assert json.loads(request('/api/v1/config/ui', key))['showRelativeDates'] == ui['showRelativeDates']
        assert run('docker', 'exec', name, 'sqlite3', '/config/prowlarr.db', 'PRAGMA integrity_check;') == 'ok'
        assert run('docker', 'exec', name, 'id', '-u') == '9696'
        print(json.dumps({'image': image, 'image_id': info['Id'], 'revision': revision, 'architecture': arch,
                          'ui_assets': len(assets), 'authenticated_api': True, 'restart_persistence': True,
                          'sqlite_integrity': 'ok', 'updater': 'docker'}))
    except BaseException:
        subprocess.run(['docker', 'logs', '--tail', '100', name], check=False)
        raise
    finally:
        subprocess.run(['docker', 'rm', '-f', name], check=False, stdout=subprocess.DEVNULL)
        subprocess.run(['docker', 'volume', 'rm', volume], check=False, stdout=subprocess.DEVNULL)


if __name__ == '__main__':
    smoke(*sys.argv[1:])
