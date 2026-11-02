"""Initialization permission recovery, using private fixtures and a fake host."""
import types
import unittest
from pathlib import Path
from unittest.mock import patch
import test_plugin as packaged
from test_queue import temporary_directory

class InitializationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        packaged.PluginTests.setUpClass();cls.module=packaged.PluginTests.module
    @classmethod
    def tearDownClass(cls):packaged.PluginTests.tearDownClass()
    def setUp(self):
        self.temp=temporary_directory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'private'
        self.module.orca.host=types.SimpleNamespace(plugin=types.SimpleNamespace(storage=lambda:self.root))
        self.page=self.module.PrintQueuePage();self.addCleanup(self.page.on_unload)
    def offline(self):
        self.page._connection.snapshot=lambda:dict(available=False,devices=[],reason='fixture offline')
    def test_permission_grant_then_explicit_retry_recovers(self):
        original=Path.open;attempts=[]
        def denied(path,*a,**kw):
            if path.name=='executor.lock':
                attempts.append(str(path))
                raise PermissionError('Plugin attempted audited operation "open" without permission: audit permission required')
            return original(path,*a,**kw)
        with patch.object(Path,'open',denied):
            self.page.on_load();self.assertIn('audit permission required',self.page._error)
            for n in range(3):self.page.on_message(dict(action='refresh',request_id=str(n)))
            self.assertEqual(len(attempts),1) # polling must not repeat permission requests
            self.assertEqual(self.page.reply['request_id'],'2')
            self.assertTrue(self.page.reply['initialization_failed'])
            self.page.on_message(dict(action='retry_initialize',request_id='denied'))
            self.assertEqual(len(attempts),2)
            self.assertFalse(self.page.reply['success'])
        with patch.object(self.module.PrinterConnection,'snapshot',return_value=dict(available=False,devices=[],reason='offline')):
            self.page.on_message(dict(action='retry_initialize',request_id='allowed'))
        self.assertTrue(self.page.reply['success']);self.assertEqual(self.page.reply['request_id'],'allowed')
        self.assertEqual(self.page._error,'');self.assertFalse(self.page._data['running'])
        self.assertIsNone(self.page._data['active'])
    def test_denied_preferences_are_not_silently_replaced_with_defaults(self):
        self.root.mkdir();(self.root/'page-preferences.json').write_text('{"language":"en"}',encoding='utf8')
        original=Path.open
        def denied(path,*a,**kw):
            if path.name=='page-preferences.json':raise PermissionError('fixture preference denied')
            return original(path,*a,**kw)
        with patch.object(Path,'open',denied):self.page.on_load()
        self.assertIn('fixture preference denied',self.page._error)
        self.assertFalse((self.root/'v3').exists())
        self.page.on_load();self.assertEqual(self.page._error,'')
        self.assertEqual(self.page._preferences.language,'en')
    def test_later_constructor_failure_releases_executor_lock_for_retry(self):
        with patch.object(self.module.sqlite3,'connect',side_effect=PermissionError('fixture database denied')):
            self.page.on_load()
        self.assertIn('fixture database denied',self.page._error)
        self.page.on_load();self.assertEqual(self.page._error,'')
        self.offline();self.page.on_message(dict(action='refresh'));self.assertTrue(self.page.reply['success'])
    def test_retry_on_healthy_page_does_not_restart_executor_or_change_queue(self):
        self.page.on_load();self.offline();service=self.page._service;before=service.snapshot()
        with patch.object(self.page,'on_load',side_effect=AssertionError('must not restart healthy queue')):
            self.page.on_message(dict(action='retry_initialize',request_id='healthy'))
        self.assertTrue(self.page.reply['success']);self.assertIs(service,self.page._service)
        self.assertEqual(before,service.snapshot())

if __name__=='__main__':unittest.main()
