"""Persistent queue executor. No Orca UI/config APIs are called by its worker."""
from local_paths import fs_path, canonical_path, replace_file
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import threading
import time
import uuid
from queue_domain import blank_print_settings, find_device, validate_print_settings
from printer_models import supports_auto_swap
from object_preview import inspect_object_preview
from task_monitor import new_monitor, reduce_task, strong_identity, matches_task


class QueueService:
    ACTIVE = {'RUNNING', 'PREPARE', 'SLICING', 'PAUSE'}
    IDLE = {'IDLE', 'FINISH', 'FAILED'}

    def __init__(self, storage, connection, inspect_model, inspect_swap, default_swap, start_worker=True, clock=time.time, asset_storage=None, asset_owner=None):
        self.root = canonical_path(storage)
        fs_path(self.root).mkdir(parents=True, exist_ok=True)
        self.assets = canonical_path(asset_storage) if asset_storage is not None else self.root / 'assets'
        fs_path(self.assets).mkdir(parents=True, exist_ok=True)
        self._lease = fs_path(self.root / 'executor.lock').open('a+b')
        self._lease.seek(0)
        if os.name == 'nt':
            import msvcrt
            try:
                msvcrt.locking(self._lease.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                self._lease.close()
                raise ValueError('已有另一个 Orca 窗口在管理这条队列，请先关闭原窗口的队列插件。') from None
        self.connection, self.inspect_model, self.inspect_swap = connection, inspect_model, inspect_swap
        self.clock = clock
        self.lock = threading.RLock()
        self.closed = threading.Event()
        self.fatal = ''
        self.db = None
        try:
            if asset_storage is not None:
                if not isinstance(asset_owner, str) or not re.fullmatch(r'[0-9a-f]{64}', asset_owner):
                    raise ValueError('缓存所属队列标记无效。')
                owner = fs_path(self.assets / 'owner')
                if not owner.exists():
                    if any(fs_path(self.assets).iterdir()):
                        raise ValueError('缓存目录缺少所属队列标记，已停止使用。')
                    with owner.open('x', encoding='ascii') as stream:
                        stream.write(asset_owner)
                        stream.flush()
                        os.fsync(stream.fileno())
                if owner.read_text(encoding='ascii') != asset_owner:
                    raise ValueError('缓存目录属于另一条队列，已停止使用。')
            self.db = sqlite3.connect(str(fs_path(self.root / 'queue-v3.sqlite3')), check_same_thread=False)
            self.db.execute('PRAGMA journal_mode=WAL')
            self.db.execute('PRAGMA synchronous=FULL')
            self.db.execute('CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)')
            row = self.db.execute('SELECT payload FROM state WHERE id=1').fetchone()
            self.data = json.loads(row[0]) if row else dict(
                schema=3, jobs=[], previews={}, auto_export=False, device_id='', running=False,
                phase='paused', reason='请加入任务并配置打印机。', active=None, dirty_plate=False,
                auto_after_swap=False, events=[], journal=[],
                a1_swap=dict(path=default_swap, source_path=default_swap, nozzle=.4, enabled=True,
                             validated=False, settings=blank_print_settings()))
            if self.data.get('schema') != 3:
                raise ValueError('开发版存档结构不符，请使用独立的 v3 存储目录。')
            if hasattr(connection, 'watch'):
                connection.watch(self.data['device_id'])
            if self.data['running'] or self.data['active']:
                self.data['running'] = False
                self.data['phase'] = 'recovery'
                self.data['reason'] = 'Orca 已重启或插件重新加载。请核对打印机，再选择继续监控或人工处理；不会自动重发。'
                self._note(self.data['reason'])
            self._save()
            self.worker = None
            if start_worker:
                self.worker = threading.Thread(target=self._loop, name='A1PlateQueue', daemon=True)
                self.worker.start()
        except Exception:
            if self.db is not None:
                self.db.close()
            self._lease.close()
            raise

    def _save(self):
        payload = json.dumps(self.data, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        with self.db:
            self.db.execute('INSERT INTO state VALUES (1,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload', (payload,))

    def commit(self, mutate):
        with self.lock:
            if self.fatal:
                raise ValueError(self.fatal)
            old = copy.deepcopy(self.data)
            try:
                mutate()
                self._save()
            except Exception:
                self.data = old
                raise

    def snapshot(self):
        with self.lock:
            result = copy.deepcopy(self.data)
            if self.fatal:
                result.update(running=False, reason=self.fatal, phase='recovery')
            return result

    def _note(self, message):
        self.data['events'].append(time.strftime('%m-%d %H:%M:%S') + ' ' + message)
        self.data['events'] = self.data['events'][-150:]

    def _hold(self, reason):
        def change():
            self.data.update(running=False, phase='recovery' if self.data['active'] else 'paused', reason=reason)
            self._note(reason)
        self.commit(change)

    def close(self):
        if self.closed.is_set():
            return
        self.closed.set()
        with self.lock:
            active = copy.deepcopy(self.data['active'])
            try:
                self._hold('队列服务已暂停。已开始的实机打印继续运行；重新加载后需核对任务。' if active else '队列已暂停，可以检查设置后开始。')
            except Exception:
                self.fatal='保存暂停状态失败，重新加载后需核对任务。'
        if active and not active.get('identity'):
            try:
                self.connection.command(dict(action='cancel_submit', request_id='cancel_'+uuid.uuid4().hex,
                                             target=active['request_id']))
            except Exception:
                pass
        if self.worker:
            self.worker.join(timeout=3)
        # Do not close the DB while a native poll is still returning to the worker.
        if not self.worker or not self.worker.is_alive():
            self.db.close()
            if os.name == 'nt':
                import msvcrt
                self._lease.seek(0)
                msvcrt.locking(self._lease.fileno(), msvcrt.LK_UNLCK, 1)
            self._lease.close()

    def freeze(self, info):
        """Keep immutable, content-addressed input; never re-open a user's file to print."""
        source = Path(info['path'])
        # Short filename, full SHA-256 still verified below before use or reuse.
        target = self.assets / (info['sha256'][:32] + '.3mf')
        legacy = self.assets / (info['sha256'] + '.3mf')
        if fs_path(legacy).exists():
            target = legacy
        if not fs_path(target).exists():
            pending = self.assets / (uuid.uuid4().hex + '.part')
            try:
                with fs_path(source).open('rb') as src, fs_path(pending).open('xb') as dst:
                    shutil.copyfileobj(src, dst, 1024*1024)
                    dst.flush()
                    os.fsync(dst.fileno())
                if self.digest(pending) != info['sha256']:
                    raise ValueError('导入期间源文件发生变化，请重新导入。')
                replace_file(pending, target)
            finally:
                fs_path(pending).unlink(missing_ok=True)
        if self.digest(target) != info['sha256']:
            raise ValueError('队列中的本地文件副本已变化。')
        result = copy.deepcopy(info)
        result.update(source_path=str(source), path=str(target))
        return result

    @staticmethod
    def digest(path):
        h = hashlib.sha256()
        with fs_path(path).open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024*1024), b''):
                h.update(chunk)
        return h.hexdigest()

    def job(self, job_id):
        row = next((j for j in self.data['jobs'] if j['id'] == job_id), None)
        if not row:
            raise ValueError('任务已不存在。')
        return row

    def object_preview(self, job_id):
        with self.lock:
            job = self.job(job_id)
            if self.digest(job['path']) != job['sha256']:
                raise ValueError('切片副本校验失败，已禁止按图片选择零件。')
            key = (job['sha256'], str(job['plate']), tuple(str(o['id']) for o in job['objects']))
            cache = getattr(self, '_object_previews', {})
            if key not in cache:
                if len(cache) >= 8:
                    cache.pop(next(iter(cache)))
                cache[key] = inspect_object_preview(job['path'], job['plate'], job['objects'])
                self._object_previews = cache
            return copy.deepcopy(cache[key])

    def waiting(self):
        return [j for j in self.data['jobs'] if j['status'] == '等待']

    def _device(self, connection):
        d = find_device(connection, self.data['device_id'])
        if not connection.get('available') or not d or not d['online'] or not d['cloud_connected'] or d['age_ms'] > 15000:
            raise ValueError('打印机断线、云端会话中断或状态过期；队列已暂停。')
        return d

    @staticmethod
    def _fault_reason(telemetry):
        details = []
        error = telemetry.get('print_error', 0)
        if error:
            label = f'0x{error:08X}' if type(error) is int and error >= 0 else str(error)
            details.append('打印错误 ' + label)
        count = telemetry.get('hms_count', 0)
        if count:
            details.append(f'{count:g} 条 HMS 设备告警' if type(count) in (int, float) else 'HMS 设备告警')
        return '；'.join(details)

    def _idle(self, connection):
        d = self._device(connection)
        if d['telemetry'].get('gcode_state') not in self.IDLE or d.get('state_age_ms', 1e9) > 15000:
            raise ValueError('需要打印机的最新空闲或已结束状态。')
        fault = self._fault_reason(d['telemetry'])
        if fault:
            raise ValueError('当前没有运行中的打印任务，但设备仍报告：' + fault + '。请在 Orca 的“设备 → 助手(HMS)”或 Handy 查看并处理；刷新后重新检查。')
        return d

    def _asset(self, asset, connection, swap=False):
        if self.digest(asset['path']) != asset['sha256']:
            raise ValueError('文件副本校验失败，已禁止发送：' + asset['name'])
        fresh = self.inspect_swap(asset['path'], asset['nozzle']) if swap else self.inspect_model(asset['path'])
        if fresh['sha256'] != asset['sha256']:
            raise ValueError('切片文件已变化。')
        settings = validate_print_settings(fresh, asset['settings'], connection, self.data['device_id'], require_send=True)
        return fresh, settings

    def preflight(self, connection, need_swap=False):
        with self.lock:
            self._device(connection)
            jobs = self.waiting()
            if not jobs:
                raise ValueError('没有等待中的任务。')
            for row in jobs:
                self._asset(row, connection)
            automatic = self.data.get('plate_mode', 'automatic') == 'automatic'
            if automatic and (len(jobs)>1 or need_swap) and not supports_auto_swap(self._device(connection)['model']):
                raise ValueError('此机型没有自动换盘，只能在每盘结束后手动更换打印板。')
            if need_swap and not automatic:
                raise ValueError('此打印机使用手动换盘，请先安装空白打印板后直接开始。')
            if automatic and (len(jobs) > 1 or need_swap):
                swap = self.data['a1_swap']
                if not swap.get('enabled') or not swap.get('validated'):
                    raise ValueError('连续换盘需要先保存并校验独立换盘文件。')
                self._asset(swap, connection, True)

    def start(self, connection, bed_clear=False, swap_first=False):
        with self.lock:
            if self.data['active']:
                raise ValueError('有未核对的执行记录，请使用“继续监控当前任务”或“确认任务已结束”。')
            self._idle(connection)
            self.preflight(connection, need_swap=swap_first)
            if not swap_first and bed_clear is not True:
                raise ValueError('开始前请确认已安装空白打印板，且换盘机构已经就绪。')
            def change():
                self.data.update(running=True, phase='between' if swap_first else 'ready', reason='', dirty_plate=bool(swap_first))
                self._note('换盘后继续队列。' if swap_first else '已确认空白打印板，开始队列。')
            self.commit(change)

    def resume_monitor(self, connection):
        with self.lock:
            a = self.data['active']
            if not a:
                raise ValueError('没有需要恢复监控的任务。')
            d = self._device(connection)
            result=reduce_task(a,d,self.clock())
            if result['decision'] in ('conflict','ambiguous'):
                raise ValueError(result['detail'])
            if not result['observed_running'] and d['telemetry'].get('gcode_state') in self.IDLE:
                raise ValueError('此前未记录到本盘实际开始打印，不能仅恢复监控。若本盘已成功，请选择“确认本盘已完成并继续”；若中止，请确认任务已结束。')
            identity=result['identity'] or self._identity(d,dict(a,identity={}))
            buffered_end=result['decision'] in ('completed','failed')
            if not buffered_end and not matches_task(d['telemetry'],a['tag'],identity):
                raise ValueError('当前实机任务身份不匹配，不能恢复。若已停止，请核对后选择“确认任务已结束”。')
            if result['observed_running'] and d['telemetry'].get('gcode_state') in ('FINISH','FAILED') and not buffered_end:
                # Explicit reattachment after a host restart establishes a new counter baseline.
                result['monitor'].update(run_event=d.get('state_event',0)-1,run_epoch=d.get('monitor_epoch',''))
                result['monitor'].update(baseline_event=d.get('state_event',0)-1,baseline_epoch=d.get('monitor_epoch',''))
            def change():
                a['monitor']=result['monitor']
                a['seen_running']=result['observed_running']
                a['identity'] = identity if result['observed_running'] else {}
                a['start_event'] = d.get('state_event', 0) - (1 if d['telemetry'].get('gcode_state') in ('FINISH','FAILED') and a['seen_running'] else 0)
                self.data.update(running=True, phase='stopping' if a.get('stop_intent') else 'monitoring', reason='')
                self._note('用户核对后恢复监控；未重发打印。')
            self.commit(change)

    def completion_review(self, connection, attempt_id):
        """Validate a user-reviewed completion without manufacturing a RUNNING event."""
        with self.lock:
            a=self.data['active']
            if self.data['running'] or not a or a['kind']!='model' or attempt_id!=a['request_id']:
                raise ValueError('待核对的打印任务已变化，请重新打开本盘完成检查。')
            d=self._idle(connection);t=d['telemetry']
            if t.get('gcode_state')!='FINISH' or type(t.get('mc_percent')) not in (int,float) or t['mc_percent']<100:
                raise ValueError('设备尚未回报本盘成功完成（FINISH / 100%），不能按成功完成继续。')
            identity=self._identity(d,a if a.get('seen_running') else dict(a,identity={}))
            if not identity:
                raise ValueError('设备当前任务名称或身份与本盘不符，请人工核对；不会继续换盘。')
            if a.get('stop_intent')=='pause':
                raise ValueError('本盘已要求停止整个队列，请先记录结束，再单独检查并开始后续任务。')
            for key in ('request_id','control_id'):
                receipt=self._receipt(connection,a.get(key))
                if receipt and receipt.get('status')=='working':
                    raise ValueError('本盘发送或操作还未结束，请稍后重新核对。')
            if self.waiting():
                self.preflight(connection,need_swap=self.data.get('plate_mode','automatic')=='automatic')
            return identity

    def complete_continue(self, connection, attempt_id, confirmed=False):
        with self.lock:
            if confirmed is not True:
                raise ValueError('请确认本盘实际打印成功、Handy 无待启动任务，且换盘机构及备板已就绪。')
            identity=self.completion_review(connection,attempt_id)
            # Keep the original observed-history bit; the operator confirmation is separate.
            self._finish(reviewed_identity=identity)

    def reconcile(self, connection, bed_clear):
        with self.lock:
            if self.data['running']:
                raise ValueError('先暂停队列，再进行人工核对。')
            self._idle(connection)
            a = self.data['active']
            if a:
                receipt = self._receipt(connection, a['request_id'])
                if receipt and receipt.get('status') == 'working':
                    raise ValueError('上传还未结束，请取消上传并等待发送进程返回，避免任务稍后启动。')
                # After restart an upload receipt may be lost. Operator explicitly
                # checks Handy/cloud pending tasks; never silently resend this attempt.
            def change():
                if a and a['kind'] == 'model':
                    self.job(a['job_id'])['status'] = '已中止'
                self.data.update(active=None, running=False, phase='paused', dirty_plate=not bed_clear,
                                 reason='已人工核对结束。可开始新任务，或先执行一次换盘。')
                self._note('人工核对：当前任务及云端待发任务已结束；未自动重试。')
            self.commit(change)

    def confirm_plate(self, connection):
        with self.lock:
            if self.data['phase'] != 'confirm_plate':
                raise ValueError('当前不在等待新盘确认。')
            self._idle(connection)
            self.commit(lambda: self.data.update(running=True, phase='ready', dirty_plate=False, reason=''))

    @staticmethod
    def _receipt(connection, request_id):
        return next((r for r in connection.get('commands', []) if r.get('request_id') == request_id), None)

    @staticmethod
    def _identity(device, active):
        t = device['telemetry']
        old=(active.get('monitor') or {}).get('identity') or strong_identity(active.get('identity',{}))
        return (old or strong_identity(t)) if matches_task(t,active['tag'],old) else None

    def _request(self, request, kind):
        # Every intent reaches durable storage BEFORE crossing the machine boundary.
        request = dict(request, request_id='q_'+uuid.uuid4().hex)
        def change():
            self.data['journal'].append(dict(request_id=request['request_id'], action=request['action'],
                tag=request.get('tag',''), time=self.clock(), outcome='intent'))
            if request['action'] == 'submit':
                self.data['journal'][-1]['materials'] = copy.deepcopy({k: request[k] for k in ('use_ams','ams_mapping','ams_mapping_info')})
            self.data['journal'] = self.data['journal'][-1000:]
            if kind:
                self.data['active'][kind] = request['request_id']
        self.commit(change)
        try:
            self.connection.command(request)
        except Exception as exc:
            self._hold('指令发送结果不明，请核对设备；不会自动重发。' + str(exc))
            return False
        def accepted():
            next(r for r in reversed(self.data['journal']) if r['request_id']==request['request_id'])['outcome'] = 'accepted'
        self.commit(accepted)
        return True

    def stop(self, connection, continue_queue=False):
        with self.lock:
            a = self.data['active']
            if not a:
                self._hold('队列已暂停；未向打印机发送停止指令。')
                return
            if a['kind'] == 'swap' and continue_queue:
                raise ValueError('换盘动作执行中不能跳过。请暂停并核对机构。')
            if continue_queue and a.get('stop_intent') == 'pause':
                raise ValueError('已选择暂停整条队列；停止完成后再手动继续。')
            d = self._device(connection)
            identity = self._identity(d, a)
            def change():
                a['stop_intent'] = 'continue' if continue_queue else 'pause'
                a['stop_since'] = self.clock()
                self.data.update(running=True, phase='stopping', reason='等待当前任务停止确认。')
                self._note('结束本盘后换盘继续。' if continue_queue else '停止当前打印并暂停整条队列。')
            self.commit(change)
            if identity:
                self._request(dict(action='stop', device_id=self.data['device_id'], tag=a['tag'], identity=identity), 'control_id')
            elif not a.get('identity'):
                self._request(dict(action='cancel_submit', target=a['request_id']), 'cancel_id')
            else:
                self._hold('当前实机任务身份已变化，未向其他任务发送停止。')

    def control(self, connection, action, objects=None):
        with self.lock:
            a = self.data['active']
            if not a or a['kind'] != 'model' or self.data['phase'] not in ('monitoring', 'recovery'):
                raise ValueError('当前没有可操作的模型盘。')
            d = self._device(connection)
            identity = self._identity(d, a)
            if not identity:
                raise ValueError('当前实机任务身份不匹配。')
            if action not in ('pause','resume','skip'):
                raise ValueError('无效的打印操作。')
            if a.get('pending_skip'):
                raise ValueError('上一条跳过指令尚未由设备确认，请等待或暂停核对。')
            extra = {}
            if action == 'skip':
                job = self.job(a['job_id'])
                valid = {int(o['id']) for o in job['objects']}
                done = set(a.get('skipped', [])) | set(d['telemetry'].get('s_obj', []))
                if not isinstance(objects, list) or not objects or any(type(o) is not int or o not in valid for o in objects):
                    raise ValueError('请选择本盘真实零件。')
                selected = done | set(objects)
                if selected >= valid:
                    self.stop(connection, continue_queue=True)
                    return
                if not job['label_markers']:
                    raise ValueError('切片未包含原生零件跳过标记，请在 Orca 启用标记对象后重新切片。')
                extra['objects'] = sorted(selected)
                self.commit(lambda: a.update(pending_skip=dict(objects=sorted(selected), since=self.clock())))
            if self._request(dict(action=action, device_id=self.data['device_id'], tag=a['tag'], identity=identity, **extra), 'control_id'):
                self.commit(lambda: self._note('已发送'+{'pause':'暂停打印','resume':'继续打印','skip':'跳过零件'}[action]+'，等待设备回报。'))

    def _dispatch(self, connection, swap=False):
        if hasattr(self.connection, 'upload_slot'):
            with self.connection.upload_slot() as ready:
                if not ready:
                    reason = '等待其他打印机完成文件上传，随后发送本机任务。'
                    if self.data.get('reason') != reason:
                        self.commit(lambda:self.data.update(reason=reason))
                    return
                return self._dispatch_unlocked(connection, swap)
        return self._dispatch_unlocked(connection, swap)

    def _dispatch_unlocked(self, connection, swap=False):
        if swap and not supports_auto_swap(self._device(connection)['model']):
            raise ValueError('此机型没有自动换盘，已禁止发送机械换盘任务。')
        asset = self.data['a1_swap'] if swap else self.waiting()[0]
        self._idle(connection)
        fresh, settings = self._asset(asset, connection, swap)
        count = fresh.get('filament_count', max((int(f['id']) for f in fresh['filaments']), default=1))
        if not 1 <= count <= 128:
            raise ValueError('切片耗材索引范围无效。')
        mapping = [-1] * count
        if settings['source'] == 'ams':
            for source, slot in settings['mapping'].items():
                match = re.fullmatch(r'ams/(\d+)/tray/(\d+)', slot)
                if not match or not (0 <= int(match[1]) <= 15 and 0 <= int(match[2]) <= 3) or not 1 <= int(source) <= count:
                    raise ValueError('耗材索引或 AMS 槽位不受支持。')
                mapping[int(source)-1] = int(match[1])*4+int(match[2])
        # Match the native sender's third mapping table as well as its slot arrays.
        # Keep sparse project indices: source 9 belongs at index 8, never index 0.
        detail = [dict(ams=-1, targetColor='', filamentId='', filamentType='') for _ in range(count)]
        slots = {s['id']:s for s in self._device(connection)['slots']}
        def wire_color(value):
            color = value.lstrip('#').upper()
            return color+'FF' if len(color)==6 else color
        for material in fresh.get('filaments', []):
            source = material['id']
            if source not in settings['mapping']:
                continue
            index = int(source)-1
            if not 0 <= index < count:
                raise ValueError('切片耗材编号超出映射范围。')
            slot = slots[settings['mapping'][source]]
            detail[index].update(ams=mapping[index], filamentId=material.get('profile_id',''),
                filamentType=material['type'], sourceColor=wire_color(material.get('color','')),
                targetColor=wire_color(slot.get('color','')))
            if material.get('nozzle_id') in (0,1):
                detail[index]['nozzleId']=material['nozzle_id']
        tag = 'oq_'+uuid.uuid4().hex
        def prepare():
            self.data['active'] = dict(kind='swap' if swap else 'model', job_id=None if swap else asset['id'],
                tag=tag, request_id='', created=self.clock(), identity={}, seen_running=False,
                start_event=0, stop_intent=None, skipped=[], mapping=copy.deepcopy(settings['mapping']))
            self.data['active']['monitor']=new_monitor(self._device(connection))
            self.data.update(phase='sending', reason='正在发送独立换盘文件。' if swap else '正在发送本盘切片。', dirty_plate=True)
            if not swap:
                asset['status'] = '发送中'
            asset['last_mapping'] = copy.deepcopy(settings['mapping'])
            for source, slot in settings['mapping'].items():
                if slot != asset['settings'].get('mapping', {}).get(source):
                    label = next((s.get('label', slot) for s in self._device(connection)['slots'] if s['id'] == slot), slot)
                    self._note('跨盘续料：切片耗材 '+source+' 改用 '+label+'。')
            self._note('发送：' + asset['name'])
        self.commit(prepare)
        self._request(dict(action='submit', device_id=self.data['device_id'], tag=tag,
            path=str(fs_path(asset['path'])), sha256=asset['sha256'], plate=int(fresh['plate']), ams_mapping=mapping,
            ams_mapping_info=detail,
            use_ams=settings['source']=='ams', options=settings['options'],
            bed_type=fresh.get('bed_type','auto')), 'request_id')

    def _finish(self, stopped=False, reviewed_identity=None):
        a = self.data['active']
        kind, intent = a['kind'], a.get('stop_intent')
        def change():
            self.data['journal'].append(dict(action='completion',time=self.clock(),request_id=a['request_id'],
                job_id=a.get('job_id'),kind=kind,outcome='reviewed' if reviewed_identity is not None else 'stopped' if stopped else 'completed',
                monitor=copy.deepcopy(a.get('monitor',{}))))
            self.data['journal']=self.data['journal'][-1000:]
            if reviewed_identity is not None:
                self.data['running']=True
                self._note('用户核对确认本盘打印成功，恢复本机队列；未重发已完成任务。')
            if kind == 'model':
                self.job(a['job_id'])['status'] = '已中止' if stopped else '已完成'
            self.data['active'] = None
            if intent == 'pause' or (stopped and intent != 'continue'):
                self.data.update(running=False, phase='paused', reason='当前任务已停止，整条队列暂停。')
            elif kind == 'swap':
                if stopped:
                    self.data.update(running=False, phase='paused', reason='换盘未完成，请人工核对机构和打印板。')
                elif self.data['auto_after_swap']:
                    self.data.update(phase='ready', dirty_plate=False, reason='')
                else:
                    self.data.update(running=False, phase='confirm_plate', reason='换盘程序已完成，请确认新板确实就位。')
            elif self.waiting():
                if self.data.get('plate_mode', 'automatic') == 'manual':
                    self.data.update(running=False, phase='confirm_plate', reason='本盘已结束。请更换或清空打印板，确认新板就位后继续本机队列。')
                else:
                    self.data.update(phase='between', reason='本盘已结束，准备独立换盘。')
            else:
                self.data.update(running=False, phase='completed', reason='队列结束，最后一盘留在打印机上。')
            self._note(self.data['reason'] or '实机回报本任务已结束。')
        self.commit(change)

    def tick(self, connection=None):
        with self.lock:
            if self.closed.is_set() or self.fatal or not self.data['running']:
                return
            connection = connection or self.connection.snapshot()
            a = self.data['active']
            try:d=self._device(connection)
            except ValueError:
                if not a:raise
                monitor=copy.deepcopy(a.get('monitor') or new_monitor({}))
                monitor.setdefault('connection_gap_since',self.clock());monitor['stage']='reconnecting'
                reason='连接暂时中断，正在重新读取本盘状态；后续任务暂不发送。'
                if monitor!=a.get('monitor') or self.data['reason']!=reason:
                    self.commit(lambda:(a.update(monitor=monitor),self.data.update(reason=reason)))
                if self.clock()-monitor['connection_gap_since']>=60:
                    self._hold('连接超过一分钟未恢复，请核对打印机；本盘记录保留，不会自动重发。')
                return
            t = d['telemetry']
            fault = self._fault_reason(t)
            if fault:
                self._hold('设备报告：' + fault + '。本机队列暂停，请在 Orca 的“设备 → 助手(HMS)”或 Handy 处理后继续监控。')
                return
            if not a:
                if not self.waiting():
                    self.commit(lambda: self.data.update(running=False, phase='completed', reason='队列结束，最后一盘保留。'))
                    return
                if self.data['phase'] == 'between':
                    if not self.data['a1_swap'].get('enabled'):
                        raise ValueError('独立换盘未启用，队列暂停。')
                    self._dispatch(connection, True)
                elif self.data['phase'] == 'ready':
                    self._dispatch(connection)
                return
            status = t.get('gcode_state', '')
            receipt = self._receipt(connection, a['request_id'])
            control = self._receipt(connection, a.get('control_id'))
            if control and control.get('status') == 'failed':
                self._hold('打印操作未被联网库接受，请在 Handy 核对当前打印。')
                return
            result=reduce_task(a,d,self.clock())
            if result['monitor']!=a.get('monitor') or result['detail']!=self.data['reason']:
                def observed():
                    first=result['observed_running'] and not a['seen_running']
                    a['monitor']=result['monitor']
                    a['identity']=result['identity']
                    a['seen_running']=result['observed_running']
                    if first:
                        a['start_event']=result['monitor'].get('run_event',d.get('state_event',0))
                        if a['kind']=='model':self.job(a['job_id'])['status']='打印中'
                        self._note('已确认打印机启动本次'+('换盘程序。' if a['kind']=='swap' else '模型盘。'))
                    self.data['reason']=result['detail']
                    if result['observed_running']:self.data['phase']='stopping' if a.get('stop_intent') else 'monitoring'
                self.commit(observed)
            if result['decision'] in ('conflict','ambiguous'):
                self._hold(result['detail']);return
            if result['decision'] in ('completed','failed'):
                if receipt and receipt.get('status')=='working':return
                self._finish(stopped=result['decision']=='failed');return
            if receipt and receipt.get('status')=='failed' and not result['observed_running']:
                self._hold('上传或云端发送失败，是否已启动尚待核对；不会自动重发。');return
            if a.get('stop_intent') and self.clock()-a.get('stop_since',a['created'])>90:
                self._hold('尚未确认当前任务停止，请在 Handy 核对；不会自动换盘。');return
            identity=self._identity(d,a) if result['observed_running'] else None
            if status in self.ACTIVE and identity and result['monitor']['stage']!='syncing' and d.get('state_age_ms',1e9)<=15000:
                if a.get('stop_intent') and not a.get('control_id'):
                    self._request(dict(action='stop', device_id=self.data['device_id'], tag=a['tag'], identity=identity), 'control_id')
                pending = a.get('pending_skip')
                if pending:
                    skipped=set(t.get('s_obj',[]))
                    ack=t.get('skip_ack_sequence')==a.get('control_id') and str(t.get('skip_ack_result','')).lower()=='success'
                    if skipped >= set(pending['objects']) or ack:
                        self.commit(lambda: (a.update(skipped=pending['objects']),a.pop('pending_skip',None),self._note('设备已确认跳过零件。')))
                    elif self.clock()-pending['since'] > 20:
                        self._hold('零件跳过尚未得到设备确认，队列暂停以供核对。')
                if status=='PAUSE' and not a.get('stop_intent'):
                    self.data['reason']='当前打印已暂停，可在本页或 Handy 继续打印。'
                return

    def _loop(self):
        while not self.closed.wait(1):
            try:
                self.tick()
            except Exception as exc:
                try:
                    with self.lock:
                        self._hold(str(exc))
                except Exception:
                    self.fatal='队列存储失败，已停止后续调度。请重开插件并核对当前打印。'
