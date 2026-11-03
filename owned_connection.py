"""One private native process per queue plugin. No host-DLL discovery or replacement."""
import copy
import hashlib
import json
import os
import queue
import subprocess
import threading
import time
import uuid
from pathlib import Path
from browser_login import BrowserLogin
from local_paths import fs_path, normal_path


class OwnedConnectionError(RuntimeError):
    pass


class ComponentRejected(OwnedConnectionError):
    pass


def private_process_command(executable):
    """Stable Windows command line shared by the permission request and Popen."""
    return subprocess.list2cmdline([str(fs_path(Path(executable).absolute()))])


class PrivateProcess:
    def __init__(self, executable, *, verify=True, timeout=30):
        self.timeout = timeout
        self._lock = threading.Lock()
        self._responses = queue.Queue(maxsize=4)
        self._closed = False
        executable = Path(executable).absolute()
        if verify:
            manifest = json.loads(fs_path(executable.with_name('manifest.json')).read_text(encoding='utf-8'))
            expected = {'orca_queue_host.exe', 'orca_queue_owned_backend.dll',
                        'msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll'}
            if set(manifest.get('files', {})) != expected:
                raise OwnedConnectionError('连接组件文件清单无效，请重新安装插件。')
            for name, digest in manifest['files'].items():
                with fs_path(executable.with_name(name)).open('rb') as source:
                    actual = hashlib.file_digest(source, 'sha256').hexdigest()
                if actual != digest:
                    raise OwnedConnectionError('连接组件文件校验失败，请重新安装插件。')
        env = dict(os.environ)
        # Do not let unrelated Open Bamboo environment overrides redirect this
        # instance's account/configuration files or change its private SDK flags.
        for key in list(env):
            if key.upper().startswith(('OBN_', 'OPEN_BAMBU')):
                env.pop(key)
        # CreateProcess limits executable discovery through argv[0] and the
        # current-directory parameter even when long-path-aware is enabled.
        # Explicit lpApplicationName + a drive-root cwd avoids both limits.
        # The helper resolves all of its own files from its absolute EXE path.
        # Orca grants the complete command line, not just the executable. Keep
        # per-launch identity out of argv so its saved grant survives restarts.
        env['ORCA_QUEUE_PARENT_PID'] = str(os.getpid())
        self._process = subprocess.Popen(private_process_command(executable),
            executable=str(fs_path(executable)),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            cwd=normal_path(executable).anchor, env=env, shell=False,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), bufsize=0)
        threading.Thread(target=self._read, daemon=True, name='queue-cloud-pipe').start()

    def _read(self):
        try:
            while not self._closed:
                line = self._process.stdout.readline(2 * 1024 * 1024 + 1)
                if not line or len(line) > 2 * 1024 * 1024 or not line.endswith(b'\n'):
                    break
                value = json.loads(line)
                if not isinstance(value, dict):
                    break
                self._responses.put_nowait(value)
        except Exception:
            pass
        finally:
            try:
                self._responses.put_nowait(None)
            except queue.Full:
                pass

    def call(self, action, payload=None):
        with self._lock:
            if self._closed:
                raise OwnedConnectionError('独立连接已关闭，请重新连接。')
            request_id = uuid.uuid4().hex
            raw = json.dumps({'id': request_id, 'action': action, 'payload': payload},
                             ensure_ascii=False, separators=(',', ':')).encode('utf-8') + b'\n'
            if len(raw) > 65536:
                raise OwnedConnectionError('指令过大。')
            try:
                # Popen's raw pipe may return a short write; preserve message boundaries.
                written = queue.Queue(maxsize=1)
                def write():
                    try:
                        view = memoryview(raw)
                        while view:
                            sent = self._process.stdin.write(view)
                            if not sent:
                                raise OSError()
                            view = view[sent:]
                        written.put(True)
                    except Exception:
                        written.put(False)
                threading.Thread(target=write, daemon=True, name='queue-cloud-write').start()
                if not written.get(timeout=self.timeout):
                    raise OSError()
                result = self._responses.get(timeout=self.timeout)
                if result is None or result.get('id') != request_id or type(result.get('ok')) is not bool:
                    raise ValueError()
            except Exception:
                self.close()
                raise OwnedConnectionError('连接组件无响应或已退出；已暂停连接，请核对当前任务后重新连接。') from None
            if not result['ok']:
                code = result.get('code')
                reasons = {-3: '连接状态或指令编号冲突', -4: '登录或任务发送未完成',
                           -6: '打印机状态已变化', -7: '当前 Windows 不支持组件所需的 UTF-8 路径',
                           -8: '设备或打印任务身份不匹配', -9: '无法保护本机登录目录',
                           -10: '该账号目录已由另一个队列组件使用'}
                raise ComponentRejected(reasons.get(code, '连接组件未接受操作') + f'（{code}）')
            return result.get('result', result.get('code', 0))

    def close(self):
        if self._closed:
            return
        self._closed = True
        process = self._process
        # No lock: close must be able to interrupt a hung SDK call. A timed-out
        # submission is never replayed; the queue's persisted recovery owns it.
        if process.poll() is None:
            process.kill()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass
        for stream in (process.stdin, process.stdout):
            try:
                stream.close()
            except OSError:
                pass


class OwnedCloudConnection:
    def __init__(self, storage, *, executable=None, process_factory=PrivateProcess, browser_factory=BrowserLogin):
        self.watch_ids = set()
        self._storage = Path(storage) / 'cloud-session'
        self._executable = executable or Path(__file__).with_name('native-bin') / 'orca_queue_host.exe'
        self._factory = process_factory
        self._browser_factory = browser_factory
        self._browser = None
        self._mu = threading.Lock()
        self._queue = queue.Queue(maxsize=40)
        self._stop = threading.Event()
        self._worker = None
        self._process = None
        self._raw = None
        self._updated = 0
        self._region = 'CN'
        self._busy = False
        self._note = '请登录 Bambu Cloud。'
        self._failed = False

    def start(self):
        if self._worker is not None:
            return
        fs_path(self._storage).mkdir(parents=True, exist_ok=True)
        pref = fs_path(self._storage / 'region.json')
        if pref.is_file():
            value = json.loads(pref.read_text(encoding='utf-8'))
            if value.get('region') in ('CN', 'US'):
                self._region = value['region']
        self._worker = threading.Thread(target=self._run, daemon=True, name='queue-owned-cloud')
        self._worker.start()

    def status(self):
        with self._mu:
            raw = self._raw or {}
            return {'region': self._region, 'busy': self._busy, 'logged_in': raw.get('logged_in') is True,
                    'connected': raw.get('cloud_connected') is True, 'note': self._note,
                    'login_method': 'browser',
                    'browser_url': self._browser.url if self._browser and not self._browser.expired and not self._busy else '',
                    'browser_waiting': self._browser is not None,
                    'failed': self._failed}

    def snapshot(self):
        with self._mu:
            if self._raw is None:
                raise OwnedConnectionError(self._note)
            result = copy.deepcopy(self._raw)
            age = max(0, (time.monotonic() - self._updated) * 1000)
        for row in result.get('devices', []):
            for key in ('age_ms', 'state_age_ms'):
                row[key] = row.get(key, 1e9) + age
            for event in row.get('task_events', []):
                event['age_ms'] = event.get('age_ms', 1e9) + age
        return result

    def _open(self, region):
        if self._process:
            self._process.close()
        with self._mu:
            self._raw = None
            self._region = region
        # Python I/O must keep ordinary private paths in Orca's allowed root.
        # Only the native SDK needs the explicit extended spelling unconditionally.
        folder = fs_path(self._storage / region)
        folder.mkdir(parents=True, exist_ok=True)
        self._process = self._factory(self._executable)
        self._process.call('open', {'storage': str(fs_path(folder, force=True)), 'region': region})
        raw = self._process.call('snapshot')
        if raw.get('logged_in'):
            self._process.call('connect')
        self._failed = False
        if not raw.get('logged_in'):
            with self._mu:
                self._note = '请登录 Bambu Cloud。'
        self._poll()

    def _poll(self):
        if not self._process or self._failed or self._stop.is_set():
            return
        raw = self._process.call('snapshot')
        if not isinstance(raw, dict) or raw.get('origin') != 'orca-owned-cloud':
            raise OwnedConnectionError('独立连接协议不匹配，请重新安装插件。')
        known = {d['id'] for d in raw.get('devices', []) if d.get('model') in ('N2S', 'C12', 'A1', 'P1S')}
        watched = sorted(self.watch_ids & known)
        if raw.get('logged_in'):
            self._process.call('command', {'action': 'watch_many', 'request_id': 'watch_queue_devices', 'device_ids': watched})
            self._process.call('refresh')
        with self._mu:
            self._raw = raw
            self._updated = time.monotonic()
            if raw.get('logged_in'):
                self._note = '插件独立云连接已连接。' if raw.get('cloud_connected') else '已登录，正在连接打印机。'

    def refresh(self):
        if not self._stop.is_set() and self._queue.empty():
            try:
                self._queue.put_nowait(('refresh', {}, None))
            except queue.Full:
                pass

    def auth_action(self, action, data):
        if action not in ('browser_begin', 'browser_cancel', 'logout', 'reconnect'):
            raise ValueError('不支持的登录操作。')
        clean = {'region': data.get('region', self._region)}
        if action == 'browser_begin' and clean['region'] not in ('CN', 'US'):
            raise ValueError('请选择中国大陆或全球区。')
        with self._mu:
            if self._stop.is_set() or self._busy:
                raise ValueError('连接操作正在进行，请稍候。')
            if action == 'browser_begin' and (self._raw or {}).get('logged_in'):
                raise ValueError('请先退出当前队列账号。')
            self._busy = True
            self._note = '正在处理连接请求…'
            try:
                self._queue.put_nowait((action, clean, None))
            except queue.Full:
                self._busy = False
                raise ValueError('连接请求繁忙，请稍后重试。') from None

    def _cancel_browser(self):
        with self._mu:
            browser, self._browser = self._browser, None
        if browser:
            browser.close()

    def _begin_browser(self, region):
        self._cancel_browser()
        # A fresh agent permits one ticket attempt and clears stale device caches.
        self._open(region)
        if self._stop.is_set() or self.status()['logged_in']:
            return
        browser = self._browser_factory(region)
        with self._mu:
            stopped = self._stop.is_set()
            if not stopped:
                self._browser = browser
                self._note = '请打开拓竹官方登录页，完成后返回 Orca。链接有效期为 5 分钟。'
        if stopped:
            browser.close()

    def _poll_browser(self):
        browser = self._browser
        if not browser or self._stop.is_set():
            return
        ticket = browser.poll()
        if ticket is None:
            if browser.expired:
                self._cancel_browser()
                with self._mu:
                    self._note = '网页登录已超时，请重新准备登录链接。'
            return
        with self._mu:
            self._busy = True
            self._note = '已收到网页登录结果，正在建立队列连接…'
        self._cancel_browser()
        try:
            if self._stop.is_set():
                return
            try:
                self._process.call('ticket', {'ticket': ticket})
            except ComponentRejected:
                with self._mu:
                    self._note = '网页登录票据未被接受，请重新准备登录链接。不会自动重复提交。'
                return
            fs_path(self._storage / 'region.json').write_text(json.dumps({'region': self._region}), encoding='utf-8')
            self._process.call('connect')
            self._poll()
            if not self.status()['logged_in']:
                raise ComponentRejected('网页登录未完成，请重新准备登录链接。')
        finally:
            ticket = None
            with self._mu:
                self._busy = False

    def command(self, request):
        if self._stop.is_set() or self._failed:
            raise OwnedConnectionError('独立连接不可用，请重新连接。')
        done = queue.Queue(maxsize=1)
        try:
            self._queue.put_nowait(('command', copy.deepcopy(request), done))
        except queue.Full:
            raise OwnedConnectionError('连接请求繁忙，请稍后重试。') from None
        try:
            ok, result = done.get(timeout=40)
        except queue.Empty:
            self._stop.set()
            if self._process:
                self._process.close()
            with self._mu:
                self._raw = None
            raise OwnedConnectionError('任务指令结果未知；请核对打印机，勿重复发送。') from None
        if not ok:
            raise OwnedConnectionError(result)
        return result

    def _run(self):
        try:
            self._open(self._region)
        except Exception as exc:
            self._failure(exc)
        while not self._stop.is_set():
            try:
                action, data, done = self._queue.get(timeout=2)
            except queue.Empty:
                action, data, done = 'refresh', {}, None
            if self._stop.is_set():
                break
            try:
                result = 0
                if action == 'reconnect':
                    self._cancel_browser()
                    self._open(self._region)
                elif action == 'browser_begin':
                    self._begin_browser(data['region'])
                elif action == 'browser_cancel':
                    self._cancel_browser()
                    with self._mu:
                        self._note = '已取消网页登录。'
                elif action == 'logout':
                    self._cancel_browser()
                    self._process.call('logout')
                    self._poll()
                    with self._mu:
                        self._note = '已退出本插件账号。'
                elif action == 'command':
                    if self._failed:
                        raise OwnedConnectionError('独立连接不可用，请重新连接。')
                    result = self._process.call('command', data)
                    self._poll()
                else:
                    self._poll()
                self._poll_browser()
                if done:
                    done.put((True, result))
            except Exception as exc:
                if isinstance(exc, ComponentRejected):
                    with self._mu:
                        self._note = str(exc)
                else:
                    self._failure(exc)
                if done:
                    done.put((False, str(exc) if isinstance(exc, OwnedConnectionError) else '独立连接操作失败。'))
            finally:
                data.clear()
                if action in ('browser_begin', 'browser_cancel', 'logout', 'reconnect'):
                    with self._mu:
                        self._busy = False
        self._cancel_browser()
        if self._process:
            self._process.close()

    def _failure(self, exc):
        self._cancel_browser()
        with self._mu:
            self._raw = None
            self._failed = True
            if 'audit permission required' in str(exc):
                # Orca denies a background operation before showing its prompt.
                # Accepting the prompt saves permission but cannot resume Popen.
                self._note = 'Orca 已暂停连接组件以请求权限。授权完成后，请在“连接说明”中点击“重新连接”，无需重启或重装。'
            else:
                self._note = str(exc) if isinstance(exc, OwnedConnectionError) else '独立连接启动失败，请检查插件文件和权限。'
        if self._process:
            self._process.close()
            self._process = None

    def close(self):
        self._stop.set()
        self._cancel_browser()
        if self._process:
            self._process.close()
        if self._worker:
            self._worker.join(timeout=1)
        with self._mu:
            self._raw = None
