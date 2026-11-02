"""Exercise packaged plugin with a minimal host contract, not a live printer."""
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from test_queue import temporary_directory
import test_queue
import base64
import zipfile
import copy
import uuid


class Base:
    def __init__(self):
        self.config = '{}'
        self.reply = None
        self.can_save = True
    def get_config(self): return self.config
    def save_config(self, value):
        if not self.can_save: return False
        self.config = value
        return True
    def post_message(self, value): self.reply = value


def existing_queue_fixture(page, path, copies=1, display_name=None):
    """Seed previously saved, unconfigured tasks for existing-queue regression tests."""
    info=page._service.freeze(page._service.inspect_model(path))
    if display_name:info['name']=display_name
    def change():
        if info['thumbnail']:page._data['previews'][info['sha256']]=info['thumbnail']
        for _ in range(copies):
            row=copy.deepcopy(info);row.pop('thumbnail',None)
            row.update(id=uuid.uuid4().hex,status='等待',object_count=len(info['objects']),settings=dict(
                device_id=page._data['device_id'],source='ams',mapping={},external_ready=False,
                options=dict(bed_leveling=True,flow_calibration=False,timelapse=False)))
            page._data['jobs'].append(row)
    page._commit(change)
    page.on_message(dict(action='refresh'))


class PluginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old = sys.modules.get('orca')
        host = types.ModuleType('orca')
        host.pages = types.SimpleNamespace(PagesPluginCapabilityBase=Base)
        host.base = Base
        host.plugin = lambda c: c
        host.LifecycleEvent = types.SimpleNamespace(GCodeExportFinished='export')
        host.LifecycleEvtCode = types.SimpleNamespace(Ok='ok')
        cls.registrations = []
        host.register_capability = cls.registrations.append
        sys.modules['orca'] = host
        spec = importlib.util.spec_from_file_location('packaged_queue', Path(__file__).parent/'plugin-dist/orca_plate_queue.py')
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)
        original=cls.module.QueueService
        class TestService(original):
            instances=[]
            def __init__(self,*args,**kwargs):
                super().__init__(*args,**kwargs,start_worker=False)
                self.instances.append(self)
        cls.module.QueueService=TestService

    @classmethod
    def tearDownClass(cls):
        if cls.old is None: sys.modules.pop('orca', None)
        else: sys.modules['orca'] = cls.old

    def setUp(self):
        self.folder_context=temporary_directory()
        self.folder=self.folder_context.__enter__()
        self.module.orca.host=types.SimpleNamespace(plugin=types.SimpleNamespace(storage=lambda:Path(self.folder)/'private'))
        self.page = self.module.PrintQueuePage()
        self.page.on_load()

    def tearDown(self):
        for service in self.module.QueueService.instances:service.close()
        self.module.QueueService.instances.clear()
        self.folder_context.__exit__(None,None,None)

    def test_registered_top_tab(self):
        self.module.PrintQueuePlugin().register_capabilities()
        self.assertIn(self.module.PrintQueuePage, self.registrations)
        self.assertEqual(self.page.get_name(), '打印队列')
        self.assertIn('orca.onMessage', self.page.get_ui())

    def test_add_copies_and_reload(self):
        with temporary_directory() as folder:
            path = test_queue.FileInspection().make(folder)
            existing_queue_fixture(self.page, str(path), 2)
            self.assertTrue(self.page.reply['success'])
            self.assertEqual(len(self.page.reply['data']['jobs']), 2)
            ids = [j['id'] for j in self.page.reply['data']['jobs']]
            self.assertNotEqual(ids[0], ids[1])
            self.page.on_unload()
            other = self.module.PrintQueuePage()
            other.config = self.page.config
            other.on_load()
            other.on_message(dict(action='refresh'))
            self.assertEqual(len(other.reply['data']['jobs']), 2)

    def test_save_failure_rolls_back(self):
        self.page._service._save=lambda:(_ for _ in ()).throw(OSError('disk full'))
        self.page.on_message(dict(action='auto', enabled=True))
        self.assertFalse(self.page.reply['success'])
        self.assertFalse(self.page._data['auto_export'])
        self.page._service._save=lambda:None

    def test_old_host_config_is_not_used(self):
        self.page.config='{broken old host config'
        self.page.on_message(dict(action='auto',enabled=True))
        self.assertTrue(self.page.reply['success'])
        self.assertTrue(self.page._data['auto_export'])

    def test_raw_gcode_event_not_queued(self):
        self.page.on_message(dict(action='auto', enabled=True))
        self.page.on_lifecycle_event('export', types.SimpleNamespace(code='ok', msg='working.gcode'))
        self.page.on_message(dict(action='refresh'))
        self.assertEqual(self.page.reply['data']['jobs'], [])
        self.assertTrue(self.page.reply['messages'])

    def test_duplicate_export_only_one_job(self):
        with temporary_directory() as folder:
            path = test_queue.FileInspection().make(folder)
            self.page.on_message(dict(action='auto', enabled=True))
            for _ in range(2):
                self.page.on_lifecycle_event('export', types.SimpleNamespace(code='ok', msg=str(path)))
            self.page.on_message(dict(action='refresh'))
            self.assertEqual(self.page.reply['data']['jobs'], [])
            self.assertEqual(len(self.page.reply['data']['drafts']), 1)

    def test_changed_source_rejected_on_verify(self):
        with temporary_directory() as folder:
            path = test_queue.FileInspection().make(folder)
            existing_queue_fixture(self.page, str(path), 1)
            with Path(self.page._data['jobs'][0]['path']).open('ab') as f: f.write(b'changed')
            self.page.on_message(dict(action='verify'))
            self.assertFalse(self.page.reply['success'])

    def test_delete_and_order(self):
        with temporary_directory() as folder:
            path = test_queue.FileInspection().make(folder)
            existing_queue_fixture(self.page, str(path), 2)
            ids = [j['id'] for j in self.page._data['jobs']]
            self.page.on_message(dict(action='up', id=ids[1]))
            self.assertEqual(self.page._data['jobs'][0]['id'], ids[1])
            self.page.on_message(dict(action='remove', id=ids[1]))
            self.assertEqual(len(self.page._data['jobs']), 1)

    def image_file(self, folder):
        path = test_queue.FileInspection().make(folder)
        png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a7xkAAAAASUVORK5CYII=')
        with zipfile.ZipFile(path, 'a') as z: z.writestr('Metadata/plate_1.png', png)
        return path

    def test_preview_is_shared_by_copies_and_survives_reload(self):
        with temporary_directory() as folder:
            path = self.image_file(folder)
            existing_queue_fixture(self.page, str(path), 2)
            self.assertTrue(self.page.reply['success'])
            self.assertEqual(len(self.page._data['previews']), 1)
            self.page.on_unload()
            other = self.module.PrintQueuePage()
            other.config = self.page.config
            other.on_load()
            other.on_message(dict(action='refresh'))
            self.assertEqual(len(other.reply['data']['previews']), 1)
            other.on_unload()
            self.page.on_load()
            ids = [j['id'] for j in self.page._data['jobs']]
            self.page.on_message(dict(action='remove', id=ids[0]))
            self.assertEqual(len(self.page._data['previews']), 1)
            self.page.on_message(dict(action='remove', id=ids[1]))
            self.assertEqual(self.page._data['previews'], {})



    def swap_file(self, folder, model='Bambu Lab A1', nozzle='0.4', complete=True):
        path = Path(folder) / 'swap.3mf'
        with zipfile.ZipFile(path, 'w') as z:
            z.writestr('Metadata/plate_1.gcode', ';start change plate\nG28 Y\n' + (';end change plate\n' if complete else ''))
            z.writestr('Metadata/plate_1 - backup.gcode', '; original backup\n')
            z.writestr('Metadata/project_settings.config', json.dumps(dict(printer_model=model, nozzle_diameter=[nozzle])))
        return path

    def test_default_swap_path_after_development_reset(self):
        self.page.config = json.dumps(dict(schema=1, jobs=[], auto_export=False))
        self.page.on_load()
        self.page.on_message(dict(action='refresh'))
        self.assertEqual(self.page.reply['swap_settings']['path'], self.module.DEFAULT_SWAP_FILE)
        self.assertFalse(self.page.reply['swap_settings']['validated'])

    def test_save_custom_swap_and_persist(self):
        with temporary_directory() as folder:
            path = self.swap_file(folder)
            self.page.on_message(dict(action='save_swap', path=str(path), nozzle=.4, enabled=True))
            self.assertTrue(self.page.reply['success'])
            self.assertEqual(self.page.reply['swap_settings']['gcode'], 'Metadata/plate_1.gcode')
            self.page.on_unload()
            other = self.module.PrintQueuePage()
            other.config = self.page.config
            other.on_load()
            other.on_message(dict(action='refresh'))
            self.assertTrue(other.reply['swap_settings']['validated'])
            self.assertEqual(other.reply['swap_settings']['source_path'], str(path.resolve()))

    def test_wrong_model_swap_rejected(self):
        with temporary_directory() as folder:
            p = self.swap_file(folder, model='Bambu Lab A1 mini')
            self.page.on_message(dict(action='save_swap', path=str(p), nozzle=.4))
            self.assertFalse(self.page.reply['success'])

    def test_wrong_nozzle_does_not_overwrite_setting(self):
        with temporary_directory() as folder:
            p = self.swap_file(folder, nozzle='0.6')
            old = self.page.config
            self.page.on_message(dict(action='save_swap', path=str(p), nozzle=.4))
            self.assertFalse(self.page.reply['success'])
            self.assertEqual(self.page.config, old)

    def test_incomplete_swap_rejected(self):
        with temporary_directory() as folder:
            p = self.swap_file(folder, complete=False)
            self.page.on_message(dict(action='save_swap', path=str(p), nozzle=.4))
            self.assertFalse(self.page.reply['success'])



    def test_swap_plan_between_models_only(self):
        jobs = [dict(id=str(i), status='等待') for i in range(3)]
        plan = self.module.swap_plan(jobs, {})
        self.assertEqual([(p['after_id'],p['before_id']) for p in plan], [('0','1'),('1','2')])
        self.assertEqual(self.module.swap_plan(jobs, dict(enabled=False)), [])
        self.assertEqual(self.module.swap_plan(jobs[:1], {}), [])

    def storage(self, folder):
        # Input files live in folder; plugin storage stays in its independent fixture.
        pass

    def begin_upload(self, raw, name='拖入的单盘.gcode.3mf', copies=1):
        self.page.on_message(dict(action='upload_begin', name=name, size=len(raw), copies=copies, request_id='begin'))
        self.assertTrue(self.page.reply['success'], self.page.reply)
        self.assertEqual(self.page.reply['request_id'], 'begin')
        return self.page.reply['upload']['token']

    def chunk(self, token, raw, seq=0):
        self.page.on_message(dict(action='upload_chunk',token=token,seq=seq,content=base64.b64encode(raw).decode()))

    def test_dropped_file_copied_locally_and_removed_after_last_copy(self):
        with temporary_directory() as folder:
            self.storage(folder)
            original=test_queue.FileInspection().make(folder)
            raw=original.read_bytes();token=self.begin_upload(raw, copies=2)
            self.chunk(token, raw[:100]);self.chunk(token, raw[100:], seq=1)
            self.page.on_message(dict(action='upload_end',token=token))
            self.assertTrue(self.page.reply['success'],self.page.reply)
            self.assertEqual(self.page.reply['data']['jobs'], [])
            draft=self.page._data['drafts'][0]
            existing_queue_fixture(self.page,draft['path'],draft['copies'],display_name=draft['name'])
            self.page._commit(lambda:self.page._data.update(drafts=[]))
            self.page.on_message(dict(action='refresh'))
            jobs=self.page.reply['data']['jobs'];ids=[j['id'] for j in jobs];saved=Path(jobs[0]['path'])
            self.assertEqual(saved.read_bytes(), raw)
            self.assertEqual(jobs[0]['name'],'拖入的单盘.gcode.3mf')
            self.assertEqual(saved.parent.resolve(),(Path(self.folder)/'private'/'v3'/'assets').resolve())
            self.page.on_message(dict(action='remove',id=ids[0]))
            self.assertTrue(saved.exists())
            self.page.on_message(dict(action='remove',id=ids[1]))
            self.assertFalse(saved.exists())
            self.assertEqual(original.read_bytes(),raw)

    def test_chunk_order_and_truncation_cannot_enqueue(self):
        with temporary_directory() as folder:
            self.storage(folder);token=self.begin_upload(b'abcdef')
            self.chunk(token,b'abc',seq=1)
            self.assertFalse(self.page.reply['success'])
            self.chunk(token,b'abc')
            self.page.on_message(dict(action='upload_end',token=token))
            self.assertFalse(self.page.reply['success'])
            self.assertEqual(self.page._data['jobs'],[])
            self.page.on_message(dict(action='upload_abort',token=token))
            self.assertFalse(list((Path(self.folder)/'private'/'queue_uploads').iterdir()))

    def test_invalid_slice_upload_leaves_no_task_or_copy(self):
        with temporary_directory() as folder:
            self.storage(folder);token=self.begin_upload(b'not a zip')
            self.chunk(token,b'not a zip')
            self.page.on_message(dict(action='upload_end',token=token))
            self.assertFalse(self.page.reply['success'])
            self.assertEqual(self.page._data['jobs'],[])
            self.assertFalse(list((Path(self.folder)/'private'/'queue_uploads').iterdir()))

    def test_upload_size_and_extension_bounds(self):
        for name,size in [('x.stl',100),('x.3mf',0),('x.3mf',100*1024*1024+1)]:
            self.page.on_message(dict(action='upload_begin',name=name,size=size))
            self.assertFalse(self.page.reply['success'])

    def test_save_failure_cleans_local_import(self):
        with temporary_directory() as folder:
            self.storage(folder);raw=test_queue.FileInspection().make(folder).read_bytes()
            token=self.begin_upload(raw);self.chunk(token,raw)
            self.page._service._save=lambda:(_ for _ in ()).throw(OSError('disk full'))
            self.page.on_message(dict(action='upload_end',token=token))
            self.assertFalse(self.page.reply['success'])
            self.assertEqual(self.page._data['jobs'],[])
            self.assertFalse(list((Path(self.folder)/'private'/'queue_uploads').iterdir()))
            self.page._service._save=lambda:None

    def test_unload_cleans_incomplete_upload_only(self):
        with temporary_directory() as folder:
            self.storage(folder);self.begin_upload(b'abc')
            self.page.on_unload()
            self.assertFalse(list((Path(self.folder)/'private'/'queue_uploads').iterdir()))

    def test_drag_move_after_and_before(self):
        with temporary_directory() as folder:
            path=test_queue.FileInspection().make(folder)
            existing_queue_fixture(self.page, str(path), 4)
            ids=[j['id'] for j in self.page._data['jobs']]
            self.page.on_message(dict(action='move',id=ids[0],target_id=ids[2],placement='after'))
            self.assertTrue(self.page.reply['success'])
            self.assertEqual([j['id'] for j in self.page._data['jobs']],[ids[1],ids[2],ids[0],ids[3]])
            self.page.on_message(dict(action='move',id=ids[3],target_id=ids[1],placement='before'))
            self.assertEqual([j['id'] for j in self.page._data['jobs']],[ids[3],ids[1],ids[2],ids[0]])
            self.assertEqual(self.page.reply['swap_plan'][0]['after_id'],ids[3])

    def test_drag_move_cannot_cross_running_task(self):
        self.page._data['jobs']=[dict(id=str(i),name=str(i),path='',sha256='',object_count=1,status='打印中' if i==1 else '等待') for i in range(3)]
        self.page.on_message(dict(action='move',id='0',target_id='2',placement='after'))
        self.assertFalse(self.page.reply['success'])
        self.assertEqual([j['id'] for j in self.page._data['jobs']],['0','1','2'])

    def test_stale_drag_target_rejected(self):
        self.page.on_message(dict(action='move',id='gone',target_id='gone',placement='before'))
        self.assertFalse(self.page.reply['success'])


if __name__ == '__main__': unittest.main(verbosity=2)
