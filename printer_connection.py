"""Validate one explicitly selected queue connection; never combine provider sessions."""
import math
import threading
from printer_models import canonical_model
from native_connection import NativeQueueBridge, NativeBridgeBindingError


class PrinterConnection:
    def __init__(self, host, *, provider=None, mode='native'):
        if mode not in ('native', 'owned_cloud'):
            raise ValueError('未知的队列连接方式。')
        if mode == 'owned_cloud' and provider is None:
            raise ValueError('独立云连接需要显式提供连接组件。')
        if provider is not None and getattr(host, 'queue_bridge_v1', None) is not None:
            raise ValueError('不能同时使用宿主桥接和独立连接。')
        self.host = host
        self.mode = mode
        # Select once. Replacing a host property must never reroute a live queue.
        host_bridge = getattr(host, 'queue_bridge_v1', None)
        self._host_provider = host_bridge is not None
        self.native = provider if provider is not None else (host_bridge if host_bridge is not None else NativeQueueBridge())
        self._watch_ids = set()
        self._watch_lock = threading.Lock()
        self._closed = False

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self.mode == 'owned_cloud':
            close = getattr(self.native, 'close', None)
            if close is not None:
                close()

    def _ensure_open(self):
        if self._closed:
            raise RuntimeError('队列连接已关闭。')

    def refresh(self):
        self._ensure_open()
        return self.native.refresh()

    def command(self, request):
        self._ensure_open()
        if self.mode == 'owned_cloud':
            status = self.snapshot()
            if not status.get('available') or not status.get('can_submit'):
                raise RuntimeError('独立云连接尚未就绪，不能发送打印控制。')
        if self._host_provider:
            status = self.snapshot()
            if not status.get('available') or not status.get('can_submit'):
                raise RuntimeError('Orca 队列接口尚未就绪，不能发送打印控制。')
            if request.get('action') == 'submit' and not status.get('material_mapping_ready'):
                raise RuntimeError('Orca 队列接口未确认完整耗材映射支持，已阻止发送。')
        result = self.native.command(request)
        if self._host_provider and (type(result) is not int or result not in (0, 1)):
            raise RuntimeError('Orca 队列接口未接受指令。')
        return result

    def watch(self, device_id):
        self._ensure_open()
        if not device_id:
            return
        if not isinstance(device_id, str) or len(device_id) > 256:
            raise ValueError('打印机编号无效。')
        with self._watch_lock:
            watched = self._watch_ids if self._host_provider else self.native.watch_ids
            if len(watched) >= 32 and device_id not in watched:
                raise ValueError('最多同时监控 32 台打印机。')
            watched.add(device_id)

    def _sync_host_watch(self, devices):
        if not self._host_provider:
            return
        with self._watch_lock:
            watched = set(self._watch_ids)
        if watched:
            ids = sorted(d['id'] for d in devices if d['id'] in watched and canonical_model(d['model']))
            result = self.native.command(dict(action='watch_many', request_id='watch_queue_devices', device_ids=ids))
            if type(result) is not int or result not in (0, 1):
                raise RuntimeError('Orca 未接受队列打印机状态订阅。')

    def snapshot(self):
        empty = dict(available=False, can_submit=False, devices=[], connection_mode=self.mode,
                     reason='当前 Orca 未提供原生队列桥接；Open Bamboo 联网正常也不会自动向页面开放设备和 AMS。')
        try:
            self._ensure_open()
            raw = self.native.snapshot()
            if not isinstance(raw, dict) or type(raw.get('protocol')) is not int or raw['protocol'] != 1 or raw.get('origin') != ('orca-owned-cloud' if self.mode == 'owned_cloud' else 'orca-native-queue'):
                raise ValueError('桥接协议不匹配。')
            if raw.get('cloud_session_reused') is not (self.mode == 'native'):
                raise ValueError('队列连接的会话归属不匹配。')
            if self.mode == 'owned_cloud' and raw.get('attached') is not True:
                raise RuntimeError('插件独立云连接尚未初始化。')
            if self._host_provider and raw.get('attached') is not True:
                raise RuntimeError('Orca 队列接口尚未接入当前连接。')
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
            if raw.get('can_submit') is True and raw.get('prototype') is not True:
                self._sync_host_watch(devices)
            return dict(available=True, can_submit=raw.get('can_submit') is True and raw.get('prototype') is not True, devices=devices, commands=commands,
                        connection_mode=self.mode,
                        material_mapping_ready=raw.get('material_mapping_ready') is True,
                        upload_busy=raw.get('upload_busy') is True,
                        refreshing=raw.get('refreshing') is True,
                        reason=raw.get('refresh_error') or ('设备列表读取中…' if raw.get('refreshing') and not devices else ('插件独立云连接已连接。' if self.mode == 'owned_cloud' else '原生桥接已连接，复用 Orca 云端会话。')))
        except NativeBridgeBindingError as exc:
            empty['reason'] = str(exc)
            empty['error_code'] = 'native_binding_failed'
            return empty
        except RuntimeError as exc:
            empty['reason'] = str(exc)
            return empty
        except Exception:
            empty['reason'] = '原生设备桥接返回无效信息，已停止使用设备列表。'
            return empty
