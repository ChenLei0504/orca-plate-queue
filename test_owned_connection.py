"""Private transport/provider/login tests. All endpoints and devices are fixtures."""
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch, MagicMock
import urllib.error
from cloud_login import CloudLogin, CloudLoginError
from owned_connection import OwnedCloudConnection, PrivateProcess, OwnedConnectionError, private_process_command
from local_paths import fs_path


class Reply(io.BytesIO):
    pass


class Opener:
    def __init__(self, body):
        self.body = body
        self.calls = []
    def open(self, request, timeout):
        self.calls.append(request)
        if isinstance(self.body, Exception):
            raise self.body
        return Reply(json.dumps(self.body).encode())


class LoginTests(unittest.TestCase):
    def test_regions_and_verification_code_payloads(self):
        for region, account, expected in [('CN', 'me@example.com', 'https://api.bambulab.cn/'),
                                         ('US', 'me@example.com', 'https://api.bambulab.com/'),
                                         ('CN', '13800000000', 'https://bambulab.cn/')]:
            opener = Opener({'code': 0})
            CloudLogin(opener).send_code(region, account)
            self.assertTrue(opener.calls[0].full_url.startswith(expected))
            self.assertEqual(json.loads(opener.calls[0].data)['type'], 'codeLogin')

    def test_bad_input_never_contacts_cloud(self):
        opener = Opener({})
        client = CloudLogin(opener)
        for region, account in [('bad', 'me@example.com'), ('US', '13800000000'), ('CN', 'not-an-account')]:
            with self.assertRaises(CloudLoginError):
                client.send_code(region, account)
        with self.assertRaises(CloudLoginError):
            client.login('CN', 'me@example.com', 'ABCDEF')
        self.assertEqual(opener.calls, [])

    def test_only_auth_fields_enter_private_pipe(self):
        result = CloudLogin(Opener({'accessToken': 'SECRET', 'refreshToken': 'REFRESH',
                     'expiresIn': 3600, 'account': 'private', 'user': {'uid': 'private'}, 'extra': 'private'})).login('CN', 'me@example.com', '123456')
        self.assertEqual(set(result), {'accessToken', 'refreshToken', 'expiresIn'})

    def test_server_errors_do_not_echo_tokens(self):
        error = urllib.error.HTTPError('https://api.bambulab.cn', 401, 'SECRET', {}, Reply(b'SECRET'))
        with self.assertRaises(CloudLoginError) as caught:
            CloudLogin(Opener(error)).login('CN', 'me@example.com', '123456')
        self.assertNotIn('SECRET', str(caught.exception))

    def test_redirect_does_not_send_code_to_other_host(self):
        from cloud_login import _NoRedirect
        self.assertIsNone(_NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.invalid'))


def eventually(check, seconds=8):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if check():
            return
        time.sleep(.03)
    raise AssertionError('Timed out waiting for fixture')


class FakeProcess:
    instances = []
    def __init__(self, _):
        self.raw = dict(protocol=1, origin='orca-owned-cloud', attached=True, cloud_session_reused=False,
                        devices=[], can_submit=False, logged_in=False, cloud_connected=False)
        self.calls=[]
        self.closed=False
        self.fail=False
        self.instances.append(self)
    def call(self, action, payload=None):
        if self.fail:
            raise OwnedConnectionError('fixture disconnected')
        self.calls.append(action)
        if action == 'snapshot':
            return json.loads(json.dumps(self.raw))
        if action == 'authenticate':
            self.raw.update(logged_in=True,can_submit=True)
        if action == 'connect':
            self.raw['cloud_connected']=True
        if action == 'logout':
            self.raw.update(logged_in=False,cloud_connected=False,can_submit=False)
        return 0
    def close(self):
        self.closed=True


class StartupPermissionTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'Windows host audit contract')
    def test_process_grant_is_identical_across_parent_restarts(self):
        executable=Path('C:/Plugin Test/native-bin/orca_queue_host.exe')
        commands=[]
        for parent in (11111,22222):
            child=MagicMock()
            child.stdout.readline.return_value=b''
            child.poll.return_value=0
            with patch('owned_connection.subprocess.Popen',return_value=child) as popen, patch('owned_connection.os.getpid',return_value=parent):
                process=PrivateProcess(executable,verify=False)
                process.close()
            args,kwargs=popen.call_args
            # Orca stores audit args[1]: on Windows Popen passes a command string.
            commands.append(args[0])
            self.assertEqual(args[0],private_process_command(executable))
            self.assertNotIn(str(parent),args[0])
            self.assertEqual(kwargs['env']['ORCA_QUEUE_PARENT_PID'],str(parent))
            self.assertFalse(kwargs['shell'])
        self.assertEqual(commands[0],commands[1])

    @unittest.skipUnless(os.name == 'nt', 'Windows private path spelling')
    def test_short_private_session_mkdir_uses_normal_allowed_root_on_restart(self):
        with tempfile.TemporaryDirectory() as root:
            mkdir=Path.mkdir
            def audited_mkdir(path,*args,**kwargs):
                if str(path).startswith(chr(92)*2+'?'+chr(92)):
                    raise PermissionError('Orca does not match extended spelling to ordinary allowed root')
                return mkdir(path,*args,**kwargs)
            for _ in range(2):
                provider=OwnedCloudConnection(root,process_factory=FakeProcess)
                try:
                    with patch.object(Path,'mkdir',audited_mkdir):
                        provider.start()
                        eventually(lambda:provider._raw is not None or provider.status()['failed'])
                        self.assertIsNotNone(provider._raw,provider.status()['note'])
                finally:provider.close()


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.opener = Opener({'accessToken': 'SECRET'})
        self.provider = OwnedCloudConnection(self.folder.name, process_factory=FakeProcess, login_client=CloudLogin(self.opener))
        self.addCleanup(self.provider.close)
        self.provider.start()
        eventually(lambda: self.provider._raw is not None)

    def test_login_status_and_local_logout_without_credentials(self):
        self.provider.auth_action('login',dict(region='CN',account='me@example.com',code='123456'))
        eventually(lambda: self.provider.status()['logged_in'])
        self.assertNotIn('SECRET',json.dumps(self.provider.status()))
        self.assertNotIn('SECRET',json.dumps(self.provider.snapshot()))
        self.provider.auth_action('logout',{})
        eventually(lambda: not self.provider.status()['busy'])
        self.assertFalse(self.provider.status()['logged_in'])

    def test_double_send_and_cooldown(self):
        self.opener.body={'code':0}
        self.provider.auth_action('send_code',dict(region='CN',account='me@example.com'))
        eventually(lambda: not self.provider.status()['busy'])
        with self.assertRaises(ValueError):
            self.provider.auth_action('send_code',dict(region='CN',account='me@example.com'))
        self.assertEqual(len(self.opener.calls),1)

    def test_dead_process_drops_cache_and_never_replays(self):
        process = self.provider._process
        process.fail=True
        with self.assertRaises(OwnedConnectionError):
            self.provider.command({'action':'submit','request_id':'once'})
        self.assertTrue(process.closed)
        with self.assertRaises(OwnedConnectionError):
            self.provider.snapshot()
        self.assertEqual(process.calls.count('command'),0)

    def test_cached_age_advances(self):
        with self.provider._mu:
            self.provider._raw['devices']=[{'age_ms':10,'state_age_ms':20}]
            self.provider._updated=time.monotonic()-2
        self.assertGreaterEqual(self.provider.snapshot()['devices'][0]['age_ms'],2000)


FIXTURE=Path(__file__).parent/'native/owned-host-fixture/orca_queue_host.exe'
@unittest.skipUnless(os.name=='nt' and FIXTURE.is_file(), 'Build native/build_owned_host.py --fixture first')
class NativePrivatePipeTests(unittest.TestCase):
    def test_unicode_long_path_login_catalog_and_shutdown(self):
        with tempfile.TemporaryDirectory(prefix='独立云测试-') as folder:
            storage=fs_path(Path(folder)/('长路径目录'*20)/('队列目录'*15),force=True)
            storage.mkdir(parents=True)
            process=PrivateProcess(FIXTURE)
            try:
                self.assertEqual(process.call('open',dict(storage=str(storage),region='CN')),0)
                self.assertFalse(process.call('snapshot')['logged_in'])
                process.call('authenticate',{'accessToken':'TEST-SECRET-DO-NOT-EXPOSE'})
                process.call('connect')
                process.call('refresh')
                eventually(lambda: len(process.call('snapshot').get('devices',[]))==2)
                raw=process.call('snapshot')
                self.assertTrue(raw['can_submit'])
                self.assertNotIn('TEST-SECRET',json.dumps(raw))
                self.assertNotIn('NEVER-EXPORTED',json.dumps(raw))
                self.assertEqual(process.call('close'),0)
            finally:
                process.close()

    def test_private_process_ams_external_and_idempotent_receipts(self):
        import hashlib
        for use_ams in (True,False):
            with self.subTest(use_ams=use_ams), tempfile.TemporaryDirectory(prefix='queue-submit-fixture-') as folder:
                asset=Path(folder)/'中文模型.3mf';asset.write_bytes(b'abc')
                process=PrivateProcess(FIXTURE)
                try:
                    process.call('open',dict(storage=folder,region='CN'))
                    process.call('authenticate',{'accessToken':'TEST-SECRET-DO-NOT-EXPOSE'})
                    process.call('connect');process.call('refresh')
                    eventually(lambda:any(d.get('telemetry',{}).get('gcode_state')=='IDLE' for d in process.call('snapshot').get('devices',[])))
                    mapping=[-1]*10;mapping[8]=2 if use_ams else -1
                    details=[dict(ams=mapping[i],targetColor='EBE6E6FF' if i==8 else '',filamentId='GFG99' if i==8 else '',filamentType='PETG' if i==8 else '') for i in range(10)]
                    details[8]['nozzleId']=1
                    request=dict(action='submit',request_id='fixture_submit_once',device_id='fixture-a1',tag='oq_fixture_0001',
                        path=str(asset),sha256=hashlib.sha256(b'abc').hexdigest(),plate=5,ams_mapping=mapping,ams_mapping_info=details,
                        use_ams=use_ams,options=dict(bed_leveling=True,flow_calibration=False,timelapse=False))
                    self.assertEqual(process.call('command',request),0)
                    self.assertEqual(process.call('command',request),1)
                    eventually(lambda:any(r.get('status')=='sent' for r in process.call('snapshot').get('commands',[])))
                    state=process.call('snapshot')
                    self.assertEqual(len(state['commands']),1)
                    self.assertNotIn('SHOULD-NOT-EXPORT',json.dumps(state))
                    self.assertTrue(state['devices'][0]['task_events'])
                finally:process.close()

    def test_session_folder_is_exclusively_owned(self):
        with tempfile.TemporaryDirectory() as folder:
            first=PrivateProcess(FIXTURE);second=PrivateProcess(FIXTURE)
            try:
                first.call('open',dict(storage=folder,region='CN'))
                with self.assertRaises(OwnedConnectionError) as caught:
                    second.call('open',dict(storage=folder,region='CN'))
                self.assertIn('-10',str(caught.exception))
            finally:first.close();second.close()

    def test_executable_and_session_both_under_long_unicode_directories(self):
        import shutil
        with tempfile.TemporaryDirectory(prefix='long-executable-') as folder:
            root=fs_path(Path(folder)/('独立连接中文路径'*14)/('长目录'*20),force=True)
            binary=root/'native-bin';binary.mkdir(parents=True)
            for name in ('orca_queue_host.exe','orca_queue_owned_backend.dll','msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll','manifest.json'):
                shutil.copyfile(FIXTURE.parent/name,binary/name)
            storage=root/'登录数据';storage.mkdir()
            process=PrivateProcess(binary/'orca_queue_host.exe')
            try:
                self.assertEqual(process.call('open',dict(storage=str(storage),region='CN')),0)
                self.assertFalse(process.call('snapshot')['logged_in'])
            finally:process.close()

    def test_no_commands_after_child_termination(self):
        process=PrivateProcess(FIXTURE,timeout=1)
        process.close()
        with self.assertRaises(OwnedConnectionError):
            process.call('command',{'action':'submit'})


if __name__=='__main__':
    unittest.main()
