"""Source fragment appended to a standalone Orca plugin by build_plugin.py."""
from local_paths import fs_path, canonical_path, replace_file
import copy
import json
import os
import re
import struct
import threading
import time
import uuid
from pathlib import Path
import orca
from queue_core import inspect_plate
from queue_domain import fresh_queue, blank_print_settings, configure_print_settings, find_device, material_signature, setup_report, validate_print_settings
from printer_models import canonical_model, supports_auto_swap
from printer_connection import PrinterConnection
from queue_engine import QueueService
from queue_fleet import QueueFleet
from queue_imports import LocalImports
from swap_support import DEFAULT_SWAP_FILE, inspect_swap_file, swap_plan
from release_info import QUEUE_VERSION, QUEUE_BUILD_ID
from page_assets import QUEUE_PAGE_HTML
from page_preferences import PagePreferences

# Enabled only by the explicitly separate standalone test-wheel builder.
OWNED_CLOUD = False
if OWNED_CLOUD:
    from owned_connection import OwnedCloudConnection, private_process_command

if os.name != 'nt' or struct.calcsize('P') != 8:
    raise RuntimeError('Orca Plate Queue 仅支持 Windows x64。')


class PrintQueuePage(orca.pages.PagesPluginCapabilityBase):
    def get_name(self):
        return '打印队列'

    def get_icon(self):
        return str(canonical_path(Path(__file__).with_name('queue_tab.svg')))

    def get_ui(self):
        return QUEUE_PAGE_HTML

    def get_default_config(self):
        return fresh_queue(DEFAULT_SWAP_FILE)

    def _swap_settings(self):
        default = dict(path=DEFAULT_SWAP_FILE, nozzle=.4, enabled=True, validated=False,
                       settings=blank_print_settings(self._data['device_id']))
        default.update(self._data.get('a1_swap', {}))
        return default

    def _validate_saved_swap(self):
        saved = self._swap_settings()
        checked = inspect_swap_file(saved['path'], saved['nozzle'])
        if saved.get('sha256') and saved['sha256'] != checked['sha256']:
            raise ValueError('换盘文件自上次保存后已经变化；请重新选择并保存，核对后再使用。')
        return checked

    @property
    def _data(self):
        return self._service.data

    def on_load(self):
        if hasattr(self, '_fleet'):
            self._fleet.close()
        elif hasattr(self, '_service'):
            self._service.close()
        if hasattr(self, '_connection'):
            self._connection.close()
        self._pending = []
        self._pending_lock = threading.Lock()
        self._error = ''
        self._last_export = ''
        self._messages = []
        self._connection = PrinterConnection(None if OWNED_CLOUD else orca.host)
        try:
            self._storage = str(orca.host.plugin.storage())
            self._preferences = PagePreferences(self._storage)
            if OWNED_CLOUD:
                self._connection = PrinterConnection(None, provider=OwnedCloudConnection(self._storage), mode='owned_cloud')
            self._fleet = QueueFleet(Path(self._storage) / ('v4-cloud' if OWNED_CLOUD else 'v3'), self._connection,
                inspect_plate, inspect_swap_file, DEFAULT_SWAP_FILE, service_factory=QueueService)
            self._service = self._fleet.selected
            self._imports = LocalImports(lambda: self._storage, self._stage_import)
            if OWNED_CLOUD:
                self._connection.native.start()
        except Exception as exc:
            self._error = '队列初始化失败：' + str(exc)

    def _ensure(self):
        if not hasattr(self, '_error'):
            self.on_load()
        if self._error:
            raise ValueError(self._error)

    def on_unload(self):
        if hasattr(self, '_imports'):
            self._imports.close()
        if hasattr(self, '_fleet'):
            self._fleet.close()
        elif hasattr(self, '_service'):
            self._service.close()
        if hasattr(self, '_connection'):
            self._connection.close()

    def _commit(self, mutate):
        self._ensure()
        self._service.commit(mutate)

    def _stage_import(self, path, copies=1, automatic=False, display_name=None):
        if not isinstance(path, str) or not path.strip():
            raise ValueError('请填写单盘切片 .3mf 的完整文件路径。')
        if type(copies) is not int or not 1 <= copies <= 100:
            raise ValueError('份数范围为 1–100。')
        info = inspect_plate(path.strip().strip('"'))
        if display_name:
            info['name'] = display_name
        existing = self._data['jobs'] + self._data.get('drafts', [])
        if automatic and any(j.get('source_path') == info['path'] and j['sha256'] == info['sha256'] for j in existing):
            return '同一文件内容已导入，忽略重复导出通知。'
        if len(self._data.get('drafts', [])) >= 100:
            raise ValueError('待配置文件已达 100 个，请先配置或取消部分导入。')
        info = self._service.freeze(info)
        info.update(id=uuid.uuid4().hex, copies=copies, object_count=len(info['objects']), settings=blank_print_settings(self._data['device_id']))
        try:
            self._commit(lambda: self._data.setdefault('drafts', []).append(info))
        except Exception:
            self._cleanup_copy(info)
            raise
        if display_name:
            raw = canonical_path(info['source_path'])
            if raw.parent == canonical_path(Path(self._storage)/'queue_uploads') and re.fullmatch(r'queue-upload-[0-9a-f]{32}\.3mf', raw.name):
                fs_path(raw).unlink(missing_ok=True)
        return f"已读取：{info['name']} × {copies}。请配置耗材后确认加入队列。"

    def _commit_import(self, data, connection):
        drafts = self._data.get('drafts', [])
        source = next((d for d in drafts if d['id'] == data.get('id')), None)
        if source is None:
            raise ValueError('待加入文件已变化，请重新选择。')
        copies = data.get('copies', source['copies'])
        if type(copies) is not int or not 1 <= copies <= 100:
            raise ValueError('加入份数须为 1–100 的整数。')
        targets = data.get('apply_to', [])
        if (not isinstance(targets, list) or len(targets)>100 or any(not isinstance(i,str) for i in targets)
                or len(set(targets))!=len(targets) or source['id'] in targets):
            raise ValueError('批量加入的文件编号无效。')
        checked = configure_print_settings(source, data.get('settings'), connection, self._data['device_id'], source.get('settings'))
        selected = [source]
        for target_id in targets:
            target = next((d for d in drafts if d['id'] == target_id), None)
            if target is None or material_signature(target) != material_signature(source):
                raise ValueError('批量加入的文件已变化或切片耗材不同。')
            selected.append(target)
        for draft in selected:
            if self._service.digest(draft['path']) != draft['sha256']:
                raise ValueError('待加入的文件副本已变化，请取消后重新导入。')
            validate_print_settings(draft, checked, connection, self._data['device_id'], require_ready=False)
        ids = {d['id'] for d in selected}
        quantities = {d['id']: copies if d['id']==source['id'] else d['copies'] for d in selected}
        def change():
            for draft in selected:
                if draft.get('thumbnail'):
                    self._data['previews'][draft['sha256']] = draft['thumbnail']
                for _ in range(quantities[draft['id']]):
                    row = copy.deepcopy(draft)
                    row.pop('copies', None)
                    row.pop('thumbnail', None)
                    row.update(id=uuid.uuid4().hex, status='等待', settings=copy.deepcopy(checked))
                    self._data['jobs'].append(row)
            self._data['drafts'] = [d for d in drafts if d['id'] not in ids]
        self._commit(change)
        return '耗材设置已保存，已加入 '+str(sum(quantities.values()))+' 盘任务；尚未开始打印。'

    def on_lifecycle_event(self, event, ctx):
        # Worker callbacks must not read external files, prompt or perform I/O.
        # Main-page polling drains candidates after the export finishes.
        if event == orca.LifecycleEvent.GCodeExportFinished and ctx.code == orca.LifecycleEvtCode.Ok:
            path = str(getattr(ctx, 'msg', '') or getattr(ctx, 'name', ''))
            if not hasattr(self, '_pending_lock'):
                return
            with self._pending_lock:
                if len(self._pending) < 20:
                    self._pending.append((path, self._data['device_id']))

    def _cleanup_copy(self, row):
        if any(j['sha256']==row['sha256'] for j in self._data['jobs']+self._data.get('drafts', [])) or self._data['a1_swap'].get('sha256')==row['sha256']:
            return
        try:
            target=canonical_path(row['path'])
            if target.parent==canonical_path(self._service.assets) and re.fullmatch(r'[0-9a-f]{64}\.3mf',target.name):
                fs_path(target).unlink(missing_ok=True)
        except OSError:
            self._messages.append('任务已删除，但本地副本清理失败。')

    def _drain(self):
        with self._pending_lock:
            pending = self._pending[:]
            self._pending.clear()
        for candidate in pending:
            path, queue_id = candidate if isinstance(candidate, tuple) else (candidate, self._data['device_id'])
            self._last_export = path
            target = self._fleet.services.get(queue_id)
            if target is None or not target.data.get('auto_export'):
                continue
            if not path.lower().endswith('.3mf'):
                self._messages.append('Orca 此次只报告内部 G-code 路径；无法据此确认最终单盘 3MF。请导出后在本页填写最终文件路径入队。')
                continue
            try:
                selected = self._service
                self._service = target
                try:
                    self._messages.append(self._stage_import(path, automatic=True))
                finally:
                    self._service = selected
            except Exception as exc:
                self._messages.append('自动入队未执行：' + str(exc))
        self._messages = self._messages[-10:]

    def on_message(self, message):
        try:
            data = message if isinstance(message, dict) else json.loads(message)
            if data.get('action') == 'retry_initialize':
                if getattr(self, '_error', ''):
                    self.on_load()
                data = dict(data, action='refresh')
            self._ensure()
            with self._fleet.lock:
                with self._service.lock:
                    self._handle_message(data)
        except Exception as exc:
            request_id = data.get('request_id') if isinstance(locals().get('data'), dict) else None
            self.post_message(dict(type='error', request_id=request_id, success=False, note=str(exc),
                                   initialization_failed=bool(getattr(self, '_error', ''))))

    def _handle_message(self, message):
        request_id = None
        try:
            self._ensure()
            data = message if isinstance(message, dict) else json.loads(message)
            request_id = data.get('request_id')
            action = data.get('action', 'refresh')
            if action == 'set_language':
                self._preferences.set_language(data.get('language'))
                self.post_message(dict(type='preferences', action=action, request_id=request_id, success=True,
                    language=self._preferences.language, language_revision=self._preferences.revision))
                return
            if data.get('queue_id', self._data['device_id']) != self._data['device_id']:
                raise ValueError('界面已切换打印机，请在当前打印机页面重新操作。')
            if action == 'refresh_devices':
                self._connection.watch(data.get('device_id') or self._data['device_id'])
                self._connection.refresh()
            connection = self._connection.snapshot()
            note = ''
            if action in ('cloud_browser_begin', 'cloud_browser_open', 'cloud_browser_cancel', 'cloud_logout', 'cloud_reconnect'):
                if not OWNED_CLOUD:
                    raise ValueError('当前安装版本未启用独立云连接。')
                active = any(s.data.get('running') or s.data.get('active') for s in self._fleet.services.values())
                running = any(s.data.get('running') for s in self._fleet.services.values())
                if (action != 'cloud_reconnect' and active) or (action == 'cloud_reconnect' and running):
                    raise ValueError('请先暂停所有队列，并核对未结束任务后再更改连接。')
                self._connection.native.auth_action(action.removeprefix('cloud_'), data)
                note = '正在处理连接请求…'
            elif action in ('connection_install','connection_restore'):
                raise ValueError('队列插件不安装或恢复联网文件。请退出 Orca 后使用独立连接组件安装器。')
            elif action in ('upload_begin', 'upload_chunk', 'upload_end', 'upload_abort'):
                result = self._imports.handle(action, dict(data, queue_id=self._data['device_id']))
                if not result.get('complete'):
                    self.post_message(dict(type='upload', action=action, request_id=request_id,
                                           success=True, upload=result))
                    return
                note = result['note']
            elif action == 'add':
                note = self._stage_import(data.get('path'), data.get('copies', 1))
            elif action == 'commit_import':
                note = self._commit_import(data, connection)
            elif action == 'discard_import':
                draft = next((d for d in self._data.get('drafts', []) if d['id']==data.get('id')), None)
                if draft is None:
                    raise ValueError('待加入文件已变化。')
                self._commit(lambda: self._data.update(drafts=[d for d in self._data.get('drafts', []) if d['id']!=draft['id']]))
                self._cleanup_copy(draft)
                note = '已取消此文件的导入，源文件保留。'
            elif action == 'move':
                jobs = self._data['jobs']
                source = next((i for i,j in enumerate(jobs) if j['id'] == data.get('id')), None)
                target = next((i for i,j in enumerate(jobs) if j['id'] == data.get('target_id')), None)
                placement = data.get('placement')
                if source is None or target is None or placement not in ('before', 'after'):
                    raise ValueError('拖动目标已变化，请刷新后重试。')
                if any(j['status'] != '等待' for j in jobs[min(source,target):max(source,target)+1]):
                    raise ValueError('只能调整等待中的任务，不能跨过正在执行的任务。')
                def change():
                    if source == target:
                        return
                    row = jobs.pop(source)
                    index = next(i for i,j in enumerate(jobs) if j['id'] == data['target_id'])
                    jobs.insert(index + (placement == 'after'), row)
                self._commit(change)
            elif action in ('remove', 'up', 'down'):
                rowid = data.get('id')
                index = next((i for i, r in enumerate(self._data['jobs']) if r['id'] == rowid), None)
                if index is None:
                    raise ValueError('请先选择一个任务。')
                allowed = ('等待','已完成','已中止') if action=='remove' else ('等待',)
                if self._data['jobs'][index]['status'] not in allowed or (self._data.get('active') or {}).get('job_id')==rowid:
                    raise ValueError('执行中的任务不能删除或移动。')
                removed_row = copy.deepcopy(self._data['jobs'][index]) if action == 'remove' else None
                def change():
                    jobs = self._data['jobs']
                    if action == 'remove':
                        removed = jobs.pop(index)
                        if not any(j['sha256'] == removed['sha256'] for j in jobs):
                            self._data.get('previews', {}).pop(removed['sha256'], None)
                    else:
                        other = index + (-1 if action == 'up' else 1)
                        if 0 <= other < len(jobs) and jobs[other]['status'] == '等待':
                            jobs[index], jobs[other] = jobs[other], jobs[index]
                self._commit(change)
                if removed_row:
                    self._cleanup_copy(removed_row)
            elif action == 'auto':
                if type(data.get('enabled')) is not bool:
                    raise ValueError('无效的自动入队开关。')
                self._commit(lambda: self._data.update(auto_export=data['enabled']))
            elif action in ('bind_device', 'select_queue'):
                if self._imports.pending:
                    raise ValueError('文件仍在导入，请完成后再切换打印机队列。')
                self._service = self._fleet.select(data.get('device_id'), connection)
                self._connection.watch(self._data['device_id'])
                note = '已切换到这台打印机的独立队列；其他打印机继续各自运行。'
            elif action == 'save_settings':
                is_swap = data.get('id') == '__swap__'
                row = self._swap_settings() if is_swap else next((j for j in self._data['jobs'] if j['id'] == data.get('id')), None)
                if row is None or (not is_swap and row['status'] != '等待'):
                    raise ValueError('任务不存在或已不能修改。')
                if is_swap:
                    if self._data['running'] or self._data['active']:
                        raise ValueError('执行中不能更改换盘打印设置。')
                    row = self._validate_saved_swap()
                checked = configure_print_settings(row, data.get('settings'), connection, self._data['device_id'], row.get('settings'))
                target_ids = data.get('apply_to', [])
                if not isinstance(target_ids, list) or len(target_ids)>1000 or any(not isinstance(i,str) for i in target_ids) or len(set(target_ids))!=len(target_ids):
                    raise ValueError('批量应用的任务列表无效。')
                if is_swap and target_ids:
                    raise ValueError('换盘任务的设置需独立保存。')
                targets = []
                for target_id in target_ids:
                    target = next((j for j in self._data['jobs'] if j['id']==target_id), None)
                    if target is None or target['status']!='等待' or target_id==data.get('id') or material_signature(target)!=material_signature(row):
                        raise ValueError('所选任务已变化或切片耗材不同，请重新选择要应用的任务。')
                    validate_print_settings(target, checked, connection, self._data['device_id'], require_ready=False)
                    targets.append(target)
                def change():
                    if is_swap:
                        self._data['a1_swap']['settings'] = checked
                    else:
                        row['settings'] = checked
                        for target in targets:
                            target['settings'] = copy.deepcopy(checked)
                self._commit(change)
                note = ('已保存 '+str(1+len(targets))+' 盘打印设置。' if targets else '打印设置已保存。') + '开始前会重新检查装料状态。'
            elif action == 'object_preview':
                preview = self._service.object_preview(data.get('id'))
                self.post_message(dict(type='object_preview', action=action, request_id=request_id,
                                       queue_id=self._data['device_id'], job_id=data.get('id'),
                                       success=True, preview=preview))
                return
            elif action == 'preflight':
                if data.get('completion_review') is True:
                    self._service.completion_review(connection,data.get('attempt_id'))
                elif data.get('for_start') is True:
                    self._service._idle(connection)
                if data.get('completion_review') is not True:
                    self._service.preflight(connection, need_swap=data.get('swap_first') is True)
                note = '文件、真实打印机、逐盘耗材和独立换盘任务检查通过。'
            elif action == 'start':
                self._service.start(connection, data.get('bed_clear') is True, data.get('swap_first') is True)
                note = '队列已启动。'
            elif action in ('end_current','stop_queue'):
                self._service.stop(connection, continue_queue=action=='end_current')
                note = '已记录停止意图，等待实机回报。'
            elif action in ('pause_print','resume_print','skip_objects'):
                native_action={'pause_print':'pause','resume_print':'resume','skip_objects':'skip'}[action]
                self._service.control(connection, native_action, data.get('objects'))
                note = '操作已提交，等待设备确认。'
            elif action == 'resume_monitor':
                self._service.resume_monitor(connection)
                note = '已恢复当前任务监控，没有重发文件。'
            elif action == 'complete_continue':
                self._service.complete_continue(connection,data.get('attempt_id'),data.get('confirmed') is True)
                note = '已确认本盘完成，按本机换板方式继续；未重发本盘。'
            elif action == 'reconcile':
                if data.get('checked_pending') is not True:
                    raise ValueError('请先确认打印机和 Handy 中没有待启动任务。')
                self._service.reconcile(connection, data.get('bed_clear') is True)
                note = '已记录人工核对结果。'
            elif action == 'confirm_plate':
                self._service.confirm_plate(connection)
                note = '新打印板已确认，继续队列。'
            elif action == 'swap_mode':
                if type(data.get('automatic')) is not bool:
                    raise ValueError('换盘继续方式无效。')
                if self._data['running'] or self._data['active']:
                    raise ValueError('请在开始前设置换盘继续方式。')
                self._commit(lambda: self._data.update(auto_after_swap=data['automatic']))
            elif action == 'duplicate':
                original = self._service.job(data.get('id'))
                def duplicate():
                    row = copy.deepcopy(original)
                    row.update(id=uuid.uuid4().hex, status='等待')
                    self._data['jobs'].append(row)
                self._commit(duplicate)
                note = '已新增一份独立的等待任务；原执行记录保留。'
            elif action == 'export_report':
                report = self._service.snapshot()
                report.pop('previews', None)
                target = Path(self._storage) / ('queue-report-' + time.strftime('%Y%m%d-%H%M%S') + '.json')
                fs_path(target).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
                note = '运行记录已保存：' + str(target)
            elif action == 'verify':
                for row in self._data['jobs']:
                    if data.get('id') and row['id'] != data['id']:
                        continue
                    info = inspect_plate(row['path'])
                    if info['sha256'] != row['sha256']:
                        raise ValueError('文件已被修改，请移出后重新入队：' + row['name'])
                note = '文件校验通过。此操作没有发送到打印机。'
            elif action in ('save_swap', 'default_swap'):
                if self._data['running'] or self._data['active']:
                    raise ValueError('队列执行中不能更换换盘程序。')
                mode = data.get('plate_mode', self._data.get('plate_mode', 'automatic'))
                if mode not in ('automatic', 'manual'):
                    raise ValueError('请选择手动或自动换盘。')
                selected_device = find_device(connection, self._data['device_id'])
                if mode == 'automatic' and self._data['device_id'] and not supports_auto_swap((selected_device or {}).get('model')):
                    raise ValueError('此机型没有自动换盘，请使用每盘结束后手动换板确认。')
                if action == 'default_swap' and self._data['device_id'] and canonical_model((find_device(connection,self._data['device_id']) or {}).get('model')) != 'N2S':
                    raise ValueError('套件默认换盘文件仅适用于 A1；其他机型请使用对应的独立程序。')
                if mode == 'manual':
                    self._commit(lambda:self._data.update(plate_mode='manual',auto_after_swap=False))
                    note = '本机已设为手动换盘，每盘结束后等待确认新板就位。'
                    self._drain()
                    self._post_state(action, request_id, note, connection)
                    return
                path = DEFAULT_SWAP_FILE if action == 'default_swap' else data.get('path')
                nozzle = .4 if action == 'default_swap' else data.get('nozzle', .4)
                enabled = data.get('enabled', True)
                if type(enabled) is not bool:
                    raise ValueError('无效的换盘计划开关。')
                checked = self._service.freeze(inspect_swap_file(path, nozzle))
                device = find_device(connection, self._data['device_id'])
                if (self._data['device_id'] and (not device or canonical_model(checked['printer']) != canonical_model(device['model']))) or (not self._data['device_id'] and canonical_model(checked['printer']) != 'N2S'):
                    raise ValueError('换盘程序的机型与当前打印机不一致。')
                automatic = data.get('automatic', self._data.get('auto_after_swap', False))
                if type(automatic) is not bool:
                    raise ValueError('无效的换盘继续方式。')
                previous = self._swap_settings()
                print_settings = (copy.deepcopy(previous['settings']) if previous.get('sha256')==checked['sha256'] and previous.get('nozzle')==checked['nozzle']
                                  else blank_print_settings(self._data['device_id']))
                self._commit(lambda: self._data.update(plate_mode='automatic',a1_swap=dict(checked, enabled=enabled,
                    settings=print_settings), auto_after_swap=automatic))
                note = 'A1 换盘文件已保存并通过静态校验，尚未执行机器动作。'
            elif action == 'check_swap':
                checked = self._validate_saved_swap()
                note = '换盘文件有效：' + checked['name'] + '。机型 A1，喷嘴 ' + str(checked['nozzle']) + ' mm；未执行换盘。'
            elif action not in ('refresh','refresh_devices','connection_status'):
                raise ValueError('不支持的队列操作。')
            self._drain()
            self._post_state(action, request_id, note, connection)
        except Exception as exc:
            self.post_message(dict(type='error', request_id=request_id, success=False, note=str(exc)))

    def _post_state(self, action, request_id, note, connection):
        with self._service.lock:
            self.post_message(dict(type='state', action=action, request_id=request_id, queue_id=self._data['device_id'],
                                   build_id=QUEUE_BUILD_ID, language=self._preferences.language, language_revision=self._preferences.revision,
                                   fleet=self._fleet.snapshot(connection), success=True, note=note, data=self._service.snapshot(),
                                   messages=self._messages + self._data.get('events',[]), last_export=self._last_export,
                                   swap_settings=self._swap_settings(),
                                   connection_mode='owned_cloud' if OWNED_CLOUD else 'external', version=QUEUE_VERSION,
                                   cloud_auth=self._connection.native.status() if OWNED_CLOUD else None,
                                   default_swap_available=bool(DEFAULT_SWAP_FILE),
                                   swap_plan=swap_plan(self._data['jobs'], self._swap_settings()) if self._data.get('plate_mode','automatic')=='automatic' else [], connection=connection,
                                   setup={j['id']: setup_report(j, j['settings'], connection, self._data['device_id']) for j in self._data['jobs']},
                                   swap_setup=setup_report(self._swap_settings(), self._swap_settings()['settings'], connection, self._data['device_id'])))


@orca.plugin
class PrintQueuePlugin(orca.base):
    def register_capabilities(self):
        if hasattr(orca, 'request_permissions'):
            if OWNED_CLOUD:
                executable = str(Path(__file__).with_name('native-bin') / 'orca_queue_host.exe')
                orca.request_permissions(threading=True, process=[private_process_command(executable)],
                    network_http=['http://127.0.0.1', 'https://api.bambulab.cn', 'https://api.bambulab.com', 'https://bambulab.cn'],
                    network_socket=['api.bambulab.cn:443', 'api.bambulab.com:443', 'bambulab.cn:443',
                                    'cn.mqtt.bambulab.com:8883', 'us.mqtt.bambulab.com:8883'])
            else:
                orca.request_permissions(threading=True)
        orca.register_capability(PrintQueuePage)
