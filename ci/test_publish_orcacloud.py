"""Offline publication tests: no network access, account tokens or printer actions."""
import base64
import contextlib
import csv
import hashlib
import io
import json
import unittest
from unittest.mock import patch
import urllib.error
import zipfile

from ci import publish_orcacloud as publisher


def fixture_wheel(extra=None):
    dist = 'orca_plate_queue-0.7.4.dist-info/'
    entries = {dist + 'METADATA': b'Name: orca-plate-queue\nVersion: 0.7.4\n',
               'orca_plate_queue/__init__.py': b'raise RuntimeError("must never execute")\n',
               'orca_plate_queue/core.py': b'pass\n',
               'orca_plate_queue/queue_engine.py': b'pass\n',
               'orca_plate_queue/permissions.json': b'{}'}
    entries.update(extra or {})
    record = io.StringIO(newline='')
    writer = csv.writer(record, lineterminator='\n')
    for name, data in entries.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode()
        writer.writerow([name, 'sha256=' + digest, len(data)])
    writer.writerow([dist + 'RECORD', '', ''])
    entries[dist + 'RECORD'] = record.getvalue().encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return output.getvalue()


class PublishingTests(unittest.TestCase):
    def setUp(self):
        self.wheel = fixture_wheel()
        self.event = {'action': 'published', 'repository': {'full_name': publisher.REPOSITORY},
                      'release': {'tag_name': 'v0.7.4', 'draft': False,
                                  'body': '修复 AMS；保留换盘。\n`$(do-not-execute)`',
                                  'assets': [{'name': publisher.WHEEL_NAME, 'size': len(self.wheel),
                                              'browser_download_url': f'https://github.com/{publisher.REPOSITORY}/releases/download/v0.7.4/{publisher.WHEEL_NAME}',
                                              'digest': 'sha256:' + hashlib.sha256(self.wheel).hexdigest()},
                                             {'name': 'Orca-Queue-Connection-0.7.3-Windows-x64.zip'}]}}
        self.env = {'GITHUB_EVENT_NAME': 'release', 'GITHUB_REPOSITORY': publisher.REPOSITORY,
                    'GITHUB_REF': 'refs/tags/v0.7.4',
                    'ACTIONS_ID_TOKEN_REQUEST_URL': 'https://example.invalid/oidc?request=fixture',
                    'ACTIONS_ID_TOKEN_REQUEST_TOKEN': 'private-request-fixture'}

    def test_uploads_only_validated_wheel_and_notes_with_oidc(self):
        logs = io.StringIO()
        with patch.object(publisher, 'fetch', side_effect=[(200, self.wheel),
                 (200, b'{"value":"private-oidc-fixture"}'), (201, b'{}')]) as fetch, contextlib.redirect_stdout(logs):
            publisher.publish(self.event, self.env)
        self.assertEqual(fetch.call_count, 3)
        oidc = fetch.call_args_list[1].args[0]
        self.assertTrue(oidc.full_url.endswith('&audience=orcacloud'))
        self.assertEqual(oidc.get_header('Authorization'), 'Bearer private-request-fixture')
        upload = fetch.call_args_list[2].args[0]
        self.assertEqual(upload.full_url, publisher.PUBLISH_URL)
        self.assertEqual(upload.method, 'POST')
        self.assertEqual(upload.get_header('Authorization'), 'Bearer private-oidc-fixture')
        self.assertIn(self.wheel, upload.data)
        self.assertEqual(upload.data.count(b'name="files"'), 1)
        self.assertNotIn(b'Orca-Queue-Connection', upload.data)
        self.assertIn(json.dumps({'version': '0.7.4', 'changelog': self.event['release']['body']}, ensure_ascii=False).encode(), upload.data)
        self.assertIn('HTTP 201', logs.getvalue())
        self.assertNotIn('private-', logs.getvalue())

    def test_notes_are_truncated_as_valid_utf8(self):
        self.event['release']['body'] = '中' * 2000
        with patch.object(publisher, 'fetch', side_effect=[(200, self.wheel), (200, b'{"value":"fixture"}'), (201, b'')]) as fetch, contextlib.redirect_stdout(io.StringIO()):
            publisher.publish(self.event, self.env)
        body = fetch.call_args_list[-1].args[0].data
        metadata = json.loads(body.split(b'\r\n\r\n', 1)[1].split(b'\r\n--', 1)[0])
        self.assertLessEqual(len(metadata['changelog'].encode('utf-8')), 4000)
        self.assertEqual(metadata['changelog'], '中' * 1333)

    def test_missing_attachment_never_requests_oidc_or_publishes(self):
        self.event['release']['assets'] = []
        with patch.object(publisher, 'fetch') as fetch, self.assertRaisesRegex(publisher.PublishError, 'BEFORE'):
            publisher.publish(self.event, self.env)
        fetch.assert_not_called()

    def test_wrong_repo_event_or_tag_never_downloads(self):
        for key, value in [('GITHUB_REPOSITORY', 'another/repo'), ('GITHUB_EVENT_NAME', 'push'), ('GITHUB_REF', 'refs/tags/v0.7.3')]:
            with self.subTest(key=key), patch.object(publisher, 'fetch') as fetch, self.assertRaises(publisher.PublishError):
                publisher.publish(self.event, dict(self.env, **{key: value}))
            fetch.assert_not_called()

    def test_invalid_download_never_requests_oidc_or_publishes(self):
        for field, value in [('digest', 'sha256:wrong'), ('size', len(self.wheel) + 1)]:
            with self.subTest(field=field):
                asset = self.event['release']['assets'][0]
                previous = asset[field]
                asset[field] = value
                with patch.object(publisher, 'fetch', return_value=(200, self.wheel)) as fetch, self.assertRaises(publisher.PublishError):
                    publisher.publish(self.event, self.env)
                self.assertEqual(fetch.call_count, 1)
                asset[field] = previous

    def test_matching_download_with_mismatched_metadata_never_requests_oidc(self):
        wrong = fixture_wheel({'orca_plate_queue-0.7.4.dist-info/METADATA': b'Name: orca-plate-queue\nVersion: 0.7.3\n'})
        asset = self.event['release']['assets'][0]
        asset['size'] = len(wrong)
        asset.pop('digest')
        with patch.object(publisher, 'fetch', return_value=(200, wrong)) as fetch, self.assertRaises(publisher.PublishError):
            publisher.publish(self.event, self.env)
        self.assertEqual(fetch.call_count, 1)

    def test_queue_code_is_never_imported(self):
        publisher.validate_wheel(self.wheel, '0.7.4')

    def test_rejects_binaries_private_data_development_and_traversal(self):
        for name in ['orca_plate_queue/bridge.dll', 'orca_plate_queue/setup.exe',
                     'orca_plate_queue/data.sqlite3', 'orca_plate_queue/test_queue.py',
                     'orca_plate_queue/build_release.py', 'orca_plate_queue/../escape.py']:
            with self.subTest(name=name), self.assertRaises(publisher.PublishError):
                publisher.validate_wheel(fixture_wheel({name: b'fixture'}), '0.7.4')

    def test_rejects_corrupt_record(self):
        wheel = fixture_wheel()
        # Re-write a payload without updating the RECORD hashes.
        with zipfile.ZipFile(io.BytesIO(wheel)) as archive:
            entries = {name: archive.read(name) for name in archive.namelist()}
        entries['orca_plate_queue/core.py'] = b'corrupt\n'
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as archive:
            for name, data in entries.items():
                archive.writestr(name, data)
        with self.assertRaises(publisher.PublishError):
            publisher.validate_wheel(output.getvalue(), '0.7.4')

    def test_rejects_archive_metadata_version_mismatch(self):
        with self.assertRaises(publisher.PublishError):
            publisher.validate_wheel(self.wheel, '0.7.5')

    def test_publish_failure_not_retried(self):
        with patch.object(publisher, 'fetch', side_effect=[(200, self.wheel), (200, b'{"value":"fixture"}'), (202, b'')]) as fetch, contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(publisher.PublishError, 'Unexpected publish status'):
            publisher.publish(self.event, self.env)
        self.assertEqual(fetch.call_count, 3)

    def test_http_error_never_exposes_body_or_credentials(self):
        request = publisher.urllib.request.Request(publisher.PUBLISH_URL, headers={'Authorization': 'Bearer private-fixture'})
        error = urllib.error.HTTPError(publisher.PUBLISH_URL, 401, 'private-server-detail', {}, io.BytesIO(b'private-body'))
        with patch.object(publisher.urllib.request, 'urlopen', side_effect=error), self.assertRaises(publisher.PublishError) as caught:
            publisher.fetch(request, 1024)
        self.assertIn('HTTP 401', str(caught.exception))
        self.assertNotIn('private', str(caught.exception))

    def test_only_supported_release_tags(self):
        for tag in ['$(cmd)', 'v0.07.4', '0.7', 'v0.7.4/../x', None]:
            with self.subTest(tag=tag), self.assertRaises(publisher.PublishError):
                publisher.version_from_tag(tag)


if __name__ == '__main__':
    unittest.main()
