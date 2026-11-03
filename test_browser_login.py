"""Offline browser callback/provider contract; no real cloud or printer calls."""
import http.client
import json
import socket
import tempfile
import time
import unittest
from urllib.parse import parse_qs, urlsplit
from browser_login import BrowserLogin
from owned_connection import OwnedCloudConnection, ComponentRejected
from test_owned_connection import FakeProcess, eventually


class CallbackTests(unittest.TestCase):
    def setUp(self):
        self.login = BrowserLogin('CN')
        self.addCleanup(self.login.close)

    def request(self, path=None, method='GET', headers=None, body=None):
        c=http.client.HTTPConnection(self.login.authority, timeout=3)
        try:
            c.request(method, path or urlsplit(self.login.callback_url).path, body=body, headers=headers or {})
            r=c.getresponse()
            return r.status, r.read().decode(), dict(r.getheaders())
        finally:c.close()

    def test_regional_signin_url_contains_unique_callback(self):
        for region,host in [('CN','bambulab.cn'),('US','bambulab.com')]:
            other=BrowserLogin(region)
            try:
                outer=urlsplit(other.url)
                self.assertEqual(outer.scheme,'https');self.assertEqual(outer.netloc,host)
                inner=urlsplit(parse_qs(outer.query)['to'][0]);q=parse_qs(inner.query)
                self.assertEqual(inner.netloc,host)
                self.assertEqual(q['redirect_url'],[other.callback_url])
                self.assertEqual(q['slicerLoginType'],['ticket'])
                self.assertEqual(urlsplit(other.callback_url).hostname,'127.0.0.1')
                self.assertNotEqual(other._path,self.login._path)
            finally:other.close()
        with self.assertRaises(ValueError):BrowserLogin('INVALID')

    def test_ticket_received_once_no_secret_in_response(self):
        path=self.login._path+'?ticket=fixture-ticket'
        status,body,headers=self.request(path)
        self.assertEqual(status,200);self.assertNotIn('fixture-ticket',body)
        self.assertEqual(headers['Cache-Control'],'no-store')
        self.assertEqual(self.login.poll(),'fixture-ticket');self.assertIsNone(self.login.poll())
        self.assertEqual(self.request(path)[0],409)
        self.assertIsNone(self.login.poll())

    def test_wrong_host_nonce_duplicate_or_bad_ticket_rejected(self):
        path=self.login._path+'?ticket=secret'
        for p,h,code in [(path,{'Host':'evil.example'},404),('/callback/wrong?ticket=secret',{},404),
                         (path+'&ticket=second',{},400),(self.login._path+'?ticket=bad%2Fvalue',{},409)]:
            self.assertEqual(self.request(p,headers=h)[0],code)
            self.assertIsNone(self.login.poll())

    def test_fragment_bridge_requires_same_origin_and_only_ticket(self):
        self.assertIn('location.hash',self.request()[1])
        body=json.dumps({'ticket':'fixture-ticket'})
        self.assertEqual(self.request(method='POST',body=body,headers={'Origin':'https://evil.example'})[0],403)
        self.assertIsNone(self.login.poll())
        self.assertEqual(self.request(method='POST',body='{"ticket":"x","extra":1}',headers={'Origin':self.login.origin})[0],400)
        self.assertEqual(self.request(method='POST',body=body,headers={'Origin':self.login.origin})[0],200)
        self.assertEqual(self.login.poll(),'fixture-ticket')

    def test_expiry_and_close_release_socket_and_discard_ticket(self):
        self.login.take('unused-ticket');self.login.close()
        self.assertIsNone(self.login.poll())
        with self.assertRaises(OSError):socket.create_connection(('127.0.0.1',int(self.login.authority.split(':')[1])),timeout=.3)
        expired=BrowserLogin('CN',lifetime=.03)
        try:
            eventually(lambda:expired.expired)
            self.assertFalse(expired.take('late-ticket'))
            eventually(lambda:not expired._thread.is_alive())
        finally:expired.close()


class BrowserProviderTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.provider=OwnedCloudConnection(self.folder.name,process_factory=FakeProcess)
        self.addCleanup(self.provider.close);self.provider.start()
        eventually(lambda:self.provider._raw is not None)

    def begin(self):
        self.provider.auth_action('browser_begin',{'region':'CN'})
        eventually(lambda:self.provider.status()['browser_waiting'] and not self.provider.status()['busy'])
        return self.provider._browser

    def test_callback_connects_without_account_or_sms_request(self):
        browser=self.begin()
        self.assertTrue(browser.take('fixture-ticket'))
        self.provider.refresh()
        eventually(lambda:self.provider.status()['logged_in'] and not self.provider.status()['busy'])
        status=self.provider.status()
        self.assertFalse(status['browser_waiting']);self.assertEqual(status['browser_url'],'')
        self.assertNotIn('fixture-ticket',json.dumps(status))
        self.assertEqual(self.provider._process.calls.count('ticket'),1)
        self.assertNotIn('authenticate',self.provider._process.calls)
        self.provider.auth_action('logout',{})
        eventually(lambda:not self.provider.status()['busy'])
        self.assertFalse(self.provider.status()['logged_in'])

    def test_browser_only_opens_on_click_with_private_callback_parameters(self):
        browser=self.begin();process=self.provider._process;opened=[];launchers=[]
        def factory(executable):
            launcher=FakeProcess(executable);launchers.append(launcher);original=launcher.call
            def capture(action,payload=None):
                if action=='open_login_browser':opened.append(payload)
                return original(action,payload)
            launcher.call=capture
            return launcher
        self.provider._factory=factory
        self.provider.refresh();eventually(lambda:self.provider._queue.empty())
        self.assertEqual(opened,[])
        self.provider.auth_action('browser_open',{'url':'https://evil.invalid','region':'US'})
        eventually(lambda:not self.provider.status()['busy'])
        self.assertEqual(opened,[browser.launch_payload()])
        self.assertEqual(opened[0]['region'],'CN')
        self.assertNotIn('url',opened[0])
        self.assertEqual(len(launchers),1)
        self.assertTrue(launchers[0].closed)
        self.assertNotIn('open',launchers[0].calls)
        self.assertNotIn('open_login_browser',process.calls)
        self.assertFalse(process.closed)
        self.assertTrue(self.provider.status()['browser_waiting'])
        self.provider.auth_action('browser_cancel',{})
        eventually(lambda:not self.provider.status()['busy'])
        with self.assertRaises(ValueError):self.provider.auth_action('browser_open',{})

    def test_browser_launch_failure_preserves_link_for_manual_copy(self):
        browser=self.begin();process=self.provider._process;launchers=[]
        def factory(executable):
            launcher=FakeProcess(executable);launchers.append(launcher)
            def reject(action,payload=None):
                raise ComponentRejected('无法打开系统浏览器，请复制登录链接到 Chrome 或 Edge')
            launcher.call=reject
            return launcher
        self.provider._factory=factory
        self.provider.auth_action('browser_open',{})
        eventually(lambda:not self.provider.status()['busy'])
        self.assertFalse(self.provider.status()['failed'])
        self.assertEqual(self.provider.status()['browser_url'],browser.url)
        self.assertIn('复制',self.provider.status()['note'])
        self.assertTrue(launchers[0].closed)
        self.assertFalse(process.closed)

    def test_cancel_reconnect_and_unload_destroy_pending_login(self):
        for action in ('browser_cancel','reconnect'):
            browser=self.begin()
            self.provider.auth_action(action,{})
            eventually(lambda:not self.provider.status()['busy'])
            self.assertFalse(browser.take('late-ticket'))
            self.assertFalse(self.provider.status()['browser_waiting'])
            self.assertNotIn('ticket',self.provider._process.calls)
        browser=self.begin();self.provider.close()
        self.assertFalse(browser.take('late-ticket'))
        self.assertFalse(browser._thread.is_alive())

    def test_expired_login_is_reported_without_automatic_restart(self):
        browser=self.begin();browser._deadline=time.monotonic()-1
        self.provider.refresh()
        eventually(lambda:not self.provider.status()['browser_waiting'] and '超时' in self.provider.status()['note'])
        self.assertIn('超时',self.provider.status()['note'])
        self.assertEqual(self.provider.status()['browser_url'],'')
        self.assertNotIn('ticket',self.provider._process.calls)

    def test_rejected_ticket_is_never_replayed_and_new_attempt_uses_fresh_agent(self):
        browser=self.begin();process=self.provider._process;original=process.call
        attempts=[]
        def reject(action,payload=None):
            if action=='ticket':
                attempts.append(1);raise ComponentRejected('fixture rejected')
            return original(action,payload)
        process.call=reject
        browser.take('bad-ticket');self.provider.refresh()
        eventually(lambda:'不会自动重复提交' in self.provider.status()['note'])
        self.provider.refresh();eventually(lambda:self.provider._queue.empty())
        self.assertEqual(len(attempts),1)
        self.assertFalse(self.provider.status()['logged_in'])
        self.begin();self.assertIsNot(self.provider._process,process)
        self.assertTrue(process.closed)

    def test_sms_actions_are_not_supported(self):
        for action in ('send_code','login'):
            with self.assertRaises(ValueError):self.provider.auth_action(action,{})


if __name__=='__main__':unittest.main()
