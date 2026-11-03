"""C-only access to an already-loaded queue provider or legacy forwarding DLL.

This never creates an agent, reads account files, or logs into a second
session. SDK C++ calls remain with the host provider or legacy forwarding layer.
"""
import ctypes
import json
import os
import time
from printer_models import canonical_model


class NativeBridgeBindingError(RuntimeError):
    """The loaded module cannot be bound by this Python runtime."""


class NativeQueueBridge:
    def __init__(self):
        self._dll = None
        self._refresh_at = -1000.0
        self.watch_id = ''
        self.watch_ids = set()
        self._watchable_ids = []

    def _load(self):
        if self._dll is not None:
            return self._dll
        if os.name != 'nt':
            raise RuntimeError('原生桥接目前仅支持 Windows。')
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
        kernel.GetModuleHandleW.restype = ctypes.c_void_p
        # The native host must own the session before we attach.
        if not kernel.GetModuleHandleW('OrcaSlicer.dll'):
            raise RuntimeError('请在 Orca 内使用连接桥接。')
        candidates=[]
        independent_seen=False
        seen=set()
        for name in ('orca_plate_queue.dll','bambu_networking_02.03.00.dll','bambu_networking_02.08.01.dll','bambu_networking_02.08.04.dll','bambu_networking.dll'):
            module=kernel.GetModuleHandleW(name)
            if not module or module in seen:continue
            seen.add(module)
            independent_seen |= name == 'orca_plate_queue.dll'
            # Bind the existing host handle directly. Never open a DLL from disk,
            # search plugin folders, resolve an installation path or create an agent.
            # Windows ctypes inspects name even when handle is supplied (3.12+).
            # An empty string avoids the None path check; the non-null handle
            # still bypasses LoadLibrary entirely.
            try:
                loaded=ctypes.CDLL('',handle=module)
            except (TypeError, OSError) as exc:
                raise NativeBridgeBindingError(
                    '无法绑定 Orca 已加载的连接组件（'+type(exc).__name__+'）。'
                    '请更新队列插件并完整退出、重启 Orca。') from None
            try:
                loaded.obn_queue_abi_version_v1.restype=ctypes.c_uint32
                if loaded.obn_queue_abi_version_v1()!=1:continue
                loaded.obn_queue_snapshot_v1.argtypes=[ctypes.c_void_p,ctypes.c_uint32]
                loaded.obn_queue_snapshot_v1.restype=ctypes.c_int32
                size=loaded.obn_queue_snapshot_v1(None,0)
                if not 0<size<=2*1024*1024+1:continue
                buffer=ctypes.create_string_buffer(size)
                result=loaded.obn_queue_snapshot_v1(buffer,size)
                if not 0<result<=size or buffer.raw[result-1:result]!=b'\0':continue
                attached=json.loads(buffer.raw[:result-1].decode('utf8')).get('attached') is True
                candidates.append((attached,loaded))
            except (AttributeError,ValueError,UnicodeError):continue
        attached=[dll for active,dll in candidates if active]
        if len(attached)>1:
            raise RuntimeError('检测到多个联网实例，请正常退出并重启 Orca 后重试。')
        if not candidates:
            raise RuntimeError('尚未加载队列桥接。若刚更新 Open Bamboo，请先完成其联网库更新，再退出 Orca，运行连接适配器重新适配并重启。')
        if not attached:
            if independent_seen:
                raise RuntimeError('独立队列组件正在等待 Orca/Open Bamboo 提供连接接口；仅加载 DLL 不能建立连接。')
            raise RuntimeError('等待 Orca 创建唯一联网实例，请先启用联网功能。')
        dll=attached[0]
        try:
            dll.obn_queue_abi_version_v1.argtypes = []
            dll.obn_queue_abi_version_v1.restype = ctypes.c_uint32
            if dll.obn_queue_abi_version_v1() != 1:
                raise RuntimeError('原生队列桥接版本不匹配。')
            dll.obn_queue_snapshot_v1.argtypes = [ctypes.c_void_p,ctypes.c_uint32]
            dll.obn_queue_snapshot_v1.restype = ctypes.c_int32
            dll.obn_queue_refresh_v1.argtypes = []
            dll.obn_queue_refresh_v1.restype = ctypes.c_int32
            dll.obn_queue_command_v1.argtypes = [ctypes.c_char_p,ctypes.c_uint32]
            dll.obn_queue_command_v1.restype = ctypes.c_int32
        except AttributeError:
            raise RuntimeError('当前联网库尚未包含队列桥接；请完成原生桥接安装并重开 Orca。') from None
        self._dll = dll
        return dll

    def refresh(self):
        if self.watch_ids or self.watch_id:
            try:
                self.command(dict(action='watch_many', request_id='watch_queue_devices', device_ids=self._watchable_ids))
            except RuntimeError:
                pass  # Bootstrap may not have populated the device catalog yet.
        rc = self._load().obn_queue_refresh_v1()
        if rc not in (0,1):
            raise RuntimeError('尚未找到 Orca 当前联网实例，或设备刷新未能启动。')
        self._refresh_at = time.monotonic()
        return rc

    def command(self, request):
        dll = self._load()
        if request.get('action') == 'submit':
            try:
                revision=dll.obn_queue_material_revision_v1
                revision.argtypes=[];revision.restype=ctypes.c_uint32
                supported=revision()>=2
            except AttributeError:
                supported=False
            if not supported:
                raise RuntimeError('当前桥接缺少完整耗材映射支持。请退出 Orca，使用连接适配器重新适配并重启，再发送任务。')
        payload = json.dumps(request, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        if len(payload) > 65536:
            raise ValueError('指令过大。')
        rc = dll.obn_queue_command_v1(payload, len(payload))
        if rc not in (0, 1):
            reasons = {-3:'指令编号冲突', -4:'发送任务忙或上传已结束', -5:'本次会话指令记录已满，请先结束队列',
                       -6:'打印机状态已变化', -7:'本机编码不能表示插件存储路径', -8:'设备或当前打印任务身份不匹配'}
            raise RuntimeError(reasons.get(rc, '原生指令未接受') + f'（{rc}）')
        return rc

    def snapshot(self):
        dll = self._load()
        needed = dll.obn_queue_snapshot_v1(None,0)
        for _ in range(3):
            if not 0 < needed <= 2*1024*1024+1:
                raise ValueError('原生设备快照大小无效。')
            buf = ctypes.create_string_buffer(needed)
            result = dll.obn_queue_snapshot_v1(buf,needed)
            if result <= 0:
                raise ValueError('原生设备快照读取失败。')
            if result > needed:
                needed = result
                continue
            if buf.raw[result-1:result] != b'\0':
                raise ValueError('原生设备快照未正常结束。')
            raw = json.loads(buf.raw[:result-1].decode('utf-8'))
            try:
                revision=dll.obn_queue_material_revision_v1
                revision.argtypes=[];revision.restype=ctypes.c_uint32
                raw['material_mapping_ready']=revision()>=2
            except AttributeError:
                raw['material_mapping_ready']=False
            if raw.get('attached') is False:
                raise RuntimeError('等待 Orca 创建唯一联网实例。')
            # Request a real bootstrap asynchronously; polling itself is memory-only.
            watched = self.watch_ids | ({self.watch_id} if self.watch_id else set())
            rows = [d for d in raw.get('devices',[]) if d.get('id') in watched]
            self._watchable_ids = sorted(d['id'] for d in rows if canonical_model(d.get('model')))
            if watched and raw.get('can_submit') is True:
                self.command(dict(action='watch_many', request_id='watch_queue_devices', device_ids=self._watchable_ids))
            if not watched:
                rows = [d for d in raw.get('devices',[]) if d.get('id')==raw.get('selected_device_id')]
            needs_state = not rows or any(d.get('age_ms',1e9)>15000 or d.get('state_age_ms',0)>10000 or d.get('nozzle') is None or not d.get('telemetry',{}).get('gcode_state') for d in rows)
            if self._refresh_at < 0 or (time.monotonic()-self._refresh_at > 10 and needs_state):
                self.refresh()
            return raw
        raise ValueError('设备快照持续变化，请稍后刷新。')
