"""Whitelist snapshots and commands from the in-process native queue bridge."""
import math
from printer_models import canonical_model
from native_connection import NativeQueueBridge


class PrinterConnection:
    def __init__(self, host):
        self.host = host
        self.native = NativeQueueBridge()

    def refresh(self):
        if getattr(self.host,'queue_bridge_v1',None) is None:
            self.native.refresh()

    def command(self, request):
        return (getattr(self.host, 'queue_bridge_v1', None) or self.native).command(request)

    def watch(self, device_id):
        if device_id:
            if len(self.native.watch_ids) >= 32 and device_id not in self.native.watch_ids:
                raise ValueError('最多同时监控 32 台打印机。')
            self.native.watch_ids.add(device_id)

    def snapshot(self):
        empty = dict(available=False, can_submit=False, devices=[],
                     reason='当前 Orca 未提供原生队列桥接；Open Bamboo 联网正常也不会自动向页面开放设备和 AMS。')
        try:
            bridge = getattr(self.host, 'queue_bridge_v1', None) or self.native
            raw = bridge.snapshot()
            if not isinstance(raw, dict) or type(raw.get('protocol')) is not int or raw['protocol'] != 1 or raw.get('origin') != 'orca-native-queue':
                raise ValueError('桥接协议不匹配。')
            if raw.get('cloud_session_reused') is not True:
                raise ValueError('桥接未复用 Orca 当前云端会话。')
            rows = raw.get('devices')
            if not isinstance(rows, list) or len(rows) > 100:
                raise ValueError('设备列表格式错误。')
            devices, seen = [], set()
            for row in rows:
                if not isinstance(row, dict):
                    raise ValueError('设备记录格式错误。')
                for key in ('id', 'name'):
                    if not isinstance(row.get(key), str) or not 0 < len(row[key]) <= 256:
                        raise ValueError('设备身份信息不完整。')
                if not isinstance(row.get('model'),str) or len(row['model'])>256:
                    raise ValueError('设备机型信息格式错误。')
                if row['id'] in seen:
                    raise ValueError('设备编号重复。')
                seen.add(row['id'])
                if any(type(row.get(k)) is not bool for k in ('online', 'cloud_connected')):
                    raise ValueError('设备连接状态不完整。')
                for key in ('age_ms',):
                    if type(row.get(key)) not in (float, int) or not math.isfinite(row[key]) or row[key] < 0:
                        raise ValueError('设备喷嘴或信息时间无效。')
                if row.get('nozzle') is not None and (type(row['nozzle']) not in (int,float) or not math.isfinite(row['nozzle']) or not 0 < row['nozzle'] <= 2):
                    raise ValueError('设备喷嘴规格无效。')
                supported = row.get('supported_options')
                if not isinstance(supported, list) or any(k not in ('bed_leveling', 'flow_calibration', 'timelapse') for k in supported):
                    raise ValueError('设备打印选项能力不完整。')
                slots, slot_ids = [], set()
                if not isinstance(row.get('slots'), list) or len(row['slots']) > 64:
                    raise ValueError('耗材槽列表格式错误。')
                for slot in row['slots']:
                    if not isinstance(slot, dict) or any(not isinstance(slot.get(k), str) or len(slot[k]) > 256 for k in ('id', 'label', 'type', 'color')):
                        raise ValueError('耗材槽信息不完整。')
                    if not slot['id'] or slot['id'] in slot_ids or slot.get('kind') not in ('ams', 'external') or (slot.get('present') is not None and type(slot['present']) is not bool):
                        raise ValueError('耗材槽身份或状态无效。')
                    slot_ids.add(slot['id'])
                    slots.append({k: slot[k] for k in ('id', 'label', 'kind', 'present', 'type', 'color')})
                # Strip arbitrary fields, including any credentials in an erroneous response.
                device = {k: row[k] for k in ('id', 'name', 'model', 'online', 'cloud_connected', 'nozzle', 'age_ms')}
                device['model'] = canonical_model(device['model']) or device['model']
                device['slots'] = slots
                device['supported_options'] = list(dict.fromkeys(supported))
                telemetry = row.get('telemetry',{})
                if not isinstance(telemetry,dict):
                    raise ValueError('设备状态格式错误。')
                device['telemetry'] = {k:v for k,v in telemetry.items() if k in (
                    'nozzle_temper','bed_temper','nozzle_target_temper','bed_target_temper',
                    'mc_percent','print_error','layer_num','total_layer_num','gcode_state',
                    'subtask_id','task_id','project_id','gcode_start_time','subtask_name','gcode_file',
                    'hms_count','skip_ack_sequence','skip_ack_result') and type(v) in (str,int,float) and len(str(v))<=256}
                skipped=telemetry.get('s_obj', [])
                device['telemetry']['s_obj']=[v for v in skipped if type(v) is int and 0<=v<1e9][:1024] if isinstance(skipped,list) else []
                for key in ('state_event','state_age_ms'):
                    n=row.get(key,1e9 if key=='state_age_ms' else 0)
                    device[key]=n if type(n) in (int,float) and math.isfinite(n) and n>=0 else 1e9
                device['telemetry_source'] = row.get('telemetry_source') if row.get('telemetry_source') in ('cloud','lan') else ''
                epoch=row.get('monitor_epoch','')
                device['monitor_epoch']=epoch if isinstance(epoch,str) and len(epoch)<=128 else ''
                seq=row.get('task_sequence',0)
                device['task_sequence']=int(seq) if type(seq) in (int,float) and math.isfinite(seq) and 0<=seq<2**53 and int(seq)==seq else 0
                device['task_events']=[]
                events=row.get('task_events',[])
                if isinstance(events,list) and len(events)<=32:
                    for event in events:
                        if not isinstance(event,dict) or type(event.get('event')) not in (int,float) or not 0<event['event']<2**53 or int(event['event'])!=event['event'] or type(event.get('age_ms')) not in (int,float) or not math.isfinite(event['age_ms']) or event['age_ms']<0 or type(event.get('state_reported')) is not bool or not isinstance(event.get('telemetry'),dict):continue
                        telemetry={k:v for k,v in event['telemetry'].items() if k in ('gcode_state','subtask_name','subtask_id','task_id','gcode_start_time','mc_percent','print_error','hms_count') and type(v) in (str,int,float) and len(str(v))<=256}
                        device['task_events'].append(dict(event=int(event['event']),age_ms=event['age_ms'],state_reported=event['state_reported'],telemetry=telemetry))
                sensor = row.get('filament_at_toolhead')
                device['filament_at_toolhead'] = sensor if type(sensor) is int and sensor in (0,1) else None
                tray = row.get('current_tray')
                device['current_tray'] = tray if type(tray) is int and 0<=tray<=255 else None
                devices.append(device)
            records=raw.get('commands',[])
            commands=[{k:v for k,v in r.items() if k in ('request_id','device_id','action','tag','status','stage','progress','code') and type(v) in (str,int,float)} for r in records if isinstance(r,dict)] if isinstance(records,list) and len(records)<=4096 else []
            return dict(available=True, can_submit=raw.get('can_submit') is True, devices=devices, commands=commands,
                        material_mapping_ready=raw.get('material_mapping_ready') is True,
                        upload_busy=raw.get('upload_busy') is True,
                        refreshing=raw.get('refreshing') is True,
                        reason=raw.get('refresh_error') or ('设备列表读取中…' if raw.get('refreshing') and not devices else '原生桥接已连接，复用 Orca 云端会话。'))
        except RuntimeError as exc:
            empty['reason'] = str(exc)
            return empty
        except Exception:
            empty['reason'] = '原生设备桥接返回无效信息，已停止使用设备列表。'
            return empty
