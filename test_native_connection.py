"""Exercise the C buffer contract without loading a networking library."""
import ctypes
import json
import time
import unittest
import types
from unittest.mock import patch
import native_connection
from native_connection import NativeQueueBridge


class BufferDLL:
    def __init__(self,content):self.content=content;self.refreshes=0;self.rc=0;self.calls=0;self.commands=[]
    def obn_queue_command_v1(self,payload,length):self.commands.append(json.loads(payload));return 0
    def obn_queue_snapshot_v1(self,buf,capacity):
        self.calls+=1
        data=self.content(self.calls) if callable(self.content) else self.content
        if buf is not None and capacity>=len(data):ctypes.memmove(buf,data,len(data))
        return len(data)
    def obn_queue_refresh_v1(self):self.refreshes+=1;return self.rc


class NativeBufferTests(unittest.TestCase):
    def bridge(self,content):
        bridge=NativeQueueBridge();bridge._dll=BufferDLL(content);bridge._refresh_at=time.monotonic()
        return bridge

    def payload(self,**extra):
        return json.dumps(dict(attached=True,selected_device_id='real-id',devices=[dict(id='real-id',age_ms=0,nozzle=.4,telemetry=dict(gcode_state='IDLE'))],**extra)).encode()+b'\0'

    def test_valid_bounded_utf8_snapshot(self):
        bridge=self.bridge(self.payload(label='真实设备'))
        self.assertEqual(bridge.snapshot()['label'],'真实设备')
        self.assertEqual(bridge._dll.refreshes,0)

    def test_snapshot_can_grow_between_size_and_read(self):
        little=self.payload();large=self.payload(extra='x'*100)
        bridge=self.bridge(lambda n:little if n==1 else large)
        self.assertEqual(bridge.snapshot()['extra'],'x'*100)
        self.assertEqual(bridge._dll.calls,3)

    def test_oversized_native_reply_rejected(self):
        bridge=self.bridge(b'x'*(2*1024*1024+2))
        with self.assertRaises(ValueError):bridge.snapshot()

    def test_unterminated_reply_rejected(self):
        with self.assertRaises(ValueError):self.bridge(b'{}x').snapshot()

    def test_malformed_json_rejected(self):
        with self.assertRaises(ValueError):self.bridge(b'{bad\0').snapshot()

    def test_no_agent_does_not_trigger_refresh(self):
        bridge=self.bridge(b'{"attached":false}\0')
        with self.assertRaises(RuntimeError):bridge.snapshot()
        self.assertEqual(bridge._dll.refreshes,0)

    def test_first_snapshot_bootstraps_existing_session_only(self):
        bridge=self.bridge(self.payload());bridge._refresh_at=-1000
        bridge.snapshot();self.assertEqual(bridge._dll.refreshes,1)
        bridge.snapshot();self.assertEqual(bridge._dll.refreshes,1)

    def test_refresh_failure_reported(self):
        bridge=self.bridge(self.payload());bridge._dll.rc=-1
        with self.assertRaises(RuntimeError):bridge.refresh()

    def test_old_bridge_rejects_submission_before_any_native_command(self):
        bridge=self.bridge(self.payload())
        with self.assertRaisesRegex(RuntimeError,'完整耗材映射'):
            bridge.command(dict(action='submit',use_ams=True))
        self.assertEqual(bridge._dll.commands,[])
        self.assertFalse(bridge.snapshot()['material_mapping_ready'])

    def test_new_bridge_accepts_submission_without_second_session(self):
        bridge=self.bridge(self.payload())
        class Revision:
            def __call__(self):return 2
        bridge._dll.obn_queue_material_revision_v1=Revision()
        bridge.command(dict(action='submit',use_ams=True,ams_mapping=[3]))
        self.assertEqual(bridge._dll.commands,[dict(action='submit',use_ams=True,ams_mapping=[3])])
        self.assertTrue(bridge.snapshot()['material_mapping_ready'])

    def test_detail_only_bridge_is_rejected_until_unused_marker_fix_is_loaded(self):
        bridge=self.bridge(self.payload())
        class Revision:
            def __call__(self):return 1
        bridge._dll.obn_queue_material_revision_v1=Revision()
        with self.assertRaisesRegex(RuntimeError,'完整耗材映射'):
            bridge.command(dict(action='submit',use_ams=True))
        self.assertFalse(bridge._dll.commands)
        self.assertFalse(bridge.snapshot()['material_mapping_ready'])

    def test_multiple_watched_devices_are_refreshed_without_replacing_selection(self):
        raw=dict(attached=True,can_submit=True,selected_device_id='real-id',devices=[
            dict(id='real-id',model='N2S',age_ms=0,state_age_ms=0,nozzle=.4,telemetry=dict(gcode_state='IDLE')),
            dict(id='p1-id',model='C12',age_ms=0,state_age_ms=20000,nozzle=.4,telemetry=dict(gcode_state='RUNNING'))])
        bridge=self.bridge(json.dumps(raw).encode()+b'\0');bridge.watch_ids={'real-id','p1-id','removed-id'};bridge._refresh_at=time.monotonic()-11
        result=bridge.snapshot()
        self.assertEqual(result['selected_device_id'],'real-id')
        self.assertEqual(bridge._dll.refreshes,1)
        self.assertTrue(bridge._dll.commands)
        for command in bridge._dll.commands:
            self.assertEqual(command['action'],'watch_many')
            self.assertEqual(command['device_ids'],['p1-id','real-id'])


class NativeDiscoveryTests(unittest.TestCase):
    def discover(self,rows):
        class Call:
            def __init__(self,fn):self.fn=fn
            def __call__(self,*args):return self.fn(*args)
        names={name:i+2 for i,(name,attached) in enumerate(rows)}
        paths={handle:'C:/fixture/'+name for name,handle in names.items()}
        dlls={}
        for name,attached in rows:
            data=json.dumps(dict(attached=attached)).encode()+b'\0'
            def snapshot(buf,capacity,data=data):
                if buf is not None and capacity>=len(data):ctypes.memmove(buf,data,len(data))
                return len(data)
            dlls['C:/fixture/'+name]=types.SimpleNamespace(obn_queue_abi_version_v1=Call(lambda:1),
                obn_queue_snapshot_v1=Call(snapshot),obn_queue_refresh_v1=Call(lambda:0),obn_queue_command_v1=Call(lambda *a:0))
        def filename(handle,buffer,size):buffer.value=paths[handle];return len(buffer.value)
        kernel=types.SimpleNamespace(GetModuleHandleW=Call(lambda name:1 if name=='OrcaSlicer.dll' else names.get(name,0)),GetModuleFileNameW=Call(filename))
        def existing(name,handle):
            self.assertIsNone(name)
            self.assertIn(handle,paths)
            return dlls[paths[handle]]
        with patch.object(native_connection,'os',types.SimpleNamespace(name='nt')),patch.object(ctypes,'WinDLL',return_value=kernel),patch.object(ctypes,'CDLL',side_effect=existing) as loader:
            bridge=NativeQueueBridge()
            result=bridge._load()
            self.assertIs(bridge._load(),result)
            return result,loader.call_args_list,dlls

    def test_each_reviewed_version_attaches_only_to_already_loaded_module(self):
        for name in ('bambu_networking_02.03.00.dll','bambu_networking_02.08.01.dll','bambu_networking_02.08.04.dll','bambu_networking.dll'):
            with self.subTest(name=name):
                dll,calls,known=self.discover([(name,True)])
                self.assertIs(dll,known['C:/fixture/'+name]);self.assertEqual(len(calls),1)

    def test_active_instance_wins_over_unused_loaded_module(self):
        dll,calls,known=self.discover([('bambu_networking_02.03.00.dll',False),('bambu_networking_02.08.04.dll',True)])
        self.assertIs(dll,known['C:/fixture/bambu_networking_02.08.04.dll'])

    def test_multiple_active_instances_are_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'多个联网实例'):
            self.discover([('bambu_networking_02.03.00.dll',True),('bambu_networking_02.08.04.dll',True)])

    def test_unattached_loaded_module_is_not_cached_as_a_session(self):
        with self.assertRaisesRegex(RuntimeError,'等待 Orca'):
            self.discover([('bambu_networking_02.03.00.dll',False)])

    def test_no_matching_module_never_loads_a_new_library(self):
        with self.assertRaisesRegex(RuntimeError,'独立连接组件安装器'):self.discover([])


if __name__=='__main__':unittest.main()
