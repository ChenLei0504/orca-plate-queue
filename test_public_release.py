"""Validate the actual split artifacts against an offline host."""
import base64
import csv
import hashlib
import importlib
import io
import json
from pathlib import Path
import sys
import types
import unittest
import zipfile
from release_info import QUEUE_VERSION
from test_queue import temporary_directory
from test_plugin import Base

ROOT=Path(__file__).resolve().parent
OUT=ROOT/('public-release-'+QUEUE_VERSION)
WHEEL=OUT/'Orca_Plate_Queue_win_x86_64.whl'
INSTALLER=OUT/('Orca-Queue-Connection-'+QUEUE_VERSION+'-Windows-x64.zip')

@unittest.skipUnless(WHEEL.exists(),'Build the split release first')
class PublicReleaseTests(unittest.TestCase):
    def setUp(self):
        self.archive=zipfile.ZipFile(WHEEL);self.addCleanup(self.archive.close)

    def test_wheel_metadata_and_record_hashes(self):
        names=self.archive.namelist();prefix='orca_plate_queue-'+QUEUE_VERSION+'.dist-info/'
        self.assertIn('Version: '+QUEUE_VERSION,self.archive.read(prefix+'METADATA').decode())
        self.assertIn('Tag: py3-none-any',self.archive.read(prefix+'WHEEL').decode())
        rows=list(csv.reader(io.StringIO(self.archive.read(prefix+'RECORD').decode())))
        self.assertEqual({r[0] for r in rows},set(names))
        for name,digest,size in rows:
            if name.endswith('/RECORD'):continue
            data=self.archive.read(name);self.assertEqual(len(data),int(size))
            self.assertEqual(digest,'sha256='+base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode())

    def test_no_native_installer_development_scripts_or_private_data_in_queue_wheel(self):
        names=self.archive.namelist()
        for name in names:
            self.assertFalse(name.lower().endswith(('.dll','.exe','.ps1','.zip','.3mf','.sqlite3','.pem','.key','.pfx')))
            self.assertFalse(any(part.startswith(('test_','build_','connection_components')) for part in name.split('/')))
        self.assertIn('orca_plate_queue/queue_engine.py',names)
        self.assertIn('orca_plate_queue/plugin_page.js',names)
        for name in names:
            if not name.endswith('.py'):continue
            for private in ('C:\\Users\\Lei','C:/Users/Lei','E:\\3D\\换盘','0f0f77d3-4890','fixture-a1','BUNDLED_CONNECTION_ROOT','ConnectionComponents'):
                self.assertNotIn(private,self.archive.read(name).decode())
        self.assertIn("DEFAULT_SWAP_FILE = ''",self.archive.read('orca_plate_queue/swap_support.py').decode())

    def test_installer_has_exact_native_components_and_full_source(self):
        with zipfile.ZipFile(INSTALLER) as archive:
            prefix='Orca-Queue-Connection-'+QUEUE_VERSION+'/'
            manifest=json.loads(archive.read(prefix+'components.json'))
            self.assertEqual(set(manifest['series']),{'02.03.00','02.08.01','02.08.04'})
            for name,row in manifest['files'].items():
                data=archive.read(prefix+'bin/'+name)
                self.assertEqual(hashlib.sha256(data).hexdigest(),row['sha256']);self.assertEqual(data[:2],b'MZ')
                if row['role']=='bridge':self.assertIn(b'obn_queue_material_revision_v1\0',data)
            self.assertIn(prefix+'OrcaQueueConnectionSetup.exe',archive.namelist())
            self.assertIn(prefix+'ConnectionInstaller.cs',archive.namelist())
            self.assertIn('not a clean-room',archive.read(prefix+'NOTICE').decode())
            self.assertFalse(any(n.endswith('.ps1') for n in archive.namelist()))
            with zipfile.ZipFile(io.BytesIO(archive.read(prefix+'source-'+QUEUE_VERSION+'.zip'))) as source:
                for required in ('native/queue_bridge.cpp','native/queue_commands.inc','ConnectionInstaller.cs','build_connection_installer.py','ConnectionInstallerTests.cs','vendor/open-bamboo-b14f880.tar.gz','BUILD.txt','LICENSE'):
                    self.assertIn('orca-queue/'+required,source.namelist())

    def test_license_and_truthful_permission_declaration(self):
        self.assertIn('GNU AFFERO GENERAL PUBLIC LICENSE',self.archive.read('orca_plate_queue/LICENSE').decode())
        permissions=json.loads(self.archive.read('orca_plate_queue/permissions.json'))
        for field in ('connection_installation','other_plugin_file_modification','bundled_native_libraries','process_execution','dynamic_code_execution','environment_variable_access'):
            self.assertIs(permissions[field],False)
        self.assertIn('existing Orca-loaded bridge handle',permissions['native_calls'])

    def test_release_metadata_excludes_workstation_backup_and_queue_details(self):
        for name in ('manifest.json','validation.json'):
            path=OUT/name
            if not path.is_file():continue
            source=path.read_text(encoding='utf8')
            for private in ('C:\\\\Users\\\\Lei','C:/Users/Lei','queue-backups','"jobs":','"backup":'):
                self.assertNotIn(private,source)

    def test_modular_wheel_loads_and_rejects_installer_actions(self):
        with temporary_directory() as folder:
            root=Path(folder);self.archive.extractall(root/'wheel')
            saved=sys.modules.get('orca');host=types.ModuleType('orca')
            host.base=Base;host.plugin=lambda c:c;host.pages=types.SimpleNamespace(PagesPluginCapabilityBase=Base)
            host.LifecycleEvent=types.SimpleNamespace(GCodeExportFinished='export');host.LifecycleEvtCode=types.SimpleNamespace(Ok='ok')
            host.host=types.SimpleNamespace(plugin=types.SimpleNamespace(storage=lambda:root/'data'))
            sys.modules['orca']=host;sys.path.insert(0,str(root/'wheel'))
            try:
                module=importlib.import_module('orca_plate_queue.core')
                self.assertFalse(hasattr(module,'ConnectionComponents'))
                original=module.QueueService
                class Service(original):
                    def __init__(self,*args,**kw):super().__init__(*args,**kw,start_worker=False)
                module.QueueService=Service;page=module.PrintQueuePage();page.on_load()
                try:
                    self.assertEqual(page._error,'')
                    page._connection.snapshot=lambda:dict(available=False,devices=[],reason='offline')
                    before=page._service.snapshot()
                    for action in ('connection_install','connection_restore'):
                        page.on_message(dict(action=action));self.assertFalse(page.reply['success']);self.assertIn('独立',page.reply['note'])
                    page.on_message(dict(action='connection_status'));self.assertTrue(page.reply['success'])
                    self.assertEqual(page.reply['connection_mode'],'external');self.assertEqual(page.reply['version'],QUEUE_VERSION)
                    self.assertEqual(page._service.snapshot(),before);self.assertFalse((root/'plugins').exists())
                    self.assertIn('独立安装器',page.get_ui())
                finally:page.on_unload()
            finally:
                sys.path.remove(str(root/'wheel'))
                for name in list(sys.modules):
                    if name=='orca_plate_queue' or name.startswith('orca_plate_queue.'):sys.modules.pop(name)
                if saved is None:sys.modules.pop('orca',None)
                else:sys.modules['orca']=saved

if __name__=='__main__':unittest.main()
