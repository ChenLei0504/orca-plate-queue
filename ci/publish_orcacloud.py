"""Publish the public release's queue wheel using GitHub OIDC; never execute it.

No third-party dependencies. Run locally with --check-wheel PATH --tag vX.Y.Z
to validate an artifact without any network access or publishing credentials.
"""
import argparse
import base64
import csv
from email.parser import BytesParser
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile

REPOSITORY = 'ChenLei0504/orca-plate-queue'
WHEEL_NAME = 'Orca_Plate_Queue_win_x86_64.whl'
PUBLISH_URL = 'https://api.orcaslicer.com/api/v1/plugin-publish/releases'
MAX_BYTES = 100 * 1024 * 1024


class PublishError(Exception):
    pass


def version_from_tag(tag):
    if not isinstance(tag, str) or not re.fullmatch(r'v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', tag):
        raise PublishError('Use a release tag such as v0.7.4 (X.Y.Z).')
    return tag.removeprefix('v')


def validate_wheel(data, version):
    """Inspect archive metadata and hashes in memory; do not extract/import."""
    if not data or len(data) > MAX_BYTES:
        raise PublishError('Wheel is empty or exceeds 100 MiB.')
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            names = [i.filename for i in infos]
            if len(names) > 1000 or len(names) != len(set(names)):
                raise PublishError('Wheel contains duplicate or excessive entries.')
            if sum(i.file_size for i in infos) > MAX_BYTES:
                raise PublishError('Uncompressed wheel exceeds 100 MiB.')
            dist = f'orca_plate_queue-{version}.dist-info/'
            for entry in infos:
                name = entry.filename
                parts = PurePosixPath(name).parts
                if (not parts or name.startswith('/') or '\\' in name or ':' in name
                        or '..' in parts or stat.S_ISLNK(entry.external_attr >> 16)
                        or entry.is_dir() or entry.flag_bits & 1):
                    raise PublishError('Wheel contains an unsupported archive entry.')
                if not (name.startswith('orca_plate_queue/') or name.startswith(dist)):
                    raise PublishError('Wheel contains an unexpected top-level package/version.')
                if name.lower().endswith(('.dll', '.exe', '.ps1', '.zip', '.3mf', '.sqlite3', '.pem', '.key', '.pfx')):
                    raise PublishError('Only the split queue wheel may be published, without connection binaries or private data.')
                if any(part.startswith(('test_', 'build_', 'connection_components')) for part in parts):
                    raise PublishError('Development/installation scripts must not be in the runtime wheel.')
            metadata = BytesParser().parsebytes(archive.read(dist + 'METADATA'))
            if metadata.get_all('Name') != ['orca-plate-queue'] or metadata.get_all('Version') != [version]:
                raise PublishError('Wheel metadata must match this plugin and the release tag.')
            for required in ('__init__.py', 'core.py', 'queue_engine.py', 'permissions.json'):
                if 'orca_plate_queue/' + required not in names:
                    raise PublishError('Queue runtime is incomplete.')
            record_name = dist + 'RECORD'
            rows = list(csv.reader(io.StringIO(archive.read(record_name).decode('utf-8'))))
            if any(len(row) != 3 for row in rows) or len(rows) != len(names) or {r[0] for r in rows} != set(names):
                raise PublishError('Wheel RECORD is incomplete or has duplicate rows.')
            for name, digest, size in rows:
                if name == record_name:
                    if digest or size:
                        raise PublishError('RECORD must have an empty self hash/size.')
                    continue
                content = archive.read(name)
                expected = 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b'=').decode('ascii')
                if digest != expected or size != str(len(content)):
                    raise PublishError('Wheel RECORD integrity check failed.')
    except (zipfile.BadZipFile, KeyError, UnicodeError, ValueError, RuntimeError, NotImplementedError) as exc:
        raise PublishError('Invalid queue wheel archive/metadata.') from exc


def fetch(request, limit):
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = response.read(limit + 1)
            if len(data) > limit:
                raise PublishError('HTTP response exceeds the expected size limit.')
            return response.status, data
    except urllib.error.HTTPError as exc:
        # Do not print response bodies or request URLs: credentials must stay private.
        hints = {401: 'Check the repository connection in Orca Cloud.',
                 403: 'Check GitHub Actions/OIDC permissions.',
                 404: 'Check that the published release contains the named wheel.',
                 400: 'Check release version and package metadata.',
                 409: 'Check that the version is greater than the current Cloud version.',
                 422: 'Check release version and package metadata.'}
        raise PublishError(f'HTTP {exc.code}. ' + hints.get(exc.code, 'Check service status; review the Cloud plugin version before retrying.')) from None
    except (urllib.error.URLError, TimeoutError):
        raise PublishError('Network request failed; check the Cloud plugin version before retrying a publish.') from None


def publish(event, env):
    if env.get('GITHUB_EVENT_NAME') != 'release' or event.get('action') != 'published':
        raise PublishError('Publishing requires a GitHub release.published event.')
    if env.get('GITHUB_REPOSITORY') != REPOSITORY or event.get('repository', {}).get('full_name') != REPOSITORY:
        raise PublishError('This workflow is configured for ' + REPOSITORY + ' only.')
    release = event.get('release', {})
    if release.get('draft') is not False:
        raise PublishError('Draft releases cannot be published.')
    tag = release.get('tag_name')
    version = version_from_tag(tag)
    if env.get('GITHUB_REF') != 'refs/tags/' + tag:
        raise PublishError('Release event and checked-out tag do not match.')
    assets = [a for a in release.get('assets', []) if a.get('name') == WHEEL_NAME]
    if len(assets) != 1:
        raise PublishError('Attach exactly one ' + WHEEL_NAME + ' BEFORE publishing the release.')
    asset = assets[0]
    if not isinstance(asset.get('size'), int) or not 0 < asset['size'] <= MAX_BYTES:
        raise PublishError('Invalid wheel attachment size.')
    url = f'https://github.com/{REPOSITORY}/releases/download/{urllib.parse.quote(tag, safe="")}/{WHEEL_NAME}'
    if asset.get('browser_download_url') != url:
        raise PublishError('Unexpected wheel attachment download URL.')
    status, data = fetch(urllib.request.Request(url, headers={'User-Agent': 'Orca-Plate-Queue-publisher'}), MAX_BYTES)
    if status != 200 or len(data) != asset['size']:
        raise PublishError('Downloaded wheel does not match the release attachment size.')
    digest = 'sha256:' + hashlib.sha256(data).hexdigest()
    if asset.get('digest') and asset['digest'] != digest:
        raise PublishError('Downloaded wheel does not match the GitHub asset digest.')
    validate_wheel(data, version)
    print(f'Validated {WHEEL_NAME}, version {version}, {digest}', flush=True)

    # Only request a short-lived publishing credential after artifact validation.
    token_url = env.get('ACTIONS_ID_TOKEN_REQUEST_URL', '')
    token_auth = env.get('ACTIONS_ID_TOKEN_REQUEST_TOKEN', '')
    if not token_url.startswith('https://') or not token_auth:
        raise PublishError('GitHub OIDC is unavailable; set id-token: write in workflow permissions.')
    separator = '&' if '?' in token_url else '?'
    status, token_data = fetch(urllib.request.Request(token_url + separator + 'audience=orcacloud',
                              headers={'Authorization': 'Bearer ' + token_auth}), 1024 * 1024)
    try:
        token = json.loads(token_data).get('value')
    except (ValueError, AttributeError):
        raise PublishError('Invalid GitHub OIDC response.') from None
    if status != 200 or not isinstance(token, str) or not token or '\r' in token or '\n' in token:
        raise PublishError('GitHub OIDC response has no valid publishing credential.')
    changelog = release.get('body') or ''
    if not isinstance(changelog, str):
        raise PublishError('Release notes must be text.')
    # Official endpoint supports up to 4000 bytes of release notes.
    changelog = changelog.encode('utf-8')[:4000].decode('utf-8', errors='ignore')
    metadata = {'version': version}
    if changelog:
        metadata['changelog'] = changelog
    boundary = 'OrcaQueue' + uuid.uuid4().hex
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="metadata"\r\n'
            'Content-Type: application/json\r\n\r\n').encode() + json.dumps(metadata, ensure_ascii=False).encode('utf-8')
    body += (f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="{WHEEL_NAME}"\r\n'
             'Content-Type: application/octet-stream\r\n\r\n').encode() + data + f'\r\n--{boundary}--\r\n'.encode()
    request = urllib.request.Request(PUBLISH_URL, data=body, method='POST', headers={
        'Authorization': 'Bearer ' + token,
        'Content-Type': 'multipart/form-data; boundary=' + boundary,
        'User-Agent': 'Orca-Plate-Queue-publisher'})
    status, _ = fetch(request, 1024 * 1024)
    if status != 201:
        raise PublishError(f'Unexpected publish status {status}; check the Cloud version before retrying.')
    print(f'Orca Cloud accepted queue version {version} (HTTP 201).')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-wheel', type=Path)
    parser.add_argument('--tag')
    args = parser.parse_args()
    try:
        if args.check_wheel:
            validate_wheel(args.check_wheel.read_bytes(), version_from_tag(args.tag))
            print('Offline validation passed; nothing was published.')
        else:
            if args.tag:
                raise PublishError('--tag is only used with --check-wheel.')
            event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text(encoding='utf-8'))
            publish(event, os.environ)
        return 0
    except (PublishError, OSError, KeyError, ValueError) as exc:
        # Only controlled messages are shown; never print tokens or server bodies.
        print(str(exc) if isinstance(exc, PublishError) else 'Cannot read local event/artifact data.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
