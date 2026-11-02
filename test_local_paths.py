"""Long cache paths with real filesystem/SQLite, fake printing transport only."""
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import unittest
import uuid
import zipfile

from local_paths import canonical_path, fs_path, normal_path
from queue_core import inspect_plate
from queue_engine import QueueService
from queue_fleet import QueueFleet
from queue_imports import LocalImports
from page_preferences import PagePreferences
from queue_domain import blank_print_settings
from swap_support import inspect_swap_file
from test_engine import Transport

TEST_ROOT=Path(__file__).resolve().parent/'.test-temp'


class LongPathTests(unittest.TestCase):
    def setUp(self):
        TEST_ROOT.mkdir(exist_ok=True)
        self.base=TEST_ROOT/('paths-'+uuid.uuid4().hex)
        self.base.mkdir()
        self.storage=self.base/'_subscribed'/('a'*36)/('b'*36)/'v3'/'printers'/('c'*64)
        self.services=[]
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for service in self.services:service.close()
        assert canonical_path(self.base).is_relative_to(canonical_path(TEST_ROOT))
        if fs_path(self.base,force=True).exists():shutil.rmtree(fs_path(self.base,force=True))

    def make(self,path,swap=False):
        fs_path(path.parent).mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(fs_path(path),'w') as archive:
            archive.writestr('Metadata/plate_5.gcode',';start change plate\nG28 Y\n;end change plate\n' if swap else 'M624 AA==\nM625\n')
            archive.writestr('Metadata/slice_info.config','<config><plate><metadata key="index" value="5"/><metadata key="printer_model_id" value="N2S"/><metadata key="nozzle_diameters" value="0.4"/><metadata key="label_object_enabled" value="true"/><object identify_id="1419" name="part"/><filament id="9" type="PETG" color="#FFFFFF" nozzle_diameter="0.4" used_g="1"/></plate></config>')
            archive.writestr('Metadata/project_settings.config',json.dumps({'printer_model':'Bambu Lab A1','nozzle_diameter':['0.4'],'filament_type':['PETG']*9}))
        return path

    def service(self):
        transport=Transport()
        service=QueueService(self.storage,transport,inspect_plate,inspect_swap_file,'',False)
        self.services.append(service)
        return service,transport

    def test_long_swap_freeze_hash_and_reopen_without_changing_saved_identity(self):
        source=self.make(self.base/'swap.3mf',swap=True)
        service,transport=self.service()
        info=inspect_swap_file(str(source),.4);frozen=service.freeze(info)
        self.assertGreater(len(frozen['path']),300)
        self.assertFalse(frozen['path'].startswith('\\\\?\\'))
        self.assertEqual(frozen['source_path'],str(source))
        self.assertEqual(service.digest(frozen['path']),info['sha256'])
        service.commit(lambda:service.data['a1_swap'].update(frozen))
        service.close()
        reopened,_=self.service()
        saved=reopened.snapshot()['a1_swap']
        self.assertEqual(saved['path'],frozen['path'])
        self.assertEqual(inspect_swap_file(saved['path'],.4)['sha256'],info['sha256'])
        self.assertFalse(transport.requests)

    def test_long_model_source_and_cached_submission_path(self):
        source=self.make(self.storage/'中文 source'/'part.gcode.3mf')
        service,transport=self.service();info=inspect_plate(source);job=service.freeze(info)
        settings=blank_print_settings('fixture-a1');settings['mapping']={'9':'ams/0/tray/2'}
        job.update(id='long-job',status='等待',settings=settings)
        def configure():service.data.update(device_id='fixture-a1');service.data['jobs'].append(job)
        service.commit(configure)
        service.start(transport.snapshot(),True);service.tick()
        request=next(r for r in transport.requests if r['action']=='submit')
        self.assertEqual(normal_path(request['path']),Path(job['path']))
        self.assertEqual(request['sha256'],hashlib.sha256(fs_path(source).read_bytes()).hexdigest())
        if os.name=='nt':self.assertTrue(request['path'].startswith('\\\\?\\'))

    def test_long_upload_staging_and_abort(self):
        source=self.make(self.base/'source.3mf');data=source.read_bytes();seen=[]
        service,_=self.service()
        def enqueue(path,copies,**kwargs):
            seen.append(service.freeze(inspect_plate(path)));return 'staged'
        imports=LocalImports(lambda:str(self.storage),enqueue);self.addCleanup(imports.close)
        result=imports.handle('upload_begin',{'name':'中文 part.3mf','size':len(data),'copies':2})
        token=result['token']
        self.assertGreater(len(str(imports.pending[token]['path'])),260)
        imports.handle('upload_chunk',{'token':token,'seq':0,'content':base64.b64encode(data).decode()})
        self.assertTrue(imports.handle('upload_end',{'token':token})['complete'])
        self.assertEqual(len(seen),1)
        self.assertEqual(service.digest(seen[0]['path']),hashlib.sha256(data).hexdigest())
        result=imports.handle('upload_begin',{'name':'cancel.3mf','size':1})
        pending=imports.pending[result['token']]['path']
        imports.handle('upload_abort',{'token':result['token']})
        self.assertFalse(fs_path(pending).exists())

    def test_preferences_and_fleet_index_under_long_root(self):
        prefs=PagePreferences(self.storage);prefs.set_language('en')
        self.assertEqual(PagePreferences(self.storage).language,'en')
        connection=Transport();connection.watch=lambda _id:None
        def factory(*args):
            service=QueueService(*args,start_worker=False);self.services.append(service);return service
        fleet=QueueFleet(self.storage,connection,inspect_plate,inspect_swap_file,'',service_factory=factory)
        try:
            fleet.select('fixture-a1',connection.snapshot())
            self.assertEqual(json.loads(fs_path(fleet.index).read_text(encoding='utf-8'))['selected'],'fixture-a1')
        finally:fleet.close()

    def test_page_swap_import_validation_and_owned_copy_cleanup(self):
        import copy
        import types
        import test_plugin as packaged
        from test_setup import native_snapshot
        packaged.PluginTests.setUpClass()
        module=packaged.PluginTests.module
        module.orca.host=types.SimpleNamespace(plugin=types.SimpleNamespace(storage=lambda:self.storage))
        page=module.PrintQueuePage();page.on_load()
        try:
            self.assertEqual(page._error,'')
            page._connection=module.PrinterConnection(types.SimpleNamespace(queue_bridge_v1=types.SimpleNamespace(snapshot=lambda:copy.deepcopy(native_snapshot()))))
            page.on_message({'action':'bind_device','device_id':'test-a1'})
            self.assertTrue(page.reply['success'])
            swap=self.make(self.base/'swap.3mf',swap=True)
            page.on_message({'action':'save_swap','path':str(swap),'nozzle':.4,'enabled':True,'automatic':False})
            self.assertTrue(page.reply['success'],page.reply.get('note'))
            cached=page.reply['swap_settings']['path']
            self.assertGreater(len(cached),300)
            self.assertTrue(inspect_swap_file(cached,.4)['validated'])
            model=self.make(self.base/'model.3mf')
            page.on_message({'action':'add','path':str(model),'copies':1})
            self.assertTrue(page.reply['success'],page.reply.get('note'))
            draft=page.reply['data']['drafts'][0];owned=draft['path']
            self.assertTrue(fs_path(owned).is_file())
            page.on_message({'action':'discard_import','id':draft['id']})
            self.assertTrue(page.reply['success'],page.reply.get('note'))
            self.assertFalse(fs_path(owned).exists())
            self.assertTrue(model.is_file())
            self.assertTrue(fs_path(cached).is_file())
        finally:
            page.on_unload();packaged.PluginTests.tearDownClass()

    @unittest.skipUnless(os.name=='nt','Windows path syntax')
    def test_drive_unc_and_existing_extended_paths(self):
        short=Path(r'C:\cache\part.3mf')
        self.assertEqual(fs_path(short),short)
        long=Path('C:\\cache\\'+'x'*200+'\\'+'y'*50+'.3mf')
        self.assertEqual(str(fs_path(long)),'\\\\?\\'+str(long))
        self.assertEqual(normal_path(fs_path(long)),long)
        unc=Path('\\\\server\\share\\'+'x'*200+'\\'+'y'*50+'.3mf')
        self.assertEqual(str(fs_path(unc)),'\\\\?\\UNC\\'+str(unc)[2:])
        self.assertEqual(normal_path(fs_path(unc)),unc)
        self.assertEqual(fs_path(fs_path(long)),fs_path(long))

    @unittest.skipUnless(os.name=='nt','Windows UTF-16 path counting')
    def test_non_bmp_characters_are_counted_as_utf16_units(self):
        path=Path('C:\\'+'🌸'*121+'.3mf')
        self.assertLess(len(str(path)),240)
        self.assertTrue(str(fs_path(path)).startswith('\\\\?\\'))

    @unittest.skipUnless(os.name=='nt','Windows host audit paths')
    def test_short_paths_keep_the_host_private_root_spelling(self):
        for size in (239,240,243,247):
            path=Path('C:/'+'x'*(size-3))
            self.assertEqual(fs_path(path),path)
        self.assertTrue(str(fs_path(Path('C:/'+'x'*245))).startswith('\\\\?\\'))

    def test_missing_source_is_still_reported_and_not_silently_created(self):
        service,_=self.service()
        with self.assertRaises(FileNotFoundError):
            service.freeze({'path':str(self.storage/'missing.3mf'),'sha256':'0'*64})
        self.assertEqual(list(fs_path(service.assets).iterdir()),[])


if __name__=='__main__':unittest.main()
