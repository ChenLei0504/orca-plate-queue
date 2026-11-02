"""UI language preferences use private fixtures; never connect to a printer."""
import json
from pathlib import Path
import types
import unittest
from unittest.mock import patch

from page_preferences import PagePreferences
from test_queue import temporary_directory
import test_plugin as packaged


class PreferenceStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp=temporary_directory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'中文 UI 设置'

    def test_default_is_simplified_chinese_without_writing(self):
        store=PagePreferences(self.root)
        self.assertEqual(store.language,'zh-CN')
        self.assertFalse(self.root.exists())

    def test_language_survives_reopening_and_switching_back(self):
        store=PagePreferences(self.root);store.set_language('en')
        self.assertEqual(store.revision,1)
        self.assertEqual(PagePreferences(self.root).language,'en')
        store.set_language('zh-CN')
        self.assertEqual(store.revision,2)
        self.assertEqual(PagePreferences(self.root).language,'zh-CN')
        self.assertEqual(json.loads(store.path.read_text(encoding='utf-8')),{'language':'zh-CN'})

    def test_invalid_or_corrupt_preferences_fall_back_without_overwriting(self):
        self.root.mkdir()
        for saved in ('{bad','[]','{"language":"fr"}','{"language":null}'):
            with self.subTest(saved=saved):
                path=self.root/'page-preferences.json';path.write_text(saved,encoding='utf-8')
                self.assertEqual(PagePreferences(self.root).language,'zh-CN')
                self.assertEqual(path.read_text(encoding='utf-8'),saved)

    def test_unknown_languages_are_rejected_without_creating_files(self):
        for value in ('fr','en-US','../en',None,True,[],{}):
            with self.subTest(value=value),self.assertRaises(ValueError):PagePreferences(self.root).set_language(value)
        self.assertFalse(self.root.exists())

    def test_failed_replace_keeps_old_preference_and_cleans_pending_file(self):
        store=PagePreferences(self.root);store.set_language('en')
        before=store.path.read_bytes()
        with patch('page_preferences.os.replace',side_effect=OSError('fixture failure')),self.assertRaises(OSError):
            store.set_language('zh-CN')
        self.assertEqual(store.language,'en');self.assertEqual(store.revision,1)
        self.assertEqual(store.path.read_bytes(),before)
        self.assertEqual(list(self.root.iterdir()),[store.path])


class PageLanguageActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        packaged.PluginTests.setUpClass();cls.module=packaged.PluginTests.module

    @classmethod
    def tearDownClass(cls):packaged.PluginTests.tearDownClass()

    def setUp(self):
        self.temp=temporary_directory();self.addCleanup(self.temp.cleanup)
        self.module.orca.host=types.SimpleNamespace(plugin=types.SimpleNamespace(storage=lambda:Path(self.temp.name)/'private'))
        self.page=self.module.PrintQueuePage();self.page.on_load();self.addCleanup(self.page.on_unload)

    def test_global_language_action_never_reads_device_state_or_changes_queue(self):
        before=self.page._service.snapshot()
        def forbidden():raise AssertionError('language must not poll or control printers')
        self.page._connection.snapshot=forbidden
        self.page.on_message({'action':'set_language','request_id':'locale-1','queue_id':'stale-view','language':'en'})
        self.assertTrue(self.page.reply['success']);self.assertEqual(self.page.reply['language'],'en')
        self.assertEqual(self.page.reply['language_revision'],1)
        self.assertEqual(self.page._service.snapshot(),before)
        self.page.on_unload();self.page.on_load()
        self.assertEqual(self.page._preferences.language,'en')

    def test_invalid_language_has_no_queue_or_preference_side_effect(self):
        before=self.page._service.snapshot()
        self.page.on_message({'action':'set_language','language':'fr','request_id':'invalid'})
        self.assertFalse(self.page.reply['success'])
        self.assertEqual(self.page._preferences.language,'zh-CN')
        self.assertFalse(self.page._preferences.path.exists())
        self.assertEqual(self.page._service.snapshot(),before)


if __name__=='__main__':unittest.main()
