"""Setup checks use explicit fixtures; no fixture devices enter the shipped plugin."""
import copy
import json
import types
import unittest
import zipfile
from pathlib import Path
import test_plugin as packaged
from test_queue import temporary_directory


def native_snapshot():
    return dict(protocol=1, origin='orca-native-queue', cloud_session_reused=True,
                devices=[dict(id='test-a1', name='测试 A1', model='N2S', online=True,
                              cloud_connected=True, nozzle=.4, age_ms=0,
                              supported_options=['bed_leveling','flow_calibration','timelapse'], slots=[
                    dict(id='unit-0/tray-2', label='AMS Lite 3', kind='ams', present=True, type='PETG', color='#EBE6E6'),
                    dict(id='unit-0/tray-3', label='AMS Lite 4', kind='ams', present=True, type='PLA', color='#FF8040'),
                    dict(id='external', label='外挂', kind='external', present=True, type='PETG', color='#EBE6E6')])])


class SetupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        packaged.PluginTests.setUpClass()
        cls.module = packaged.PluginTests.module

    @classmethod
    def tearDownClass(cls):
        packaged.PluginTests.tearDownClass()

    def setUp(self):
        self.folder_context=temporary_directory()
        self.folder=self.folder_context.__enter__()
        self.module.orca.host=types.SimpleNamespace(plugin=types.SimpleNamespace(storage=lambda:Path(self.folder)/'private'))
        self.raw = native_snapshot()
        provider = types.SimpleNamespace(snapshot=lambda: copy.deepcopy(self.raw))
        self.host = types.SimpleNamespace(queue_bridge_v1=provider)
        self.connection = self.module.PrinterConnection(self.host)
        self.asset = dict(printer='N2S', nozzle='0.4', filaments=[
            dict(id='9', type='PETG', color='#EBE6E6', nozzle='0.4')])
        self.settings = self.module.blank_print_settings('test-a1')
        self.settings['mapping'] = {'9': 'unit-0/tray-2'}

    def tearDown(self):
        for service in self.module.QueueService.instances:service.close()
        self.module.QueueService.instances.clear()
        self.folder_context.__exit__(None,None,None)

    def check(self, **kwargs):
        return self.module.validate_print_settings(self.asset, self.settings,
            self.connection.snapshot(), 'test-a1', **kwargs)

    def make(self, folder, swap=False):
        path = Path(folder) / ('swap.3mf' if swap else 'model.3mf')
        with zipfile.ZipFile(path, 'w') as z:
            z.writestr('Metadata/plate_5.gcode', ';start change plate\nG28 Y\n;end change plate\n' if swap else 'M624 AA==\nM625\n')
            z.writestr('Metadata/slice_info.config', '<config><plate><metadata key="index" value="5"/><metadata key="printer_model_id" value="N2S"/><metadata key="nozzle_diameters" value="0.4"/><object identify_id="24" name="sample"/><filament id="9" type="'+('PLA' if swap else 'PETG')+'" color="#EBE6E6" nozzle_diameter="0.4" used_g="1"/></plate></config>')
            z.writestr('Metadata/project_settings.config', json.dumps(dict(printer_model='Bambu Lab A1', nozzle_diameter=['0.4'])))
        return path

    def page(self):
        page = self.module.PrintQueuePage()
        page.on_load()
        page._connection = self.connection
        return page

    def test_object_preview_reply_is_scoped_and_cannot_choose_an_arbitrary_path(self):
        with temporary_directory() as folder:
            page=self.page()
            page.on_message(dict(action='bind_device',device_id='test-a1'))
            packaged.existing_queue_fixture(page,str(self.make(folder)),1)
            job=page._data['jobs'][0]
            before=copy.deepcopy(page._data)
            page.on_message(dict(action='object_preview',id=job['id'],queue_id='test-a1',request_id='preview',path='E:/must-not-read'))
            self.assertTrue(page.reply['success'],page.reply)
            self.assertEqual(page.reply['type'],'object_preview')
            self.assertEqual(page.reply['queue_id'],'test-a1')
            self.assertEqual(page.reply['job_id'],job['id'])
            self.assertFalse(page.reply['preview']['available'])
            self.assertEqual(page._data,before)
            page.on_message(dict(action='object_preview',id=job['id'],queue_id='wrong-printer'))
            self.assertFalse(page.reply['success'])

    def test_stock_host_has_no_fake_devices(self):
        result = self.module.PrinterConnection(types.SimpleNamespace()).snapshot()
        self.assertFalse(result['available'])
        self.assertFalse(result['can_submit'])
        self.assertEqual(result['devices'], [])

    def test_native_response_whitelist(self):
        self.raw['devices'][0]['access_code'] = 'should-not-copy'
        result = self.connection.snapshot()
        self.assertTrue(result['available'])
        self.assertNotIn('access_code', result['devices'][0])
        self.assertFalse(result['can_submit'])

    def test_bounded_task_history_is_whitelisted_and_cannot_export_credentials(self):
        d=self.raw['devices'][0];d.update(monitor_epoch='fixture-epoch',task_sequence=3.0,
            task_events=[dict(event=3.0,age_ms=10,state_reported=True,telemetry=dict(gcode_state='FINISH',subtask_name='oq_fixture',subtask_id='actual',access_code='never-copy',token='never-copy'))])
        result=self.connection.snapshot()['devices'][0]
        self.assertEqual(result['task_sequence'],3);self.assertEqual(result['monitor_epoch'],'fixture-epoch')
        self.assertEqual(result['task_events'][0]['telemetry'],dict(gcode_state='FINISH',subtask_name='oq_fixture',subtask_id='actual'))

    def test_invalid_or_oversized_history_cannot_become_completion_evidence(self):
        d=self.raw['devices'][0]
        invalid=[dict(event=1.5,age_ms=0,state_reported=True,telemetry={}),dict(event=1,age_ms=float('nan'),state_reported=True,telemetry={}),dict(event=1,age_ms=0,state_reported='true',telemetry={})]
        d['task_events']=invalid;self.assertEqual(self.connection.snapshot()['devices'][0]['task_events'],[])
        d['task_events']=[dict(event=i+1,age_ms=0,state_reported=True,telemetry={}) for i in range(33)]
        self.assertEqual(self.connection.snapshot()['devices'][0]['task_events'],[])

    def test_invalid_bridge_has_no_partial_devices(self):
        cases = [lambda r: r.update(protocol=2),
                 lambda r: r.update(cloud_session_reused=False),
                 lambda r: r['devices'].append(copy.deepcopy(r['devices'][0])),
                 lambda r: r['devices'][0].update(age_ms=float('nan')),
                 lambda r: r['devices'][0]['slots'].append(copy.deepcopy(r['devices'][0]['slots'][0]))]
        for change in cases:
            self.raw=native_snapshot();change(self.raw)
            result=self.connection.snapshot()
            self.assertFalse(result['available'])
            self.assertEqual(result['devices'],[])

    def test_source_id_nine_not_renumbered(self):
        with temporary_directory() as folder:
            info = self.module.inspect_plate(self.make(folder))
            self.assertEqual(info['filaments'][0]['id'], '9')
            self.assertEqual(info['nozzle'], '0.4')
        self.assertEqual(self.check()['mapping'], {'9': 'unit-0/tray-2'})

    def test_incomplete_or_extra_source_mapping_rejected(self):
        for mapping in ({}, {'1':'unit-0/tray-2'}, {'9':'unit-0/tray-2','1':'external'}):
            self.settings['mapping'] = mapping
            with self.assertRaises(ValueError): self.check()

    def test_external_requires_real_external_slot(self):
        self.settings.update(source='external', mapping={'9':'external'})
        self.assertEqual(self.check()['source'], 'external')
        self.settings['mapping']['9'] = 'unit-0/tray-2'
        with self.assertRaises(ValueError): self.check()

    def test_multimaterial_external_rejected(self):
        self.asset['filaments'].append(dict(id='11',type='PLA',nozzle='0.4'))
        self.settings.update(source='external',mapping={'9':'external','11':'external'})
        with self.assertRaisesRegex(ValueError, '多耗材'): self.check()

    def test_ams_mapping_keeps_noncontiguous_source_ids(self):
        self.asset['filaments'].append(dict(id='11',type='PLA',nozzle='0.4'))
        self.settings['mapping']['11'] = 'unit-0/tray-3'
        self.assertEqual(set(self.check()['mapping']), {'9','11'})

    def test_ams_material_mismatch_rejected(self):
        self.settings['mapping']['9'] = 'unit-0/tray-3'
        with self.assertRaisesRegex(ValueError, '类型'): self.check()

    def test_disappeared_or_empty_slot_rejected(self):
        self.raw['devices'][0]['slots'][0]['present'] = False
        with self.assertRaises(ValueError): self.check()
        self.raw['devices'][0]['slots'] = []
        with self.assertRaises(ValueError): self.check()

    def test_stale_offline_cloud_and_wrong_model_rejected(self):
        for update in [dict(age_ms=15001),dict(online=False),dict(cloud_connected=False),dict(model='N1')]:
            self.raw=native_snapshot();self.raw['devices'][0].update(update)
            with self.assertRaises(ValueError):self.check()

    def test_nozzle_mismatch_and_nan_rejected(self):
        for value in ('0.6', '', 'nan'):
            self.asset['nozzle'] = value
            with self.assertRaises(ValueError): self.check()
        self.asset['nozzle'] = '0.4'
        self.asset['filaments'][0]['nozzle'] = 'nan'
        with self.assertRaises(ValueError): self.check()

    def test_print_options_must_be_boolean(self):
        self.settings['options']['timelapse'] = 'false'
        with self.assertRaises(ValueError): self.check()

    def test_unsupported_print_option_rejected(self):
        self.raw['devices'][0]['supported_options'] = []
        with self.assertRaisesRegex(ValueError, '不支持'): self.check()

    def test_browser_cannot_inject_arbitrary_submit_parameters(self):
        self.settings['start_gcode'] = 'G28'
        self.assertNotIn('start_gcode', self.check())

    def test_readable_catalog_never_enables_unimplemented_send(self):
        self.check()
        with self.assertRaisesRegex(ValueError, '发送'): self.check(require_send=True)

    def test_old_schema_is_reset_without_migration(self):
        page = self.page()
        page.config = json.dumps(dict(schema=1,jobs=[dict(name='old')],a1_swap=dict(path='old')))
        page.on_load()
        self.assertEqual(page._data['schema'], 3)
        self.assertEqual(page._data['jobs'], [])
        self.assertEqual(page._data['device_id'], '')
        self.assertEqual(json.loads(page.config)['schema'], 1)

    def test_fabricated_device_cannot_bind(self):
        page = self.page()
        page.on_message(dict(action='bind_device',device_id='invented'))
        self.assertFalse(page.reply['success'])
        self.assertEqual(page._data['device_id'], '')

    def test_per_copy_settings_are_independent_and_persist(self):
        with temporary_directory() as folder:
            page = self.page()
            page.on_message(dict(action='bind_device',device_id='test-a1'))
            packaged.existing_queue_fixture(page, str(self.make(folder)), 2)
            first, second = page._data['jobs']
            page.on_message(dict(action='save_settings',id=first['id'],settings=self.settings))
            self.assertTrue(page.reply['success'], page.reply)
            self.assertEqual(first['settings']['mapping'], self.settings['mapping'])
            self.assertEqual(second['settings']['mapping'], {})
            page.on_load();page._connection = self.connection
            self.assertEqual(page._data['jobs'][0]['settings']['mapping'], self.settings['mapping'])

    def test_selecting_another_device_keeps_original_queue_and_material_maps(self):
        page = self.page()
        page.on_message(dict(action='bind_device',device_id='test-a1'))
        page._data['jobs'] = [dict(id='one',status='等待',settings=copy.deepcopy(self.settings),**self.asset)]
        page._data['a1_swap']['settings'] = copy.deepcopy(self.settings)
        second = copy.deepcopy(self.raw['devices'][0]);second['id'] = 'test-a1-second'
        self.raw['devices'].append(second)
        page.on_message(dict(action='bind_device',device_id=second['id']))
        self.assertTrue(page.reply['success'],page.reply)
        self.assertEqual(page._data['jobs'], [])
        self.assertEqual(page._data['a1_swap']['settings']['mapping'], {})
        page.on_message(dict(action='select_queue',device_id='test-a1'))
        self.assertTrue(page.reply['success'],page.reply)
        self.assertEqual(page._data['jobs'][0]['settings']['mapping'],self.settings['mapping'])
        self.assertEqual(page._data['a1_swap']['settings']['mapping'],self.settings['mapping'])

    def test_save_settings_rechecks_latest_slot_and_rolls_back(self):
        with temporary_directory() as folder:
            page = self.page()
            page.on_message(dict(action='bind_device',device_id='test-a1'))
            packaged.existing_queue_fixture(page, str(self.make(folder)), 1)
            row = page._data['jobs'][0]
            before = page.config
            self.raw['devices'][0]['slots'][0]['type'] = 'PLA'
            page.on_message(dict(action='save_settings',id=row['id'],settings=self.settings))
            self.assertFalse(page.reply['success'])
            self.assertEqual(page.config,before)

    def test_swap_mapping_independent_and_material_checked(self):
        with temporary_directory() as folder:
            page = self.page()
            page.on_message(dict(action='bind_device',device_id='test-a1'))
            path=self.make(folder,swap=True)
            page.on_message(dict(action='save_swap',path=str(path),nozzle=.4))
            page.on_message(dict(action='save_settings',id='__swap__',settings=self.settings))
            self.assertFalse(page.reply['success'])
            good = copy.deepcopy(self.settings);good['mapping']['9'] = 'unit-0/tray-3'
            page.on_message(dict(action='save_settings',id='__swap__',settings=good))
            self.assertTrue(page.reply['success'],page.reply)
            page.on_message(dict(action='save_swap',path=str(path),nozzle=.4))
            self.assertEqual(page._data['a1_swap']['settings']['mapping'], good['mapping'])

    def test_preflight_detects_modified_private_copy(self):
        with temporary_directory() as folder:
            page = self.page();path = self.make(folder)
            page.on_message(dict(action='bind_device',device_id='test-a1'))
            packaged.existing_queue_fixture(page, str(path), 1)
            page.on_message(dict(action='save_settings',id=page._data['jobs'][0]['id'],settings=self.settings))
            snapshot=dict(self.connection.snapshot(),can_submit=True)
            page._connection=types.SimpleNamespace(snapshot=lambda:snapshot)
            page.on_message(dict(action='preflight'))
            self.assertTrue(page.reply['success'],page.reply)
            saved=Path(page._data['jobs'][0]['path'])
            saved.write_bytes(saved.read_bytes()+b'changed')
            page.on_message(dict(action='preflight'))
            self.assertFalse(page.reply['success'])

    def test_draft_mapping_saves_without_filament_but_print_preflight_still_blocks(self):
        self.settings.update(source='external', mapping={'9':'external'})
        self.raw['devices'][0]['slots'][2]['present']=False
        draft=self.check(require_ready=False)
        self.assertEqual(draft['mapping'],{'9':'external'})
        self.raw['can_submit']=True
        with self.assertRaisesRegex(ValueError,'无料'):
            self.check(require_send=True,require_ready=False)

    def test_saved_configuration_remains_visible_while_device_is_offline(self):
        self.raw['devices'][0]['online']=False
        report=self.module.setup_report(self.asset,self.settings,self.connection.snapshot(),'test-a1')
        self.assertTrue(report['configured'])
        self.assertFalse(report['ready'])

    def test_start_preflight_checks_machine_idle_before_submitting(self):
        page=self.page()
        page.on_message(dict(action='bind_device',device_id='test-a1'))
        self.raw['can_submit']=True
        self.raw['devices'][0].update(state_age_ms=0,telemetry=dict(gcode_state='RUNNING',print_error=0))
        page.on_message(dict(action='preflight',for_start=True))
        self.assertFalse(page.reply['success'])
        self.assertIn('空闲',page.reply['note'])
        self.assertEqual(page._data['journal'],[])

    def test_bulk_save_is_explicit_and_keeps_each_copy_independent(self):
        with temporary_directory() as folder:
            page=self.page();page.on_message(dict(action='bind_device',device_id='test-a1'))
            packaged.existing_queue_fixture(page, str(self.make(folder)), 3)
            a,b,c=page._data['jobs']
            settings=copy.deepcopy(self.settings);settings.update(source='external',mapping={'9':'external'})
            self.raw['devices'][0]['slots'][2]['present']=False
            page.on_message(dict(action='save_settings',id=a['id'],settings=settings,apply_to=[b['id']]))
            self.assertTrue(page.reply['success'],page.reply)
            self.assertEqual(a['settings']['mapping'],b['settings']['mapping'])
            self.assertEqual(c['settings']['mapping'],{})
            self.assertIsNot(a['settings']['mapping'],b['settings']['mapping'])
            self.assertFalse(page.reply['setup'][a['id']]['ready'])
            self.assertTrue(page.reply['setup'][a['id']]['configured'])
            page._connection=types.SimpleNamespace(snapshot=lambda:dict(self.connection.snapshot(),can_submit=True))
            page.on_message(dict(action='preflight'))
            self.assertFalse(page.reply['success'])
            self.assertEqual(page._data['journal'],[])

    def test_bulk_save_rejects_changed_targets_without_partial_writes(self):
        with temporary_directory() as folder:
            page=self.page();page.on_message(dict(action='bind_device',device_id='test-a1'))
            packaged.existing_queue_fixture(page, str(self.make(folder)), 3)
            a,b,c=page._data['jobs'];c['filaments']=copy.deepcopy(c['filaments']);c['filaments'][0]['color']='#FF0000'
            page.on_message(dict(action='save_settings',id=a['id'],settings=self.settings,apply_to=[b['id'],c['id']]))
            self.assertFalse(page.reply['success'])
            self.assertTrue(all(j['settings']['mapping']=={} for j in page._data['jobs']))
            page.on_message(dict(action='save_settings',id=a['id'],settings=self.settings,apply_to=[b['id'],b['id']]))
            self.assertFalse(page.reply['success'])

    def test_backup_groups_are_captured_and_bulk_saved_by_packaged_runtime(self):
        self.raw['devices'][0]['slots'].append(dict(self.raw['devices'][0]['slots'][0],id='unit-0/tray-1',label='AMS Lite 2'))
        with temporary_directory() as folder:
            page=self.page();page.on_message(dict(action='bind_device',device_id='test-a1'))
            packaged.existing_queue_fixture(page, str(self.make(folder)), 2)
            a,b=page._data['jobs']
            draft=copy.deepcopy(self.settings)
            draft['refill']={'9':dict(slots=['unit-0/tray-1'],type='PLA',color='000000FF')}
            page.on_message(dict(action='save_settings',id=a['id'],settings=draft,apply_to=[b['id']]))
            self.assertTrue(page.reply['success'],page.reply)
            self.assertEqual(a['settings']['refill']['9']['color'],'EBE6E6FF')
            self.assertEqual(a['settings']['refill'],b['settings']['refill'])
            self.assertIsNot(a['settings']['refill'],b['settings']['refill'])
            self.raw['devices'][0]['slots'][0].update(present=False,type='',color='')
            page.on_message(dict(action='refresh'))
            self.assertTrue(page.reply['setup'][a['id']]['ready'])
            self.assertEqual(page.reply['setup'][a['id']]['resolved_mapping']['9'],'unit-0/tray-1')

    def test_changed_swap_archive_invalidates_mapping_and_mode_save_is_atomic(self):
        with temporary_directory() as folder:
            page=self.page();page.on_message(dict(action='bind_device',device_id='test-a1'))
            path=self.make(folder,swap=True)
            page.on_message(dict(action='save_swap',path=str(path),nozzle=.4))
            good=copy.deepcopy(self.settings);good['mapping']['9']='unit-0/tray-3'
            page.on_message(dict(action='save_settings',id='__swap__',settings=good))
            page.on_message(dict(action='save_swap',path=str(path),nozzle=.4,automatic=True))
            self.assertTrue(page.reply['success'])
            self.assertEqual(page._data['a1_swap']['settings']['mapping'],good['mapping'])
            self.assertTrue(page._data['auto_after_swap'])
            with zipfile.ZipFile(path,'a') as z:z.writestr('changed.txt','new content')
            page.on_message(dict(action='save_swap',path=str(path),nozzle=.4,automatic=False))
            self.assertTrue(page.reply['success'])
            self.assertEqual(page._data['a1_swap']['settings']['mapping'],{})
            self.assertFalse(page._data['auto_after_swap'])

    def staged(self, page, path, copies=1):
        page.on_message(dict(action='bind_device',device_id='test-a1'))
        page.on_message(dict(action='add',path=str(path),copies=copies))
        self.assertTrue(page.reply['success'],page.reply)
        return page._data['drafts'][-1]

    def add_second_printer(self):
        second=copy.deepcopy(self.raw['devices'][0]);second.update(id='test-p1',name='测试 P1S',model='C12')
        second['supported_options']=['bed_leveling','timelapse']
        self.raw['devices'].append(second)
        return second

    def test_fleet_rejects_old_page_actions_after_switching_printer(self):
        page=self.page();self.add_second_printer()
        page.on_message(dict(action='bind_device',device_id='test-a1'))
        page.on_message(dict(action='select_queue',device_id='test-p1',queue_id='test-a1'))
        self.assertTrue(page.reply['success'],page.reply)
        self.assertEqual(page.reply['queue_id'],'test-p1')
        for action in ('auto','start','remove','commit_import','stop_queue'):
            page.on_message(dict(action=action,queue_id='test-a1',enabled=True))
            self.assertFalse(page.reply['success'])
            self.assertIn('切换打印机',page.reply['note'])
        self.assertFalse(page._data['auto_export'])
        self.assertEqual(page._data['journal'],[])

    def test_fleet_drafts_and_files_remain_with_the_machine_selected_at_import(self):
        with temporary_directory() as folder:
            page=self.page();self.add_second_printer();draft=self.staged(page,self.make(folder))
            page.on_message(dict(action='select_queue',device_id='test-p1'))
            self.assertEqual(page._data.get('drafts',[]),[])
            self.assertEqual(page._data['plate_mode'],'manual')
            page.on_message(dict(action='commit_import',id=draft['id'],settings=self.settings))
            self.assertFalse(page.reply['success'])
            page.on_message(dict(action='select_queue',device_id='test-a1'))
            self.assertEqual(page._data['drafts'][0]['id'],draft['id'])
            self.assertEqual(len(page.reply['fleet']),2)

    def test_other_models_cannot_enable_automatic_swap_or_use_a1_default(self):
        page=self.page();self.add_second_printer()
        page.on_message(dict(action='bind_device',device_id='test-p1'))
        for request in (dict(action='save_swap',plate_mode='automatic'),dict(action='default_swap',plate_mode='automatic')):
            page.on_message(request)
            self.assertFalse(page.reply['success'])
            self.assertIn('没有自动换盘',page.reply['note'])
        page.on_message(dict(action='save_swap',plate_mode='manual'))
        self.assertTrue(page.reply['success'],page.reply)
        self.assertEqual(page._data['plate_mode'],'manual')

    def test_fleet_export_notification_is_pinned_to_its_original_machine(self):
        with temporary_directory() as folder:
            page=self.page();self.add_second_printer();path=self.make(folder)
            page.on_message(dict(action='bind_device',device_id='test-a1'))
            page.on_message(dict(action='auto',enabled=True))
            page.on_lifecycle_event('export',types.SimpleNamespace(code='ok',msg=str(path)))
            page.on_message(dict(action='select_queue',device_id='test-p1'))
            self.assertTrue(page.reply['success'],page.reply)
            self.assertEqual(page._data.get('drafts',[]),[])
            self.assertEqual(len(page._fleet.services['test-a1'].data['drafts']),1)

    def test_fleet_switch_is_rejected_while_a_file_is_still_transferring(self):
        page=self.page();self.add_second_printer()
        page.on_message(dict(action='bind_device',device_id='test-a1'))
        page.on_message(dict(action='upload_begin',name='pending.3mf',size=10))
        token=page.reply['upload']['token']
        page.on_message(dict(action='select_queue',device_id='test-p1'))
        self.assertFalse(page.reply['success'])
        self.assertEqual(page._data['device_id'],'test-a1')
        page.on_message(dict(action='upload_abort',token=token))
        self.assertTrue(page.reply['success'],page.reply)

    def test_fleet_selected_printer_and_both_queues_survive_page_reload(self):
        page=self.page();self.add_second_printer()
        page.on_message(dict(action='bind_device',device_id='test-a1'))
        page.on_message(dict(action='select_queue',device_id='test-p1'))
        page.on_load();page._connection=self.connection
        page.on_message(dict(action='refresh'))
        self.assertTrue(page.reply['success'],page.reply)
        self.assertEqual(page.reply['queue_id'],'test-p1')
        self.assertEqual({r['id'] for r in page.reply['fleet']},{'test-a1','test-p1'})

    def test_import_stays_out_of_queue_until_material_configuration_is_confirmed(self):
        with temporary_directory() as folder:
            page=self.page();draft=self.staged(page,self.make(folder),copies=2)
            self.assertEqual(page.reply['data']['jobs'],[])
            self.assertEqual(draft['copies'],2)
            self.assertEqual(draft['object_count'],len(draft['objects']))
            self.assertEqual(page.reply['swap_plan'],[])
            page.on_message(dict(action='commit_import',id=draft['id'],settings=self.settings))
            self.assertTrue(page.reply['success'],page.reply)
            a,b=page._data['jobs']
            self.assertNotEqual(a['id'],b['id'])
            self.assertEqual(a['settings']['mapping'],self.settings['mapping'])
            self.assertEqual(a['object_count'],len(a['objects']))
            self.assertIsNot(a['settings'],b['settings'])
            self.assertEqual(page._data['drafts'],[])
            self.assertFalse(page._data['running'])
            self.assertEqual(page._data['journal'],[])
            self.raw['can_submit']=True
            _,resolved=page._service._asset(a,self.connection.snapshot())
            self.assertEqual(resolved['mapping'],self.settings['mapping'])
            page.on_message(dict(action='commit_import',id=draft['id'],settings=self.settings))
            self.assertFalse(page.reply['success'])
            self.assertEqual(len(page._data['jobs']),2)

    def test_import_invalid_materials_or_offline_device_never_adds_task(self):
        with temporary_directory() as folder:
            page=self.page();draft=self.staged(page,self.make(folder))
            for settings in (None, self.module.blank_print_settings('test-a1')):
                page.on_message(dict(action='commit_import',id=draft['id'],settings=settings))
                self.assertFalse(page.reply['success'])
                self.assertEqual(page._data['jobs'],[])
                self.assertEqual(len(page._data['drafts']),1)
            self.raw['devices'][0]['online']=False
            page.on_message(dict(action='commit_import',id=draft['id'],settings=self.settings))
            self.assertFalse(page.reply['success'])
            self.assertEqual(page._data['jobs'],[])

    def test_import_quantity_override_creates_exact_number_of_independent_jobs(self):
        with temporary_directory() as folder:
            page=self.page();draft=self.staged(page,self.make(folder),copies=1)
            page.on_message(dict(action='commit_import',id=draft['id'],copies=4,settings=self.settings))
            self.assertTrue(page.reply['success'],page.reply)
            jobs=page._data['jobs']
            self.assertEqual(len(jobs),4)
            self.assertEqual(len({j['id'] for j in jobs}),4)
            self.assertEqual(len({id(j['settings']) for j in jobs}),4)
            self.assertEqual(page._data['drafts'],[])
            self.assertEqual(page._data['journal'],[])

    def test_invalid_import_quantity_leaves_queue_and_stored_draft_unchanged(self):
        with temporary_directory() as folder:
            page=self.page();draft=self.staged(page,self.make(folder),copies=2)
            for value in (0,101,-1,1.5,True,'3',None):
                page.on_message(dict(action='commit_import',id=draft['id'],copies=value,settings=self.settings))
                self.assertFalse(page.reply['success'],page.reply)
                self.assertEqual(page._data['jobs'],[])
                self.assertEqual(page._data['drafts'][0]['copies'],2)

    def test_bulk_import_quantity_override_changes_only_the_current_file(self):
        with temporary_directory() as folder:
            page=self.page();path=self.make(folder);a=self.staged(page,path,1);b=self.staged(page,path,2)
            page.on_message(dict(action='commit_import',id=a['id'],copies=4,settings=self.settings,apply_to=[b['id']]))
            self.assertTrue(page.reply['success'],page.reply)
            self.assertEqual(len(page._data['jobs']),6)

    def test_import_draft_survives_reload_and_cancellation_preserves_original(self):
        with temporary_directory() as folder:
            page=self.page();path=self.make(folder);original=path.read_bytes()
            draft=self.staged(page,path);cached=Path(draft['path'])
            page.on_load();page._connection=self.connection
            self.assertEqual(page._data['drafts'][0]['id'],draft['id'])
            page.on_message(dict(action='discard_import',id=draft['id']))
            self.assertTrue(page.reply['success'],page.reply)
            self.assertEqual(page._data['drafts'],[])
            self.assertEqual(page._data['jobs'],[])
            self.assertFalse(cached.exists())
            self.assertEqual(path.read_bytes(),original)

    def test_import_cancellation_keeps_shared_assets_for_remaining_draft(self):
        with temporary_directory() as folder:
            page=self.page();path=self.make(folder);a=self.staged(page,path);b=self.staged(page,path)
            page.on_message(dict(action='discard_import',id=a['id']))
            self.assertTrue(Path(b['path']).exists())
            page.on_message(dict(action='commit_import',id=b['id'],settings=self.settings))
            self.assertTrue(page.reply['success'],page.reply)

    def test_bulk_import_is_atomic_and_keeps_configured_copies_independent(self):
        with temporary_directory() as folder:
            page=self.page();path=self.make(folder);a=self.staged(page,path,2);b=self.staged(page,path,3)
            page.on_message(dict(action='commit_import',id=a['id'],settings=self.settings,apply_to=[b['id']]))
            self.assertTrue(page.reply['success'],page.reply)
            self.assertEqual(len(page._data['jobs']),5)
            self.assertEqual(page._data['drafts'],[])
            self.assertEqual(len({id(j['settings']) for j in page._data['jobs']}),5)

    def test_bulk_import_rejects_changed_materials_without_partial_jobs(self):
        with temporary_directory() as folder:
            page=self.page();path=self.make(folder);a=self.staged(page,path);b=self.staged(page,path)
            b['filaments']=copy.deepcopy(b['filaments']);b['filaments'][0]['color']='#000000'
            page.on_message(dict(action='commit_import',id=a['id'],settings=self.settings,apply_to=[b['id']]))
            self.assertFalse(page.reply['success'])
            self.assertEqual(page._data['jobs'],[])
            self.assertEqual(len(page._data['drafts']),2)

    def test_import_changed_copy_and_save_failure_never_add_partial_jobs(self):
        with temporary_directory() as folder:
            page=self.page();draft=self.staged(page,self.make(folder),2)
            cached=Path(draft['path']);raw=cached.read_bytes();cached.write_bytes(raw+b'changed')
            page.on_message(dict(action='commit_import',id=draft['id'],settings=self.settings))
            self.assertFalse(page.reply['success'])
            self.assertEqual(page._data['jobs'],[])
            cached.write_bytes(raw);save=page._service._save
            page._service._save=lambda:(_ for _ in ()).throw(OSError('disk full'))
            page.on_message(dict(action='commit_import',id=draft['id'],settings=self.settings))
            page._service._save=save
            self.assertFalse(page.reply['success'])
            self.assertEqual(page._data['jobs'],[])
            self.assertEqual(len(page._data['drafts']),1)

    def test_upload_enters_same_configuration_gate_and_keeps_original_name(self):
        import base64
        with temporary_directory() as folder:
            page=self.page();page.on_message(dict(action='bind_device',device_id='test-a1'))
            raw=self.make(folder).read_bytes()
            page.on_message(dict(action='upload_begin',name='拖入测试.3mf',size=len(raw),copies=2))
            token=page.reply['upload']['token']
            page.on_message(dict(action='upload_chunk',token=token,seq=0,content=base64.b64encode(raw).decode()))
            page.on_message(dict(action='upload_end',token=token))
            self.assertTrue(page.reply['success'],page.reply)
            self.assertEqual(page._data['jobs'],[])
            draft=page._data['drafts'][0]
            self.assertEqual(draft['name'],'拖入测试.3mf')
            self.assertFalse(list((Path(page._storage)/'queue_uploads').iterdir()))
            page.on_message(dict(action='commit_import',id=draft['id'],settings=self.settings))
            self.assertTrue(page.reply['success'],page.reply)
            self.assertEqual([j['name'] for j in page._data['jobs']],['拖入测试.3mf']*2)


if __name__ == '__main__':
    unittest.main()
