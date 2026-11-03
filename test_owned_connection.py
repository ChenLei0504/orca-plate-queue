"""Private transport/provider/login tests. All endpoints and devices are fixtures."""
import io
from email.message import Message
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
        if request.get_method() == 'GET':
            response=Reply(b'')
            response.status=204
            response.headers=Message()
            response.headers.add_header('Set-Cookie','bbl_csrf_token=fixture-csrf; Path=/; Secure; HttpOnly')
            return response
        return Reply(json.dumps(self.body).encode())


class LoginTests(unittest.TestCase):
    def test_regions_and_verification_code_payloads(self):
        for region, account, expected in [('CN', 'me@example.com', 'https://api.bambulab.cn/'),
                                         ('US', 'me@example.com', 'https://api.bambulab.com/'),
                                         ('CN', '13800000000', 'https://bambulab.cn/')]:
            opener = Opener({'code': 0})
            CloudLogin(opener).send_code(region, account)
            self.assertTrue(opener.calls[-1].full_url.startswith(expected))
            self.assertEqual(json.loads(opener.calls[-1].data)['type'], 'codeLogin')

    def test_sms_gets_own_csrf_before_post_and_never_sends_it_to_api_login(self):
        opener=Opener({'accessToken':'fixture-token','code':0})
        client=CloudLogin(opener)
        client.send_code('CN','13800000000')
        self.assertEqual(len(opener.calls),2)
        self.assertEqual(opener.calls[0].full_url,'https://bambulab.cn/api/csrf')
        self.assertIsNone(opener.calls[0].data)
        self.assertEqual(opener.calls[1].get_header('Cookie'),'bbl_csrf_token=fixture-csrf')
        self.assertEqual(opener.calls[1].get_header('X-bbl-csrf-token'),'fixture-csrf')
        client.login('CN','13800000000','123456')
        self.assertIsNone(opener.calls[-1].get_header('Cookie'))
        self.assertIsNone(opener.calls[-1].get_header('X-bbl-csrf-token'))

    def test_missing_csrf_cookie_stops_before_requesting_sms(self):
        opener=Opener({})
        response=Reply(b'');response.status=204;response.headers=Message()
        with patch.object(opener,'open',return_value=response) as request:
            with self.assertRaises(CloudLoginError):CloudLogin(opener).send_code('CN','13800000000')
            self.assertEqual(request.call_count,1)

    def test_403_reason_is_classified_without_leaking_response_or_retry(self):
        for body,expected in [(b'{"error":"missing_cookie", "private":"SECRET"}','网页校验'),
                              (b'<html>cloudflare SECRET</html>','安全验证'),
                              (b'{"private":"SECRET"}','无法仅凭')]:
            error=urllib.error.HTTPError('https://bambulab.cn',403,'SECRET',{},Reply(body))
            opener=Opener(error)
            with self.assertRaises(CloudLoginError) as caught:
                CloudLogin(opener).send_code('CN','x@example.com')
            self.assertIn(expected,str(caught.exception))
            self.assertNotIn('SECRET',str(caught.exception))
            self.assertEqual(len(opener.calls),1)

    def test_network_errors_have_safe_stage_specific_diagnostics(self):
        import socket,ssl
        cases=[(TimeoutError('SECRET'), 'TIMEOUT'),
               (urllib.error.URLError(socket.gaierror(-1,'SECRET')), 'DNS'),
               (ssl.SSLCertVerificationError('SECRET'), 'TLS_CERTIFICATE'),
               (ConnectionResetError('SECRET'), 'CONNECTION'),
               (RuntimeError('SECRET audit permission required'), 'PERMISSION'),
               (RuntimeError('SECRET'), 'INTERNAL')]
        for error,category in cases:
            with self.subTest(category=category):
                opener=Opener(error)
                with self.assertRaises(CloudLoginError) as caught:
                    CloudLogin(opener).send_code('CN','x@example.com')
                self.assertEqual(caught.exception.diagnostic,'EMAIL_SEND/'+category)
                self.assertNotIn('SECRET',str(caught.exception))
                self.assertEqual(len(opener.calls),1)

    def test_verification_acknowledgements_do_not_relax_login_token_validation(self):
        for body,status in [(b'',204),(b'"OK"',200),(b'"success"',200)]:
            def response(*args,**kwargs):
                result=Reply(body);result.status=status;return result
            opener=Opener({})
            with patch.object(opener,'open',side_effect=response):
                CloudLogin(opener).send_code('CN','x@example.com')
                with self.assertRaises(CloudLoginError):
                    CloudLogin(opener).login('CN','x@example.com','123456')

    def test_unexpected_response_is_not_reported_as_network_failure(self):
        for body,category in [(b'<html>SECRET</html>','NON_JSON'),
                              (b'"SECRET"','JSON_STRING'),(b'[]','JSON_SHAPE')]:
            response=Reply(body);response.status=200
            with patch.object(Opener,'open',return_value=response):
                with self.assertRaises(CloudLoginError) as caught:
                    CloudLogin(Opener({})).send_code('CN','x@example.com')
            self.assertEqual(caught.exception.diagnostic,'EMAIL_SEND/HTTP_200/'+category)
            self.assertNotIn('SECRET',str(caught.exception))

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
        if action in ('authenticate','ticket'):
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


class PermissionRecoveryTests(unittest.TestCase):
    def test_audit_prompt_pauses_until_explicit_reconnect(self):
        with tempfile.TemporaryDirectory() as root:
            approved=False
            attempts=[]
            def factory(executable):
                attempts.append(executable)
                if not approved:
                    raise RuntimeError('Plugin attempted audited operation "open" without permission: audit permission required')
                return FakeProcess(executable)
            provider=OwnedCloudConnection(root,process_factory=factory)
            try:
                provider.start()
                eventually(lambda:provider.status()['failed'])
                self.assertIn('重新连接',provider.status()['note'])
                self.assertIn('无需重启或重装',provider.status()['note'])
                provider.refresh()
                eventually(lambda:provider._queue.empty())
                self.assertEqual(len(attempts),1, 'Polling must not create repeated permission prompts')
                approved=True
                provider.auth_action('reconnect',{})
                eventually(lambda:provider._raw is not None and not provider.status()['busy'])
                self.assertFalse(provider.status()['failed'])
                self.assertFalse(provider.status()['logged_in'])
                self.assertEqual(provider.status()['note'],'请登录 Bambu Cloud。')
                self.assertEqual(len(attempts),2)
                self.assertNotIn('command',provider._process.calls)
            finally:provider.close()


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.opener = Opener({'accessToken': 'SECRET'})
        self.provider = OwnedCloudConnection(self.folder.name, process_factory=FakeProcess)
        self.addCleanup(self.provider.close)
        self.provider.start()
        eventually(lambda: self.provider._raw is not None)

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

    def test_browser_callback_through_real_private_pipe_to_fixture_catalog(self):
        import http.client
        from urllib.parse import urlsplit
        with tempfile.TemporaryDirectory() as folder:
            provider=OwnedCloudConnection(folder,executable=FIXTURE)
            try:
                provider.start();eventually(lambda:provider._raw is not None)
                provider.auth_action('browser_begin',{'region':'CN'})
                eventually(lambda:provider.status()['browser_url'])
                browser=provider._browser
                request=http.client.HTTPConnection(browser.authority,timeout=3)
                try:
                    request.request('GET',urlsplit(browser.callback_url).path+'?ticket=fixture-ticket')
                    response=request.getresponse();response.read();self.assertEqual(response.status,200)
                finally:request.close()
                provider.refresh()
                eventually(lambda:provider.status()['connected'])
                eventually(lambda:len(provider.snapshot().get('devices',[]))==2)
                self.assertEqual(provider.status()['browser_url'],'')
                self.assertNotIn('TEST-SECRET',json.dumps(provider.snapshot()))
            finally:provider.close()

    def test_native_system_browser_destination_matches_callback_and_rejects_commands(self):
        from browser_login import BrowserLogin
        process=PrivateProcess(FIXTURE)
        try:
            for region in ('CN','US'):
                browser=BrowserLogin(region)
                try:
                    payload=browser.launch_payload()
                    # The fixture compiles out ShellExecute: this returns the would-be URL.
                    self.assertEqual(process.call('open_login_browser',payload),browser.url)
                    for field,values in [('region',['https://evil.invalid','CN&evil=1']),
                                         ('port',[0,65536,True,'13618',1.5]),
                                         ('nonce',['short','x'*42+'/', 'x'*42+'\n'])]:
                        for value in values:
                            with self.assertRaises(OwnedConnectionError):
                                process.call('open_login_browser',dict(payload,**{field:value}))
                    with self.assertRaises(OwnedConnectionError):
                        process.call('open_login_browser',{'url':'file:///C:/Windows/System32/cmd.exe'})
                finally:browser.close()
        finally:process.close()

    def test_ticket_exchange_is_single_use_and_never_exports_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            process=PrivateProcess(FIXTURE)
            try:
                process.call('open',dict(storage=folder,region='CN'))
                with self.assertRaises(OwnedConnectionError):process.call('ticket',{'ticket':'invalid-ticket'})
                with self.assertRaises(OwnedConnectionError):process.call('ticket',{'ticket':'fixture-ticket'})
                process.close()
                process=PrivateProcess(FIXTURE)
                process.call('open',dict(storage=folder,region='CN'))
                process.call('ticket',{'ticket':'fixture-ticket'})
                raw=process.call('snapshot')
                self.assertTrue(raw['logged_in'])
                self.assertNotIn('TEST-SECRET',json.dumps(raw))
                self.assertNotIn('fixture-ticket',json.dumps(raw))
                with self.assertRaises(OwnedConnectionError):process.call('ticket',{'ticket':'fixture-ticket'})
            finally:process.close()

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
