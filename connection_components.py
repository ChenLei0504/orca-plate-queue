"""Versioned, offline installation of bundled Open Bamboo + queue bridges.

No agent creation, credentials, Orca configuration edits, network or subprocesses.
Installation is explicit and blocked while any managed task needs reconciliation.
"""
from pathlib import Path
import ctypes
import hashlib
import json
import os
import struct
import sys
import time
import uuid


def loaded_network_modules():
    if os.name != 'nt':
        return []
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetModuleHandleW.argtypes=[ctypes.c_wchar_p]
    kernel.GetModuleHandleW.restype=ctypes.c_void_p
    kernel.GetProcAddress.argtypes=[ctypes.c_void_p,ctypes.c_char_p]
    kernel.GetProcAddress.restype=ctypes.c_void_p
    rows=[]
    for series in ('02.03.00','02.08.01','02.08.04','default'):
        name='bambu_networking.dll' if series=='default' else f'bambu_networking_{series}.dll'
        handle=kernel.GetModuleHandleW(name)
        if handle:
            rows.append(dict(series=series,queue_api=bool(kernel.GetProcAddress(handle,b'obn_queue_abi_version_v1')),
                             history=bool(kernel.GetProcAddress(handle,b'obn_queue_monitor_revision_v1'))))
    return rows


class ConnectionComponents:
    def __init__(self, bundle, storage, target=None, busy=None, probe=None):
        self.bundle=Path(bundle).resolve()
        self.storage=Path(storage).resolve()
        self.target=Path(target).resolve() if target is not None else Path(os.environ.get('APPDATA',''))/'OrcaSlicer'/'plugins'
        self.target=self.target.resolve()
        self.busy=busy or (lambda:False)
        self.probe=probe or loaded_network_modules
        self._digests={}
        self.restart_needed=False
        self.manifest=json.loads((self.bundle/'components.json').read_text(encoding='utf8'))
        self.files=self.manifest['files']
        if self.manifest.get('schema')!=1 or not self.files or any(Path(n).name!=n or '/' in n or '\\' in n or not n.endswith('.dll') for n in self.files):
            raise ValueError('内置连接组件清单无效。')
        for name,entry in self.files.items():
            if len(entry.get('sha256',''))!=64:
                raise ValueError('连接组件校验信息无效。')

    def digest(self,path):
        path=Path(path)
        if path.is_symlink():
            raise ValueError('连接组件路径不能是符号链接。')
        if not path.is_file():return ''
        st=path.stat();key=(str(path),st.st_size,st.st_mtime_ns)
        if key not in self._digests:
            h=hashlib.sha256()
            with path.open('rb') as stream:
                for part in iter(lambda:stream.read(1024*1024),b''):h.update(part)
            self._digests[key]=h.hexdigest()
        return self._digests[key]

    def verify_bundle(self):
        self._digests.clear()
        for name,entry in self.files.items():
            path=self.bundle/name
            if self.digest(path)!=entry['sha256']:
                raise ValueError('内置连接组件校验失败：'+name)
            data=path.read_bytes()
            if len(data)<64 or data[:2]!=b'MZ':raise ValueError('连接组件不是有效的 Windows 库。')
            at=struct.unpack_from('<I',data,0x3c)[0]
            if at+6>len(data) or data[at:at+4]!=b'PE\0\0' or struct.unpack_from('<H',data,at+4)[0]!=0x8664:
                raise ValueError('连接组件架构必须为 Windows x64。')

    def status(self):
        loaded=self.probe()
        rows=[]
        for series,spec in self.manifest['series'].items():
            installed=self.digest(self.target/spec['bridge'])
            backend_ok=self.digest(self.target/spec['backend'])==self.files[spec['backend']]['sha256']
            accepted={self.files[spec['bridge']]['sha256'],*spec.get('compatible_bridge_hashes',[])}
            compatible=bool(installed and installed in accepted and backend_ok)
            kind='queue' if compatible else 'open_bamboo' if installed==self.files[spec['backend']]['sha256'] else 'other' if installed else 'missing'
            rows.append(dict(series=series,kind=kind,compatible=compatible,loaded=any(d['series']==series for d in loaded)))
        active=[r for r in rows if r['loaded']]
        queue_loaded=any(r.get('queue_api') for r in loaded)
        active_ok=bool(active) and all(r['compatible'] for r in active)
        # The unversioned fallback is a reviewed 02.08.04 build.
        if not active and any(r['series']=='default' for r in loaded):
            active_ok=self.digest(self.target/'bambu_networking.dll')==self.files['bambu_networking.dll']['sha256'] and self.digest(self.target/self.manifest['series']['02.08.04']['backend'])==self.files[self.manifest['series']['02.08.04']['backend']]['sha256']
        ready=active_ok and queue_loaded and not self.restart_needed
        history_ready=ready and any(r.get('history') for r in loaded)
        installed=all(r['compatible'] for r in rows)
        summary='连接组件已更改，请保存工程并正常退出、重启 Orca。' if self.restart_needed else '已复用 Orca 当前连接组件与登录会话。' if ready else '组件已安装，请重启 Orca 后在首页登录 Bambu Cloud。' if installed else '已发现 Open Bamboo，可安装内置队列桥接；原组件将自动备份。' if any(r['kind']!='missing' for r in rows) else '尚未安装连接组件，可使用本插件内置安装包。'
        if ready and not history_ready:summary+=' 当前连接仍使用旧桥接，安装内置组件并重启后启用状态历史。'
        return dict(available=True,ready=ready,installed=installed,restart_required=self.restart_needed or (installed and not ready),
                    history_ready=history_ready,
                    can_install=not self.busy(),restore_available=(self.storage/'latest-install.json').is_file(),
                    summary=summary,series=rows,loaded_series=[r['series'] for r in loaded],
                    note='仅支持 Windows x64；接口 02.03.00 / 02.08.01 / 02.08.04。不修改账号、固件或 Orca 配置。')

    @staticmethod
    def write_json(path,value):
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
        pending=path.with_name(path.name+'.pending')
        with pending.open('w',encoding='utf8') as stream:
            json.dump(value,stream,ensure_ascii=False,indent=2);stream.flush();os.fsync(stream.fileno())
        os.replace(pending,path)

    def place(self,source,target,expected):
        source,target=Path(source),Path(target)
        if target.parent.resolve()!=self.target or self.target.is_symlink():
            raise ValueError('连接组件目标目录无效。')
        pending=target.with_name(target.name+'.'+uuid.uuid4().hex+'.pending')
        parked=None
        try:
            with source.open('rb') as src,pending.open('xb') as dst:
                for block in iter(lambda:src.read(1024*1024),b''):dst.write(block)
                dst.flush();os.fsync(dst.fileno())
            if self.digest(pending)!=expected:raise ValueError('组件复制校验失败。')
            try:os.replace(pending,target)
            except PermissionError:
                if not target.is_file():raise
                # Windows can rename a mapped DLL without unloading the running instance.
                parked=target.with_name(target.name+'.previous-'+uuid.uuid4().hex)
                os.rename(target,parked)
                try:os.replace(pending,target)
                except Exception:
                    os.rename(parked,target);raise
            if self.digest(target)!=expected:raise ValueError('安装后组件校验失败。')
        finally:
            pending.unlink(missing_ok=True)

    def install(self):
        if self.busy():raise ValueError('仍有运行中或待核对的打印任务，请结束并核对后再安装连接组件。')
        self.verify_bundle()
        self.target.mkdir(parents=True,exist_ok=True)
        backup=self.storage/'backups'/(time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]);backup.mkdir(parents=True)
        receipt=dict(schema=1,target=str(self.target),phase='prepared',files=[])
        # Backends and sidecars must be present before publishing the bridge names.
        names=sorted(self.files,key=lambda n:(self.files[n]['role']=='bridge',n=='bambu_networking.dll',n))
        for name in names:
            target=self.target/name;old=self.digest(target);new=self.files[name]['sha256']
            if old and self.files[name].get('preserve_existing'):continue
            if old==new:continue
            if old:
                saved=backup/name
                with target.open('rb') as src,saved.open('xb') as dst:
                    for block in iter(lambda:src.read(1024*1024),b''):dst.write(block)
                if self.digest(saved)!=old:raise ValueError('原连接组件备份校验失败。')
            receipt['files'].append(dict(name=name,before=old,after=new))
        if not receipt['files']:
            backup.rmdir()
            return '内置连接组件已是当前版本，无需重复安装。'
        receipt_path=backup/'receipt.json';self.write_json(receipt_path,receipt)
        changed=[]
        try:
            for row in receipt['files']:
                if self.busy():raise ValueError('队列状态发生变化，连接组件安装已中止。')
                if self.digest(self.target/row['name'])!=row['before']:raise ValueError('连接组件被其他安装器修改，已停止覆盖。')
                changed.append(row)
                self.place(self.bundle/row['name'],self.target/row['name'],row['after'])
            receipt['phase']='installed';self.write_json(receipt_path,receipt)
            self.write_json(self.storage/'latest-install.json',dict(backup=backup.name))
            self.restart_needed=True
        except Exception as original:
            failures=[]
            for row in reversed(changed):
                try:self.restore_row(backup,row)
                except Exception as exc:failures.append(str(exc))
            receipt['phase']='repair_required' if failures else 'rolled_back'
            self.write_json(receipt_path,receipt)
            if failures:
                self.write_json(self.storage/'latest-install.json',dict(backup=backup.name))
                raise ValueError('安装未完成，部分组件需要恢复。请保留备份目录：'+str(backup)+'。'+str(original)) from original
            raise
        return '连接组件已安装并备份。请保存工程、正常退出并重启 Orca；首次使用需启用 Orca 联网功能并在首页登录 Bambu Cloud。'

    def restore_row(self,backup,row):
        name=row['name']
        if name not in self.files:raise ValueError('恢复清单包含未知文件。')
        target=self.target/name;current=self.digest(target)
        if current==row['before']:return
        if current!=row['after']:raise ValueError('组件已被其他安装器更新，未覆盖新文件：'+name)
        if row['before']:
            if self.digest(backup/name)!=row['before']:raise ValueError('原组件备份已变化。')
            self.place(backup/name,target,row['before'])
        else:
            try:target.unlink()
            except PermissionError:os.rename(target,target.with_name(target.name+'.removed-'+uuid.uuid4().hex))

    def restore(self):
        if self.busy():raise ValueError('仍有运行中或待核对任务，不能恢复连接组件。')
        self._digests.clear()
        latest=json.loads((self.storage/'latest-install.json').read_text(encoding='utf8'))
        name=latest['backup']
        if Path(name).name!=name or '/' in name or '\\' in name:raise ValueError('备份路径无效。')
        backup=self.storage/'backups'/name
        receipt=json.loads((backup/'receipt.json').read_text(encoding='utf8'))
        if receipt.get('schema')!=1 or receipt.get('target')!=str(self.target):raise ValueError('备份不属于当前连接目录。')
        # Validate all targets and backup bytes before changing anything.
        for row in receipt['files']:
            if row['name'] not in self.files or self.digest(self.target/row['name']) not in (row['before'],row['after']):raise ValueError('当前组件已被其他安装器更改，恢复已中止。')
            if row['before'] and self.digest(backup/row['name'])!=row['before']:raise ValueError('备份组件校验失败。')
        changed=[]
        try:
            for row in reversed(receipt['files']):
                if self.busy():raise ValueError('队列状态发生变化，已停止恢复组件。')
                changed.append((row,self.digest(self.target/row['name'])))
                self.restore_row(backup,row)
        except Exception as original:
            failures=[]
            for row,prior in reversed(changed):
                if prior==row['before']:continue
                try:
                    current=self.digest(self.target/row['name'])
                    if current==prior:continue
                    if current!=row['before']:raise ValueError('恢复期间组件被其他安装器修改。')
                    self.place(self.bundle/row['name'],self.target/row['name'],row['after'])
                except Exception as exc:failures.append(str(exc))
            receipt['phase']='repair_required' if failures else 'installed'
            self.write_json(backup/'receipt.json',receipt)
            if failures:raise ValueError('恢复未完成，请保留备份并重新核对连接组件。'+str(original)) from original
            raise
        receipt['phase']='restored';self.write_json(backup/'receipt.json',receipt)
        (self.storage/'latest-install.json').unlink(missing_ok=True)
        self.restart_needed=True
        return '已恢复安装前的连接组件，请正常退出并重启 Orca。队列和耗材设置未改动。'
