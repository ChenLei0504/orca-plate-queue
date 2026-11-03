"""Verify the standalone wheel without installing or signing in to Orca."""
import base64
import csv
import hashlib
import importlib
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch
import zipfile
from test_plugin import Base
from test_owned_connection import FakeProcess, eventually

ROOT=Path(__file__).parent
WHEEL=ROOT/'standalone-dist/0.8.0a1/Orca_Plate_Queue_win_x86_64.whl'


@unittest.skipUnless(WHEEL.exists(),'Build standalone preview first')
class StandaloneReleaseTests(unittest.TestCase):
    def test_record_platform_native_hashes_and_honest_permissions(self):
        with zipfile.ZipFile(WHEEL) as archive:
            dist='orca_plate_queue-0.8.0a1.dist-info/'
            self.assertIn('Tag: py3-none-win_amd64',archive.read(dist+'WHEEL').decode())
            self.assertIn('OWNED_CLOUD = True',archive.read('orca_plate_queue/core.py').decode())
            for name,digest,size in csv.reader(io.StringIO(archive.read(dist+'RECORD').decode())):
                if not digest:continue
                data=archive.read(name)
                self.assertEqual(len(data),int(size))
                self.assertEqual('sha256='+base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode(),digest)
            manifest=json.loads(archive.read('orca_plate_queue/native-bin/manifest.json'))
            self.assertFalse(manifest['fixture'])
            self.assertGreaterEqual(tuple(manifest['msvc_runtime'][:2]),(14,40))
            for name,digest in manifest['files'].items():
                self.assertEqual(hashlib.sha256(archive.read('orca_plate_queue/native-bin/'+name)).hexdigest(),digest)
            permissions=json.loads(archive.read('orca_plate_queue/permissions.json'))
            self.assertTrue(permissions['process_execution'])
            self.assertTrue(permissions['bundled_native_libraries'])
            self.assertFalse(permissions['other_plugin_file_modification'])
            self.assertFalse(permissions['host_account_discovery'])
            self.assertIn('pending',permissions['real_device_validation'])

    def test_packaged_plugin_lifecycle_and_active_queue_auth_guard(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            with zipfile.ZipFile(WHEEL) as archive:archive.extractall(folder)
            host=types.ModuleType('orca')
            host.pages=types.SimpleNamespace(PagesPluginCapabilityBase=Base)
            host.base=Base;host.plugin=lambda cls:cls
            host.host=types.SimpleNamespace(plugin=types.SimpleNamespace(storage=lambda:folder/'storage'))
            host.LifecycleEvent=types.SimpleNamespace(GCodeExportFinished='export')
            host.LifecycleEvtCode=types.SimpleNamespace(Ok='ok')
            granted=[];host.request_permissions=lambda **kw:granted.append(kw)
            host.register_capability=lambda cls:None
            old={k:v for k,v in sys.modules.items() if k=='orca' or k.startswith('orca_plate_queue')}
            for key in old:sys.modules.pop(key)
            sys.modules['orca']=host
            sys.path.insert(0,str(folder))
            page=None
            try:
                core=importlib.import_module('orca_plate_queue.core')
                provider=importlib.import_module('orca_plate_queue.owned_connection')
                real=provider.OwnedCloudConnection
                core.OwnedCloudConnection=lambda storage:real(storage,process_factory=FakeProcess)
                core.PrintQueuePlugin().register_capabilities()
                self.assertEqual(len(granted[0]['process']),1)
                self.assertIn('https://api.bambulab.cn',granted[0]['network_http'])
                page=core.PrintQueuePage();page.on_load()
                self.assertEqual(page._error,'')
                eventually(lambda:page._connection.native._raw is not None)
                page.on_message({'action':'refresh'})
                self.assertTrue(page.reply['success'])
                self.assertEqual(page.reply['connection_mode'],'owned_cloud')
                self.assertFalse(page.reply['cloud_auth']['logged_in'])
                self.assertTrue((folder/'storage/v4-cloud').exists())
                self.assertFalse((folder/'storage/v3').exists())
                # No account operation may proceed while a queue could still send.
                page._service.data['running']=True
                page.on_message({'action':'cloud_login','region':'CN','account':'x@example.com','code':'123456'})
                self.assertFalse(page.reply['success'])
                self.assertIn('暂停所有队列',page.reply['note'])
                page._service.data['running']=False
                process=page._connection.native._process
                page.on_unload();page=None
                self.assertTrue(process.closed)
            finally:
                if page:page.on_unload()
                sys.path.remove(str(folder))
                for key in list(sys.modules):
                    if key=='orca' or key.startswith('orca_plate_queue'):sys.modules.pop(key)
                sys.modules.update(old)


if __name__=='__main__':unittest.main()
