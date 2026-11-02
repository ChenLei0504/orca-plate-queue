"""Machine-boundary tests use a local fake transport, never a real printer."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from queue_engine import QueueService
from queue_domain import blank_print_settings, configure_print_settings


class Transport:
    def __init__(self):
        self.requests=[]
        self.value=dict(available=True,can_submit=True,commands=[],devices=[dict(id='fixture-a1',name='A1',model='N2S',
            online=True,cloud_connected=True,nozzle=.4,age_ms=0,state_age_ms=0,state_event=1,
            supported_options=['bed_leveling','flow_calibration','timelapse'],
            slots=[dict(id='ams/0/tray/2',kind='ams',present=True,type='PETG',color='#ffffff'),dict(id='external',kind='external',present=True,type='PETG',color='#ffffff')],
            telemetry=dict(gcode_state='IDLE',print_error=0,s_obj=[]))])
    @property
    def device(self):return self.value['devices'][0]
    def snapshot(self):return copy.deepcopy(self.value)
    def command(self,request):
        self.requests.append(copy.deepcopy(request))
        self.value['commands'].append(dict(request_id=request['request_id'],action=request['action'],status='sent',code=0))
        return 0


class EngineTest(unittest.TestCase):
    def setUp(self):
        base=Path(__file__).resolve().parent/'test-temp'
        base.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=base);self.root=Path(self.temp.name)
        self.transport=Transport();self.now=1000.;self.services=[]
        def inspect(path,*args):
            p=Path(path)
            return dict(path=str(p),name=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),plate='5',
                printer='N2S',nozzle=.4,filament_count=10,filaments=[dict(id='9',type='PETG',nozzle='.4')],
                objects=[dict(id='1419',name='one'),dict(id='1420',name='two')],object_count=2,label_markers=True,
                duration_s=1,thumbnail='')
        self.inspect=inspect
        def swap(path,nozzle=.4):
            return dict(inspect(path),plate='1',motion_only=True,filament_count=1,validated=True)
        self.swap=swap
        self.s=self.service()
        self.s.data['device_id']='fixture-a1'
        path=self.root/'swap.3mf';path.write_bytes(b'swap fixture')
        swap_asset=self.s.freeze(swap(path));swap_asset.update(settings=blank_print_settings('fixture-a1'),enabled=True)
        self.s.data['a1_swap']=swap_asset;self.s._save()
    def service(self):
        s=QueueService(self.root/'queue',self.transport,self.inspect,self.swap,'default',False,clock=lambda:self.now)
        self.services.append(s);return s
    def tearDown(self):
        for s in self.services:s.close()
        assert self.root.resolve().is_relative_to(Path(__file__).resolve().parent/'test-temp')
        self.temp.cleanup()
    def add(self,**extra):
        path=self.root/(str(len(self.s.data['jobs']))+'.3mf');path.write_bytes(b'fixture'+str(len(self.s.data['jobs'])).encode())
        asset=self.s.freeze(self.inspect(path));settings=blank_print_settings('fixture-a1');settings['mapping']={'9':'ams/0/tray/2'}
        asset.update(id=str(len(self.s.data['jobs'])),status='等待',settings=settings,**extra)
        self.s.commit(lambda:self.s.data['jobs'].append(asset));return asset
    def begin(self,count=1):
        for _ in range(count):self.add()
        self.s.start(self.transport.snapshot(),True);self.s.tick();return self.s.data['active']
    def status(self,state,tag=None,identity='job1'):
        a=self.s.data['active'];d=self.transport.device;d['state_event']+=1
        d['telemetry'].update(gcode_state=state,subtask_name=tag or a['tag'],subtask_id=identity,gcode_start_time='123')
        self.s.tick()
    def finish(self):self.status('RUNNING');self.status('FINISH')

    def test_unicode_storage_and_source_paths_survive_reopen_and_locking(self):
        storage=self.root/'中文 用户 [测试]'/'打印队列'
        source=self.root/'樱花 冰蓝 🌸.3mf';source.write_bytes(b'unicode fixture')
        service=QueueService(storage,self.transport,self.inspect,self.swap,'',False)
        self.services.append(service)
        asset=service.freeze(self.inspect(source))
        asset.update(id='unicode-job',status='等待',settings=blank_print_settings('fixture-a1'))
        service.commit(lambda:service.data['jobs'].append(asset))
        if os.name=='nt':
            with self.assertRaisesRegex(ValueError,'另一个 Orca'):
                QueueService(storage,self.transport,self.inspect,self.swap,'',False)
        service.close()
        reopened=QueueService(storage,self.transport,self.inspect,self.swap,'',False)
        self.services.append(reopened)
        job=reopened.snapshot()['jobs'][0]
        self.assertEqual(job['name'],source.name)
        self.assertEqual(Path(job['path']).read_bytes(),b'unicode fixture')
        self.assertEqual(source.read_bytes(),b'unicode fixture')
        self.assertFalse(self.transport.requests)

    def test_object_preview_is_read_only_cached_and_rechecks_file_hash(self):
        job=self.add()
        before=self.s.snapshot()
        result=self.s.object_preview(job['id'])
        self.assertFalse(result['available'])
        result['note']='changed outside cache'
        self.assertNotEqual(self.s.object_preview(job['id'])['note'],result['note'])
        self.assertEqual(self.s.snapshot(),before)
        self.assertFalse(self.transport.requests)
        Path(job['path']).write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError,'校验失败'):
            self.s.object_preview(job['id'])

    def test_sparse_mapping_preserves_source_id9(self):
        self.begin();r=self.transport.requests[-1]
        self.assertEqual(r['ams_mapping'],[-1]*8+[2,-1]);self.assertEqual(r['plate'],5)
        self.assertTrue(r['use_ams'])
        self.assertEqual(len(r['ams_mapping_info']),10)
        self.assertEqual(r['ams_mapping_info'][8]['ams'],2)
        self.assertEqual(r['ams_mapping_info'][8]['filamentType'],'PETG')
        self.assertEqual(r['ams_mapping_info'][0],dict(ams=-1,targetColor='',filamentId='',filamentType=''))
        self.assertEqual(self.s.data['journal'][-1]['materials']['ams_mapping_info'],r['ams_mapping_info'])

    def test_material_details_use_fresh_source_profile_and_actual_tray_color(self):
        inspect=self.s.inspect_model
        def enriched(path):
            result=inspect(path);result['filaments'][0].update(color='#ebe6e6',profile_id='GFG99',nozzle_id=1)
            return result
        self.s.inspect_model=enriched
        self.transport.device['slots'][0]['color']='#12345678'
        self.begin();row=self.transport.requests[-1]['ams_mapping_info'][8]
        self.assertEqual(row,dict(ams=2,targetColor='12345678',sourceColor='EBE6E6FF',filamentId='GFG99',filamentType='PETG',nozzleId=1))

    def test_external_spool_has_no_ams_slots_in_any_mapping(self):
        job=self.add();job['settings'].update(source='external',mapping={'9':'external'})
        self.s.start(self.transport.snapshot(),True);self.s.tick();request=self.transport.requests[-1]
        self.assertFalse(request['use_ams'])
        self.assertEqual(request['ams_mapping'],[-1]*10)
        self.assertTrue(all(row['ams']==-1 for row in request['ams_mapping_info']))

    def refill_jobs(self):
        primary=self.transport.device['slots'][0]
        backup=dict(primary,id='ams/0/tray/0',label='AMS 1 / 1')
        self.transport.device['slots'].append(backup)
        jobs=[self.add(),self.add()]
        for job in jobs:
            draft=copy.deepcopy(job['settings']);draft['refill']={'9':dict(slots=[backup['id']])}
            job['settings']=configure_print_settings(job,draft,self.transport.snapshot(),'fixture-a1')
        self.s.data['auto_after_swap']=True
        return jobs,primary,backup

    def test_refill_after_swap_uses_fresh_backup_mapping_in_real_submit_boundary(self):
        jobs,primary,backup=self.refill_jobs()
        self.s.start(self.transport.snapshot(),True);self.s.tick()
        self.assertEqual(self.transport.requests[-1]['ams_mapping'],[-1]*8+[2,-1])
        self.status('RUNNING');primary.update(present=False,type='',color='');self.status('FINISH')
        self.s.tick();self.assertEqual(self.s.data['active']['kind'],'swap')
        self.finish();self.s.tick()
        self.assertEqual(self.transport.requests[-1]['ams_mapping'],[-1]*8+[0,-1])
        self.assertEqual(self.transport.requests[-1]['ams_mapping_info'][8]['ams'],0)
        self.assertEqual(jobs[1]['settings']['mapping']['9'],'ams/0/tray/2')
        self.assertEqual(jobs[1]['last_mapping']['9'],backup['id'])
        self.assertEqual(self.s.data['active']['mapping'],jobs[1]['last_mapping'])
        self.assertTrue(any('跨盘续料' in event for event in self.s.data['events']))
        self.s.close();reloaded=self.service()
        self.assertEqual(reloaded.data['jobs'][1]['last_mapping']['9'],backup['id'])
        self.assertEqual(reloaded.data['jobs'][1]['settings']['refill']['9']['color'],'FFFFFFFF')

    def test_preflight_does_not_cache_mapping_for_dispatch(self):
        jobs,primary,backup=self.refill_jobs()
        self.s.start(self.transport.snapshot(),True)
        primary['present']=False
        self.s.tick()
        self.assertEqual(self.transport.requests[-1]['ams_mapping'][8],0)

    def test_empty_or_changed_backup_after_swap_blocks_next_model(self):
        jobs,primary,backup=self.refill_jobs()
        self.s.start(self.transport.snapshot(),True);self.s.tick();self.finish()
        self.s.tick();self.finish()
        primary.update(present=False,type='',color='');backup['color']='#000000'
        with self.assertRaisesRegex(ValueError,'均无可用'):self.s.tick()
        self.assertEqual(len(self.transport.requests),2)
        self.assertIsNone(self.s.data['active'])
        self.assertEqual(jobs[1]['status'],'等待')
    def test_send_receipt_never_means_physical_completion(self):
        self.begin(2);self.s.tick();self.assertEqual(len(self.transport.requests),1)
        self.assertEqual(self.s.data['jobs'][0]['status'],'发送中')
    def test_last_plate_stays(self):
        self.begin();self.finish();self.s.tick()
        self.assertEqual(self.s.data['phase'],'completed');self.assertEqual(len(self.transport.requests),1)
        self.assertTrue(self.s.data['dirty_plate'])
    def test_two_models_have_exactly_one_independent_swap(self):
        self.begin(2);self.finish();self.s.tick();self.assertEqual(self.s.data['active']['kind'],'swap')
        swap_request=self.transport.requests[-1];self.assertFalse(swap_request['use_ams']);self.assertFalse(any(swap_request['options'].values()))
        self.finish();self.assertEqual(self.s.data['phase'],'confirm_plate');self.assertEqual(len(self.transport.requests),2)
        self.s.confirm_plate(self.transport.snapshot());self.s.tick();self.finish()
        self.assertEqual(self.s.data['phase'],'completed');self.assertEqual(len(self.transport.requests),3)
    def test_opt_in_automatic_after_program_completion(self):
        self.s.data['auto_after_swap']=True;self.begin(2);self.finish();self.s.tick();self.finish();self.s.tick()
        self.assertEqual(self.s.data['active']['kind'],'model');self.assertEqual(len(self.transport.requests),3)
    def test_unknown_terminal_does_not_advance(self):
        self.begin(2);self.status('FINISH');self.assertEqual(len(self.transport.requests),1)
        self.assertIsNotNone(self.s.data['active'])
    def test_other_job_is_never_stopped_or_advanced(self):
        self.begin(2);self.now+=16;self.status('RUNNING',tag='other')
        self.assertEqual(self.s.data['active']['monitor']['stage'],'syncing')
        self.assertEqual(len(self.transport.requests),1)
        self.now+=16;self.s.tick()
        self.assertFalse(self.s.data['running']);self.assertEqual(len(self.transport.requests),1)
    def test_changed_strong_identity_holds(self):
        self.begin();self.status('RUNNING');self.status('FINISH',identity='other')
        self.assertEqual(self.s.data['active']['monitor']['stage'],'syncing')
        self.now+=16;self.s.tick()
        self.assertEqual(self.s.data['phase'],'recovery')
    def test_external_stop_pauses_without_swap(self):
        self.begin(2);self.status('RUNNING');self.status('FAILED');self.s.tick()
        self.assertEqual(self.s.data['phase'],'paused');self.assertEqual(len(self.transport.requests),1)
    def test_end_current_stops_then_swaps(self):
        self.begin(2);self.status('RUNNING');self.s.stop(self.transport.snapshot(),True)
        self.assertEqual(self.transport.requests[-1]['action'],'stop');self.status('FAILED');self.s.tick()
        self.assertEqual(self.s.data['active']['kind'],'swap')
    def test_stop_queue_wins_finish_race(self):
        self.begin(2);self.status('RUNNING');self.s.stop(self.transport.snapshot(),False);self.status('FINISH');self.s.tick()
        self.assertEqual(self.s.data['phase'],'paused');self.assertEqual(len(self.transport.requests),2)
    def test_pause_intent_cannot_be_overridden_by_continue(self):
        self.begin();self.status('RUNNING');self.s.stop(self.transport.snapshot(),False)
        with self.assertRaises(ValueError):self.s.stop(self.transport.snapshot(),True)
    def test_skip_some_waits_for_ack(self):
        self.begin();self.status('RUNNING');self.s.control(self.transport.snapshot(),'skip',[1419])
        self.assertEqual(self.transport.requests[-1]['objects'],[1419]);self.assertTrue(self.s.data['active']['pending_skip'])
        self.transport.device['telemetry']['s_obj']=[1419];self.s.tick()
        self.assertEqual(self.s.data['active']['skipped'],[1419]);self.assertNotIn('pending_skip',self.s.data['active'])
    def test_skip_last_becomes_end_current(self):
        self.begin();self.status('RUNNING');self.transport.device['telemetry']['s_obj']=[1419]
        self.s.control(self.transport.snapshot(),'skip',[1420]);self.assertEqual(self.transport.requests[-1]['action'],'stop')
        self.assertEqual(self.s.data['active']['stop_intent'],'continue')
    def test_missing_object_markers_reject_partial_skip(self):
        self.begin();self.status('RUNNING');self.s.data['jobs'][0]['label_markers']=False
        with self.assertRaises(ValueError):self.s.control(self.transport.snapshot(),'skip',[1419])
    def test_skip_ack_timeout_holds(self):
        self.begin();self.status('RUNNING');self.s.control(self.transport.snapshot(),'skip',[1419]);self.now+=21;self.s.tick()
        self.assertEqual(self.s.data['phase'],'recovery')
    def test_stop_upload_keeps_intent_for_late_start(self):
        self.begin();self.s.stop(self.transport.snapshot(),False)
        self.assertEqual(self.transport.requests[-1]['action'],'cancel_submit')
        self.status('RUNNING');self.assertEqual(self.transport.requests[-1]['action'],'stop')
    def test_modified_private_asset_never_submits(self):
        j=self.add();Path(j['path']).write_bytes(b'corrupt')
        with self.assertRaises(ValueError):self.s.start(self.transport.snapshot(),True)
        self.assertFalse(self.transport.requests)
    def test_input_original_can_change_without_affecting_frozen_asset(self):
        j=self.add();Path(j['source_path']).write_bytes(b'other')
        self.s.start(self.transport.snapshot(),True);self.s.tick();self.assertEqual(len(self.transport.requests),1)
    def test_preflight_does_not_start_machine(self):
        self.add();self.s.preflight(self.transport.snapshot());self.assertFalse(self.transport.requests)
    def test_no_start_without_clear_plate_ack(self):
        self.add()
        with self.assertRaises(ValueError):self.s.start(self.transport.snapshot())
    def test_device_error_never_advances(self):
        self.begin();self.status('RUNNING');self.transport.device['telemetry']['print_error']=123;self.s.tick()
        self.assertFalse(self.s.data['running'])

    def test_hms_message_pauses_future_dispatch(self):
        self.begin();self.status('RUNNING');self.transport.device['telemetry']['hms_count']=1;self.s.tick()
        self.assertFalse(self.s.data['running'])

    def test_idle_hms_is_reported_as_device_alert_not_running_task(self):
        self.add()
        self.transport.device['telemetry'].update(gcode_state='IDLE', hms_count=1)
        with self.assertRaisesRegex(ValueError, '没有运行中的打印任务.*1 条 HMS'):
            self.s.start(self.transport.snapshot(), True)
        self.assertFalse(self.transport.requests)
        self.assertFalse(self.s.data['running'])
        self.transport.device['telemetry']['hms_count'] = 0
        self.s.start(self.transport.snapshot(), True)
        self.assertTrue(self.s.data['running'])
        self.assertFalse(self.transport.requests)

    def test_idle_print_error_includes_code_and_does_not_send(self):
        self.add()
        self.transport.device['telemetry'].update(gcode_state='FINISH', print_error=0x03008004)
        with self.assertRaisesRegex(ValueError, '打印错误 0x03008004'):
            self.s.start(self.transport.snapshot(), True)
        self.assertFalse(self.transport.requests)
        self.assertFalse(self.s.data['running'])

    def test_new_title_without_strong_identity_does_not_reuse_old_id(self):
        a=self.begin();self.now+=1
        t=self.transport.device['telemetry'];t.update(gcode_state='PREPARE',subtask_name=a['tag'])
        self.s.tick();self.assertTrue(self.s.data['running']);self.assertFalse(self.s.data['active']['identity'])

    def test_new_title_with_previous_terminal_ids_does_not_poison_startup(self):
        a=self.begin(2)
        self.status('FINISH',identity='previous-plate')
        self.assertFalse(a['identity']);self.assertFalse(a['seen_running'])
        self.status('PREPARE',identity='temporary-startup-id')
        self.assertFalse(a['identity']);self.assertFalse(a['seen_running'])
        self.status('RUNNING',identity='actual-new-plate')
        self.assertTrue(a['seen_running']);self.assertEqual(a['identity']['subtask_id'],'actual-new-plate')
        self.status('FINISH',identity='actual-new-plate')
        self.assertEqual(self.s.data['phase'],'between');self.s.tick()
        self.assertEqual(self.s.data['active']['kind'],'swap')
        self.assertEqual(len(self.transport.requests),2)

    def test_preparation_ids_can_change_before_actual_running(self):
        a=self.begin()
        self.status('PREPARE',identity='old');self.status('SLICING',identity='provisional')
        self.assertTrue(self.s.data['running']);self.assertFalse(a['identity'])
        self.status('RUNNING',identity='actual');self.status('FINISH',identity='actual')
        self.assertEqual(self.s.data['phase'],'completed')

    def test_stale_running_state_cannot_bind_startup_identity(self):
        a=self.begin();self.transport.device['state_age_ms']=20000;self.status('RUNNING')
        self.assertFalse(a['identity']);self.assertFalse(a['seen_running'])

    def finished_unobserved(self,count=2):
        a=self.begin(count)
        # Legacy versions saved a provisional identity before observing actual RUNNING.
        a['identity']={'subtask_id':'previous','task_id':'old'};a['seen_running']=False
        self.transport.device['telemetry'].update(gcode_state='FINISH',mc_percent=100,subtask_name=a['tag'],subtask_id='actual',task_id='actual')
        self.s._hold('未获得可信的本任务完成回报')
        return a

    def test_unobserved_finished_task_does_not_loop_resume_back_into_recovery(self):
        self.finished_unobserved();before=self.s.snapshot()
        with self.assertRaisesRegex(ValueError,'确认本盘已完成并继续'):self.s.resume_monitor(self.transport.snapshot())
        self.assertEqual(self.s.snapshot(),before)

    def test_user_review_recovers_legacy_startup_mismatch_then_one_swap_and_next_model(self):
        a=self.finished_unobserved();self.s.data['auto_after_swap']=True
        self.s.completion_review(self.transport.snapshot(),a['request_id'])
        self.assertEqual(len(self.transport.requests),1)
        self.s.complete_continue(self.transport.snapshot(),a['request_id'],True)
        self.assertEqual(self.s.data['jobs'][0]['status'],'已完成');self.assertEqual(self.s.data['phase'],'between')
        self.assertEqual(len(self.transport.requests),1)
        self.s.tick();self.assertEqual(self.s.data['active']['kind'],'swap')
        self.finish();self.s.tick();self.assertEqual(self.s.data['active']['kind'],'model')
        self.assertEqual(self.s.data['active']['job_id'],self.s.data['jobs'][1]['id'])
        self.assertEqual(len(self.transport.requests),3)

    def test_completion_review_never_advances_without_explicit_confirmation(self):
        a=self.finished_unobserved();before=self.s.snapshot()
        with self.assertRaisesRegex(ValueError,'请确认本盘'):self.s.complete_continue(self.transport.snapshot(),a['request_id'])
        self.assertEqual(self.s.snapshot(),before);self.assertEqual(len(self.transport.requests),1)

    def test_completion_review_checks_frozen_attempt_id(self):
        self.finished_unobserved()
        with self.assertRaisesRegex(ValueError,'任务已变化'):self.s.complete_continue(self.transport.snapshot(),'another-attempt',True)

    def test_completion_review_rejects_other_task_or_no_strong_identity(self):
        a=self.finished_unobserved();t=self.transport.device['telemetry'];t['subtask_name']='other'
        with self.assertRaisesRegex(ValueError,'身份'):self.s.completion_review(self.transport.snapshot(),a['request_id'])
        t['subtask_name']=a['tag'];t.pop('subtask_id');t.pop('task_id')
        with self.assertRaisesRegex(ValueError,'身份'):self.s.completion_review(self.transport.snapshot(),a['request_id'])

    def test_completion_review_requires_fresh_success_and_full_progress(self):
        a=self.finished_unobserved();t=self.transport.device['telemetry']
        for status,progress in [('FAILED',100),('IDLE',100),('RUNNING',100),('FINISH',99)]:
            t.update(gcode_state=status,mc_percent=progress)
            with self.subTest(status=status):
                with self.assertRaises(ValueError):self.s.completion_review(self.transport.snapshot(),a['request_id'])
        t.update(gcode_state='FINISH',mc_percent=100);self.transport.device['state_age_ms']=20000
        with self.assertRaises(ValueError):self.s.completion_review(self.transport.snapshot(),a['request_id'])

    def test_completion_review_keeps_strict_identity_after_actual_running(self):
        a=self.begin();self.status('RUNNING',identity='one');self.s._hold('offline')
        self.transport.device['telemetry'].update(gcode_state='FINISH',mc_percent=100,subtask_id='two')
        with self.assertRaisesRegex(ValueError,'身份'):self.s.completion_review(self.transport.snapshot(),a['request_id'])

    def test_completion_review_blocks_unfinished_upload_or_pause_intent(self):
        a=self.finished_unobserved();receipt=self.transport.value['commands'][0];receipt['status']='working'
        with self.assertRaisesRegex(ValueError,'还未结束'):self.s.completion_review(self.transport.snapshot(),a['request_id'])
        receipt['status']='sent';a['stop_intent']='pause'
        with self.assertRaisesRegex(ValueError,'停止整个队列'):self.s.completion_review(self.transport.snapshot(),a['request_id'])

    def test_completion_review_checks_swap_before_recording_success(self):
        a=self.finished_unobserved();self.s.data['a1_swap']['enabled']=False
        with self.assertRaises(ValueError):self.s.complete_continue(self.transport.snapshot(),a['request_id'],True)
        self.assertEqual(self.s.data['jobs'][0]['status'],'发送中');self.assertEqual(len(self.transport.requests),1)

    def test_completion_review_manual_mode_waits_for_physical_board_confirmation(self):
        a=self.finished_unobserved();self.s.data['plate_mode']='manual'
        self.s.complete_continue(self.transport.snapshot(),a['request_id'],True);self.s.tick()
        self.assertEqual(self.s.data['phase'],'confirm_plate');self.assertFalse(self.s.data['running'])
        self.assertEqual(len(self.transport.requests),1)

    def test_reviewed_last_plate_is_retained(self):
        a=self.finished_unobserved(1);self.s.complete_continue(self.transport.snapshot(),a['request_id'],True)
        self.assertEqual(self.s.data['phase'],'completed');self.assertFalse(self.s.data['running'])
        self.assertTrue(self.s.data['dirty_plate']);self.assertEqual(len(self.transport.requests),1)

    def add_callback_events(self,states,identity='actual'):
        d=self.transport.device;a=self.s.data['active'];d['monitor_epoch']='fixture-session'
        d['task_events']=[dict(event=i+1,age_ms=0,state_reported=True,telemetry=dict(gcode_state=state,subtask_name=a['tag'],subtask_id=identity)) for i,state in enumerate(states)]
        d['task_sequence']=len(states)
        d['telemetry'].update(gcode_state=states[-1],subtask_name=a['tag'],subtask_id=identity)

    def test_callback_replay_completes_missed_poll_then_only_one_swap(self):
        self.begin(2);self.add_callback_events(['PREPARE','RUNNING','FINISH'])
        self.s.tick();self.assertEqual(self.s.data['phase'],'between')
        self.assertEqual(self.s.data['jobs'][0]['status'],'已完成')
        self.s.tick();self.assertEqual(self.s.data['active']['kind'],'swap')
        self.assertEqual(len(self.transport.requests),2)
        record=next(r for r in self.s.data['journal'] if r['action']=='completion')
        self.assertEqual([e['kind'] for e in record['monitor']['evidence']],['started','terminal'])

    def test_callback_replay_failed_print_pauses_without_swap(self):
        self.begin(2);self.add_callback_events(['RUNNING','FAILED']);self.s.tick();self.s.tick()
        self.assertEqual(self.s.data['phase'],'paused');self.assertEqual(len(self.transport.requests),1)

    def test_buffered_finish_after_idle_is_recognized_without_current_task_title(self):
        self.begin(2);self.add_callback_events(['RUNNING','FINISH']);self.transport.device['telemetry']=dict(gcode_state='IDLE')
        self.s.tick();self.assertEqual(self.s.data['phase'],'between')
        self.s.tick();self.assertEqual(self.s.data['active']['kind'],'swap')

    def test_upload_worker_still_blocks_replayed_completion_dispatch(self):
        self.begin(2);self.add_callback_events(['RUNNING','FINISH']);self.transport.value['commands'][0]['status']='working'
        self.s.tick();self.assertIsNotNone(self.s.data['active']);self.assertEqual(len(self.transport.requests),1)
        self.transport.value['commands'][0]['status']='sent';self.s.tick()
        self.assertEqual(self.s.data['phase'],'between')

    def test_optional_identifier_late_change_does_not_pause_queue(self):
        self.begin(2);self.transport.device['telemetry']['task_id']='early';self.status('RUNNING')
        self.transport.device['telemetry']['task_id']='late';self.status('FINISH')
        self.assertEqual(self.s.data['phase'],'between')

    def test_completion_history_survives_service_restart(self):
        self.begin();self.status('RUNNING');self.status('FINISH');self.s.close();self.s=self.service()
        evidence=[r for r in self.s.data['journal'] if r['action']=='completion'][0]['monitor']['evidence']
        self.assertEqual([e['kind'] for e in evidence],['started','terminal'])
    def test_stale_terminal_does_not_advance(self):
        self.begin();self.status('RUNNING');self.transport.device['state_age_ms']=20000;self.status('FINISH')
        self.assertIsNotNone(self.s.data['active'])
    def test_disconnect_recovery_does_not_resubmit(self):
        self.begin();self.status('RUNNING');self.transport.device['age_ms']=20000
        self.s.tick();self.assertEqual(self.s.data['active']['monitor']['stage'],'reconnecting')
        self.now+=61;self.s.tick();self.assertEqual(self.s.data['phase'],'recovery')
        self.transport.device['age_ms']=0;self.s.resume_monitor(self.transport.snapshot());self.s.tick()
        self.assertEqual(len(self.transport.requests),1)

    def test_short_connection_gap_recovers_terminal_history_without_manual_resume(self):
        self.begin(2);self.status('RUNNING');self.transport.device['age_ms']=20000
        self.s.tick();self.assertTrue(self.s.data['running'])
        self.now+=20;self.transport.device['age_ms']=0;self.add_callback_events(['RUNNING','FINISH'],identity='job1')
        self.s.tick();self.assertEqual(self.s.data['phase'],'between');self.assertEqual(len(self.transport.requests),1)
    def test_restart_requires_reconciliation_and_no_duplicate_send(self):
        self.begin();self.status('RUNNING');self.s.close();self.s=self.service();self.s.tick()
        self.assertEqual(self.s.data['phase'],'recovery');self.assertEqual(len(self.transport.requests),1)
        self.s.resume_monitor(self.transport.snapshot());self.status('FINISH');self.assertEqual(self.s.data['phase'],'completed')
    def test_recovery_after_native_event_counter_reset(self):
        self.begin();self.status('RUNNING');self.s._hold('restart');self.transport.device['state_event']=1
        self.transport.device['telemetry']['gcode_state']='FINISH'
        self.s.resume_monitor(self.transport.snapshot());self.s.tick();self.assertEqual(self.s.data['phase'],'completed')
    def test_intent_persistence_failure_prevents_machine_command(self):
        self.add();self.s.start(self.transport.snapshot(),True)
        def fail():raise OSError('disk full')
        self.s._save=fail
        with self.assertRaises(OSError):self.s.tick()
        self.assertFalse(self.transport.requests)
        self.s._save=lambda:None
    def test_command_failure_keeps_attempt_and_never_retries(self):
        self.add();self.s.start(self.transport.snapshot(),True)
        self.transport.command=lambda r:(_ for _ in ()).throw(RuntimeError('unknown result'))
        self.s.tick();self.s.tick();self.assertIsNotNone(self.s.data['active']);self.assertFalse(self.s.data['running'])
        self.assertEqual(len(self.s.data['journal']),1)
    def test_pause_during_swap_never_advances(self):
        self.begin(2);self.finish();self.s.tick();self.status('RUNNING');self.s.stop(self.transport.snapshot(),False);self.status('FINISH');self.s.tick()
        self.assertFalse(self.s.data['running']);self.assertEqual(self.s.data['jobs'][1]['status'],'等待')
    def test_only_explicit_reconcile_discards_ambiguous_attempt(self):
        self.begin();self.s._hold('unknown');self.s.reconcile(self.transport.snapshot(),False)
        self.assertEqual(self.s.data['jobs'][0]['status'],'已中止');self.assertTrue(self.s.data['dirty_plate'])
    def test_two_copies_are_independent(self):
        a=self.add();b=self.add();a['settings']['mapping']['9']='external'
        self.assertEqual(b['settings']['mapping']['9'],'ams/0/tray/2')

    def test_second_executor_cannot_own_same_queue(self):
        with self.assertRaisesRegex(ValueError,'另一个'):
            self.service()

    def test_worker_dispatches_without_any_page_poll(self):
        self.add();self.s.start(self.transport.snapshot(),True)
        import threading
        self.s.worker=threading.Thread(target=self.s._loop,daemon=True);self.s.worker.start()
        deadline=time.monotonic()+3
        while not self.transport.requests and time.monotonic()<deadline:
            time.sleep(.02)
        self.assertEqual(len(self.transport.requests),1)

if __name__=='__main__':unittest.main()
