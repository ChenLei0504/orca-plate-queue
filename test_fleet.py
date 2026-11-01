"""Multi-printer tests use two local fixtures and never contact real hardware."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from queue_engine import QueueService
from queue_fleet import QueueFleet
from queue_domain import blank_print_settings, validate_print_settings
from printer_models import PRINTER_MODELS, canonical_model, supports_auto_swap


class FleetTransport:
    def __init__(self):
        self.requests, self.watched = [], set()
        self.value = dict(available=True, can_submit=True, upload_busy=False, commands=[], devices=[])
        for device_id, model in [('a1', 'N2S'), ('p1', 'C12')]:
            self.value['devices'].append(dict(id=device_id, name=device_id.upper(), model=model, online=True,
                cloud_connected=True, age_ms=0, state_age_ms=0, state_event=1, nozzle=.4,
                supported_options=['bed_leveling', 'timelapse'],
                slots=[dict(id='ams/0/tray/0', label='AMS 1', kind='ams', present=True, type='PETG', color='#FFFFFF')],
                telemetry=dict(gcode_state='IDLE', print_error=0, hms_count=0, s_obj=[])))

    def snapshot(self): return copy.deepcopy(self.value)
    def watch(self, device_id): self.watched.add(device_id)
    def refresh(self): pass
    def device(self, device_id): return next(d for d in self.value['devices'] if d['id'] == device_id)

    def command(self, request):
        self.requests.append(copy.deepcopy(request))
        if request['action'] == 'submit': self.value['upload_busy'] = True
        self.value['commands'].append(dict(request_id=request['request_id'], action=request['action'],
            device_id=request.get('device_id'), status='working' if request['action']=='submit' else 'sent'))
        return 0

    def uploaded(self):
        self.value['upload_busy'] = False
        for r in self.value['commands']:
            if r['action']=='submit': r['status']='sent'


class FleetTests(unittest.TestCase):
    def setUp(self):
        base=Path(__file__).parent/'test-temp';base.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=base);self.root=Path(self.temp.name)
        self.transport=FleetTransport();self.fleets=[]
        def inspect(path, *args):
            path=Path(path);data=json.loads(path.read_text())
            return dict(path=str(path), name=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                printer=data['model'], plate='5', nozzle='.4', filaments=[dict(id='9',type='PETG',color='#FFFFFF',nozzle='.4')],
                filament_count=10, objects=[dict(id='1',name='one')], object_count=1, label_markers=True,
                duration_s=100, thumbnail='')
        self.inspect=inspect
        def factory(*args, **kwargs):return QueueService(*args, **kwargs, start_worker=False)
        self.factory=factory;self.fleet=self.open()

    def open(self):
        fleet=QueueFleet(self.root/'v3',self.transport,self.inspect,self.inspect,'default',service_factory=self.factory)
        self.fleets.append(fleet);return fleet

    def tearDown(self):
        for fleet in self.fleets:fleet.close()
        self.temp.cleanup()

    def select(self, device_id):return self.fleet.select(device_id,self.transport.snapshot())

    def add(self, service):
        device_id=service.data['device_id'];model=self.transport.device(device_id)['model']
        path=self.root/(device_id+'-'+str(len(service.data['jobs']))+'.3mf');path.write_text(json.dumps(dict(model=model)))
        asset=service.freeze(self.inspect(path));settings=blank_print_settings(device_id);settings['mapping']={'9':'ams/0/tray/0'}
        asset.update(id=device_id+'-'+str(len(service.data['jobs'])),status='等待',settings=settings)
        service.commit(lambda:service.data['jobs'].append(asset));return asset

    def state(self, service, status):
        a=service.data['active'];device=self.transport.device(service.data['device_id']);device['state_event']+=1
        device['telemetry'].update(gcode_state=status,subtask_name=a['tag'],subtask_id=device['id']+'-task',gcode_start_time='123')
        service.tick(self.transport.snapshot())

    def test_queues_materials_and_assets_are_isolated_and_selection_is_non_destructive(self):
        a=self.select('a1');one=self.add(a);b=self.select('p1')
        self.assertEqual(b.data['jobs'],[]);self.assertEqual(b.data['plate_mode'],'manual')
        self.assertEqual(b.data['a1_swap']['path'],'');self.assertFalse(b.data['a1_swap']['enabled'])
        two=self.add(b);self.assertNotEqual(Path(one['path']).parent,Path(two['path']).parent)
        self.assertIs(self.select('a1'),a);self.assertEqual(a.data['jobs'][0]['id'],one['id'])
        self.assertEqual(one['settings']['device_id'],'a1');self.assertEqual(two['settings']['device_id'],'p1')

    def test_views_can_change_while_another_printer_is_running(self):
        a=self.select('a1');self.add(a);a.start(self.transport.snapshot(),True);a.tick()
        self.assertIsNotNone(a.data['active']);self.select('p1')
        self.assertTrue(a.data['running']);self.assertEqual(self.fleet.selected_id,'p1')
        self.assertFalse(any(r['action']=='stop' for r in self.transport.requests))

    def test_uploads_are_serialized_but_both_printers_can_print_at_once(self):
        a=self.select('a1');self.add(a);b=self.select('p1');self.add(b)
        a.start(self.transport.snapshot(),True);b.start(self.transport.snapshot(),True)
        a.tick();b.tick()
        self.assertEqual(len(self.transport.requests),1)
        self.assertIsNone(b.data['active']);self.assertTrue(b.data['running'])
        self.assertIn('等待其他打印机',b.data['reason'])
        self.transport.uploaded();self.state(a,'RUNNING');b.tick()
        self.assertEqual([r['device_id'] for r in self.transport.requests],['a1','p1'])
        self.transport.uploaded();self.state(b,'RUNNING')
        self.assertTrue(a.data['running'] and b.data['running'])
        self.assertEqual(a.data['phase'],'monitoring');self.assertEqual(b.data['phase'],'monitoring')

    def test_error_on_one_printer_does_not_pause_another(self):
        a=self.select('a1');self.add(a);b=self.select('p1');self.add(b)
        a.start(self.transport.snapshot(),True);a.tick();self.transport.uploaded();self.state(a,'RUNNING')
        b.start(self.transport.snapshot(),True);b.tick();self.transport.uploaded();self.state(b,'RUNNING')
        self.transport.device('a1')['telemetry']['print_error']=1;a.tick()
        self.assertFalse(a.data['running']);self.assertTrue(b.data['running']);b.tick()
        self.assertTrue(b.data['running'])

    def test_stop_targets_only_the_requested_machine(self):
        a=self.select('a1');self.add(a);b=self.select('p1');self.add(b)
        for service in (a,b):
            service.start(self.transport.snapshot(),True);service.tick();self.transport.uploaded();self.state(service,'RUNNING')
        a.stop(self.transport.snapshot(),False)
        self.assertEqual(self.transport.requests[-1]['action'],'stop')
        self.assertEqual(self.transport.requests[-1]['device_id'],'a1');self.assertTrue(b.data['running'])

    def test_wrong_machine_identity_never_completes_other_printers_task(self):
        a=self.select('a1');self.add(a);b=self.select('p1');self.add(b)
        for service in (a,b):
            service.start(self.transport.snapshot(),True);service.tick();self.transport.uploaded();self.state(service,'RUNNING')
        self.transport.device('a1')['telemetry'].update(gcode_state='FINISH',subtask_name=b.data['active']['tag'])
        self.transport.device('a1')['state_event']+=1;a.tick()
        self.assertNotEqual(a.data['jobs'][0]['status'],'已完成');self.assertTrue(b.data['running'])

    def test_manual_plate_change_waits_for_confirmation_without_mechanical_commands(self):
        b=self.select('p1');self.add(b);self.add(b)
        b.start(self.transport.snapshot(),True);b.tick();self.transport.uploaded();self.state(b,'RUNNING');self.state(b,'FINISH')
        self.assertEqual(b.data['phase'],'confirm_plate');self.assertFalse(b.data['running'])
        self.assertEqual(len(self.transport.requests),1)
        b.confirm_plate(self.transport.snapshot());b.tick()
        self.assertEqual(len(self.transport.requests),2);self.assertEqual(b.data['active']['kind'],'model')

    def test_manual_queue_cannot_run_an_automatic_swap_first(self):
        b=self.select('p1');self.add(b)
        with self.assertRaisesRegex(ValueError,'手动'):b.start(self.transport.snapshot(),swap_first=True)
        self.assertEqual(self.transport.requests,[])

    def test_restart_restores_each_queue_and_requires_independent_recovery(self):
        a=self.select('a1');self.add(a);b=self.select('p1');self.add(b)
        for service in (a,b):
            service.start(self.transport.snapshot(),True);service.tick();self.transport.uploaded();self.state(service,'RUNNING')
        self.fleet.close();restored=self.open()
        self.assertEqual(restored.selected_id,'p1')
        for device_id in ('a1','p1'):
            service=restored.services[device_id]
            self.assertFalse(service.data['running']);self.assertEqual(service.data['phase'],'recovery')
            self.assertIsNotNone(service.data['active'])

    def test_model_match_is_exact_for_all_supported_single_nozzle_models(self):
        asset=dict(printer='N2S',nozzle='.4',filaments=[dict(id='9',type='PETG',nozzle='.4')])
        settings=blank_print_settings('a1');settings['mapping']={'9':'ams/0/tray/0'}
        for code,name in PRINTER_MODELS.items():
            self.transport.device('a1')['model']=code;asset['printer']=name
            self.assertEqual(canonical_model(name),code)
            validate_print_settings(asset,settings,self.transport.snapshot(),'a1',require_send=True)
            asset['printer']='Bambu Lab P1P' if code!='C11' else 'Bambu Lab A1'
            with self.assertRaisesRegex(ValueError,'机型'):validate_print_settings(asset,settings,self.transport.snapshot(),'a1')

    def test_default_a1_swap_is_rejected_on_other_models(self):
        asset=dict(printer='Bambu Lab P1S',nozzle='.4',motion_only=True)
        self.transport.device('a1')['model']='C12'
        with self.assertRaisesRegex(ValueError,'A1'):validate_print_settings(asset,blank_print_settings('a1'),self.transport.snapshot(),'a1')

    def test_current_swap_capability_is_limited_to_a1(self):
        for code in PRINTER_MODELS:
            self.assertEqual(supports_auto_swap(code),code=='N2S')
        b=self.select('p1');self.add(b);self.add(b);b.data['plate_mode']='automatic'
        with self.assertRaisesRegex(ValueError,'没有自动换盘'):b.preflight(self.transport.snapshot())
        with self.assertRaisesRegex(ValueError,'没有自动换盘'):b._dispatch(self.transport.snapshot(),True)
        self.assertEqual(self.transport.requests,[])

    def test_missing_or_unsupported_machine_cannot_create_a_queue(self):
        for device_id in ('missing','../../outside'):
            with self.assertRaises(ValueError):self.select(device_id)
        self.transport.device('p1')['model']='unknown'
        with self.assertRaises(ValueError):self.select('p1')
        self.assertEqual(list(self.fleet.services),[''])

    def test_offline_existing_queue_remains_viewable(self):
        self.select('a1');self.select('p1');self.transport.device('a1')['online']=False
        self.assertEqual(self.select('a1').data['device_id'],'a1')
        self.assertFalse(next(r for r in self.fleet.snapshot(self.transport.snapshot()) if r['id']=='a1')['online'])


if __name__=='__main__':unittest.main()
