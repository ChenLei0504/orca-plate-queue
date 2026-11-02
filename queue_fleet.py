"""Separate durable executors per printer, sharing only the cloud upload lane."""
from local_paths import fs_path, canonical_path, replace_file
import copy
import hashlib
import json
import os
from pathlib import Path
import threading
from contextlib import contextmanager
from printer_models import canonical_model, supports_auto_swap
from queue_domain import blank_print_settings, bind_queue, find_device
from queue_engine import QueueService


class FleetConnection:
    def __init__(self, source):
        self.source = source
        self.lock = threading.RLock()
        self.pending_upload = ''

    def snapshot(self):
        return self.source.snapshot()

    def watch(self, device_id):
        self.source.watch(device_id)

    def refresh(self):
        return self.source.refresh()

    def command(self, request):
        if request.get('action') == 'submit':
            with self.lock:
                self.pending_upload = request['request_id']
                return self.source.command(request)
        return self.source.command(request)

    @contextmanager
    def upload_slot(self):
        with self.lock:
            snapshot = self.source.snapshot()
            records = snapshot.get('commands', [])
            busy = snapshot.get('upload_busy') is True or any(
                r.get('action') == 'submit' and r.get('status') == 'working' for r in records)
            if self.pending_upload:
                record = next((r for r in records if r.get('request_id') == self.pending_upload), None)
                if (record and record.get('status') in ('sent', 'failed')) or snapshot.get('upload_busy') is False:
                    self.pending_upload = ''
                else:
                    busy = True
            yield not busy


class QueueFleet:
    def __init__(self, root, connection, inspect_model, inspect_swap, default_swap, service_factory=QueueService):
        self.root = canonical_path(root)
        self.connection = FleetConnection(connection)
        self.lock = threading.RLock()
        self.services = {}
        self._factory = service_factory
        self._inspect_model, self._inspect_swap, self._default = inspect_model, inspect_swap, default_swap
        self.index = self.root / 'fleet-v1.json'
        self.primary = self._open(self.root)
        self.services[self.primary.data['device_id']] = self.primary
        try:
            index = json.loads(fs_path(self.index).read_text(encoding='utf8')) if fs_path(self.index).exists() else {}
            ids = index.get('devices', [])
            if not isinstance(ids, list) or len(ids)>32 or any(not isinstance(i,str) or not 0<len(i)<=128 for i in ids):
                raise ValueError('多打印机队列目录无效，请核对备份。')
            for device_id in ids:
                if device_id in self.services:
                    continue
                service = self._open(self._device_root(device_id))
                if service.data['device_id'] != device_id:
                    service.close()
                    raise ValueError('打印机队列目录与设备身份不符。')
                self.services[device_id] = service
            self.selected_id = index.get('selected', self.primary.data['device_id'])
            if self.selected_id not in self.services:
                self.selected_id = self.primary.data['device_id']
        except Exception:
            self.close()
            raise

    def _device_root(self, device_id):
        return self.root / 'printers' / hashlib.sha256(device_id.encode('utf8')).hexdigest()

    def _open(self, folder):
        return self._factory(folder, self.connection, self._inspect_model, self._inspect_swap, self._default)

    def _save_index(self, selected):
        payload = dict(devices=[i for i in self.services if i], selected=selected)
        temp = self.index.with_suffix('.part')
        try:
            with fs_path(temp).open('w', encoding='utf8') as stream:
                json.dump(payload, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            replace_file(temp, self.index)
        finally:
            fs_path(temp).unlink(missing_ok=True)

    def select(self, device_id, connection):
        with self.lock:
            if not isinstance(device_id, str) or not 0<len(device_id)<=128:
                raise ValueError('请选择实际打印机。')
            if device_id not in self.services:
                device = find_device(connection, device_id)
                model = canonical_model(device.get('model')) if device else ''
                if not connection.get('available') or not model:
                    raise ValueError('未在当前云端设备列表中找到受支持的打印机。')
                if len(self.services) >= 32:
                    raise ValueError('最多管理 32 台打印机。')
                if self.primary.data['device_id'] == '':
                    service = self.primary
                    service.commit(lambda:bind_queue(service.data, device_id, connection))
                    del self.services['']
                else:
                    service = self._open(self._device_root(device_id))
                    if service.data['device_id'] not in ('', device_id):
                        service.close()
                        raise ValueError('本地队列与打印机身份不符。')
                    def bind():
                        service.data.update(device_id=device_id, device_name=device['name'], printer_model=model,
                            plate_mode='automatic' if model=='N2S' else 'manual')
                        if model != 'N2S':
                            service.data['a1_swap'].update(path='', source_path='', enabled=False, validated=False,
                                                          settings=blank_print_settings(device_id))
                    service.commit(bind)
                service.commit(lambda:service.data.update(device_name=device['name'], printer_model=model,
                    plate_mode=service.data.get('plate_mode', 'automatic' if model=='N2S' else 'manual')))
                if model != 'N2S':
                    service.commit(lambda:service.data['a1_swap'].update(path='',source_path='',enabled=False,settings=blank_print_settings(device_id)))
                self.services[device_id] = service
            self._save_index(device_id)
            self.selected_id = device_id
            self.connection.watch(device_id)
            return self.services[device_id]

    @property
    def selected(self):
        return self.services[self.selected_id]

    def snapshot(self, connection):
        rows = []
        for device_id, service in self.services.items():
            if not device_id:
                continue
            state = service.snapshot()
            device = find_device(connection, device_id) or {}
            rows.append(dict(id=device_id, name=device.get('name') or state.get('device_name') or '打印机',
                model=device.get('model') or state.get('printer_model',''), online=device.get('online') is True,
                running=state['running'], phase=state['phase'], reason=state.get('reason',''),
                active=bool(state['active']), pending=sum(j['status']=='等待' for j in state['jobs']),
                monitor_stage=((state.get('active') or {}).get('monitor') or {}).get('stage',''),
                supports_swap=supports_auto_swap(device.get('model') or state.get('printer_model')),
                drafts=len(state.get('drafts', [])),
                completed=sum(j['status']=='已完成' for j in state['jobs'])))
        return rows

    def close(self):
        seen = set()
        for service in self.services.values():
            if id(service) not in seen:
                seen.add(id(service))
                service.close()
