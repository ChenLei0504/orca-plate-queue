"""Build an explicit standalone cloud preview, separate from the stable split release."""
import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile
from build_public_release import runtime_entries, archive_bytes, SOURCES

ROOT = Path(__file__).resolve().parent
VERSION = '0.8.0a1'
BUILD = '20261103.3'
OUT = ROOT / 'standalone-dist' / VERSION
NATIVE = ROOT / 'native/owned-host-build'
EXTRA = ['cloud_login.py','owned_connection.py','build_standalone_release.py','test_owned_connection.py',
         'test_standalone_release.py','native/owned_host.cpp','native/owned_host.manifest','native/build_owned_host.py']


def main():
    manifest = json.loads((NATIVE/'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('fixture') is not False or manifest.get('backend_revision') != 'b14f880':
        raise ValueError('Only the pinned production core may be packaged')
    entries = runtime_entries()
    for module in ('cloud_login', 'owned_connection'):
        source=(ROOT/(module+'.py')).read_text(encoding='utf-8')
        source=re.sub(r'^from (cloud_login|local_paths) import ',r'from .\1 import ',source,flags=re.M)
        entries['orca_plate_queue/'+module+'.py']=source.encode()
    core=entries['orca_plate_queue/core.py'].decode()
    assert core.count('OWNED_CLOUD = False')==1
    core=core.replace('OWNED_CLOUD = False','OWNED_CLOUD = True').replace('    from owned_connection import ', '    from .owned_connection import ')
    entries['orca_plate_queue/core.py']=core.encode()
    for name in ('release_info.py','plugin_page.html','plugin_page.js'):
        key='orca_plate_queue/'+name
        value=entries[key].decode()
        from release_info import QUEUE_VERSION, QUEUE_BUILD_ID
        value=value.replace(QUEUE_VERSION,VERSION).replace(QUEUE_BUILD_ID,BUILD)
        value=value.replace('精简队列版','独立云连接测试版')
        entries[key]=value.encode()
    for name,digest in manifest['files'].items():
        if '/' in name or '\\' in name:
            raise ValueError('Invalid binary name')
        data=(NATIVE/name).read_bytes()
        if hashlib.sha256(data).hexdigest()!=digest:
            raise ValueError('Native file changed: '+name)
        entries['orca_plate_queue/native-bin/'+name]=data
    entries['orca_plate_queue/native-bin/manifest.json']=(NATIVE/'manifest.json').read_bytes()
    notice=(
        'Orca Plate Queue '+VERSION+' — independent cloud PREVIEW\n'
        'Queue runtime and private process host: AGPL-3.0-or-later.\n'
        'Includes the pinned Open Bamboo networking core b14f880, renamed for private use.\n'
        'Open Bamboo authors: Alexey Cluster and contributors. No official endorsement.\n'
        'No Open Bamboo plugin installation is required; its code remains an upstream dependency.\n'
        'No Orca or other plugin files are modified. Windows x64, Windows 10 1903 or newer.\n'
        'Microsoft Visual C++ runtime DLLs are included for application-local use under Microsoft terms.\n'
        'Corresponding project source and pinned upstream source are included in source-'+VERSION+'.zip.\n'
        'Requires interactive user sign-in. Real cloud/Handy/printing validation is NOT complete.\n')
    license_text=(ROOT/'LICENSE').read_bytes()
    entries['orca_plate_queue/LICENSE']=license_text
    entries['orca_plate_queue/NOTICE']=notice.encode()
    # Keep the exact upstream license and source with the binary, not just a web link.
    with tarfile.open(ROOT/'vendor/open-bamboo-b14f880.tar.gz','r:gz') as archive:
        member=next(m for m in archive.getmembers() if m.name.endswith('/LICENSE') and m.name.count('/')==1)
        upstream_license=archive.extractfile(member).read()
    entries['orca_plate_queue/licenses/Open-Bamboo-AGPL.txt']=upstream_license
    entries['orca_plate_queue/permissions.json']=json.dumps({
        'version':VERSION,'bundled_native_libraries':True,'process_execution':True,
        'process_scope':'bundled orca_queue_host.exe, hidden child with private stdin/stdout pipes',
        'network':'Bambu HTTPS sign-in, device services, cloud upload and MQTT; default TLS verification',
        'credential_storage':'plugin cloud-session directory; Windows ACL current user and SYSTEM; not encrypted',
        'other_plugin_file_modification':False,'host_account_discovery':False,
        'private_storage_writes':True,'user_selected_file_reads':'single-plate and swap 3MF files',
        'environment_variable_access':'child process inherits standard environment; unrelated OBN overrides removed',
        'supported_platforms':['Windows x64 10 1903+'],'real_device_validation':'pending',
    },ensure_ascii=False,indent=2).encode()
    instructions='''Orca Plate Queue 0.8.0a1 独立云连接测试版

安装：保存工程，在旧版队列中暂停所有队列并核对未结束任务。Orca 插件管理中停用旧版打印队列，然后通过“安装插件”选择本目录的 .whl 文件。接受插件声明的私有组件启动和网络权限。打开“打印队列 → 连接说明”，选择账号地区，输入邮箱或中国大陆手机号，获取验证码并登录。无需运行旧版连接组件 EXE，也无需修改 Open Bamboo。

Windows x64，Windows 10 1903 或更新版本；Orca 2.5.0 beta 插件接口。此包保留包名，安装时可能替换旧队列包。旧 v3 队列数据不迁移；独立版使用 v4-cloud。回退时停用测试版，重新安装原先的 0.7.8 wheel。不要同时启用两份队列插件。

先验证：能否收取验证码、是否出现 A1/P1S、AMS 颜色和槽位是否正确、Handy 与 Orca 是否同时在线。请先不要开始无人值守打印。云端登录、真实打印、换盘和 Handy 同时在线尚未验收；当前离线测试不代表这些已通过。

登录会话由内置开源组件保存在本插件私有目录，目录权限限制为当前 Windows 用户与 SYSTEM，未加密。退出本插件账号清除该组件的本地会话，不调用远程账号注销。关闭 Orca 会结束组件进程；打印机上的已开始任务不会因此停止。

English
Install the .whl using Orca’s plugin manager after pausing and reconciling the old queue. Disable the old queue plugin first. Open Print Queue → Connection guide and sign in using an email/SMS verification code. No separate installer, Docker service or Open Bamboo plugin is required. Existing networking files are untouched.
Windows x64 only (Windows 10 1903+). Old v3 queues stay separate from v4-cloud. This is a preview: real cloud login, simultaneous Handy access, AMS printing and plate swapping still need supervised device validation. Session files use a private Windows ACL and are not encrypted.
'''
    entries['orca_plate_queue/README.txt']=instructions.encode()
    dist='orca_plate_queue-'+VERSION+'.dist-info/'
    entries[dist+'METADATA']=(
        'Metadata-Version: 2.4\nName: orca-plate-queue\nVersion: '+VERSION+'\n'
        'Summary: Independent cloud A1/P1S print queue preview with bundled networking component\n'
        'Author: Orca Plate Queue contributors\nRequires-Python: >=3.12\n'
        'Import-Name: orca_plate_queue\nLicense-Expression: AGPL-3.0-or-later\n'
        'License-File: LICENSE\nLicense-File: NOTICE\n\n'+notice).encode()
    # Orca 2.5.0-rc requires an explicit CPython prefix for platform wheels.
    # The host EXE has no Python ABI dependency; these are the tested interpreters.
    # Do not advertise -any: the bundled executable and DLLs are Windows x64.
    entries[dist+'WHEEL']=(
        'Wheel-Version: 1.0\nGenerator: OrcaPlateQueueStandalone\n'
        'Root-Is-Purelib: false\nTag: cp312-none-win_amd64\nTag: cp313-none-win_amd64\n'
    ).encode()
    entries[dist+'top_level.txt']=b'orca_plate_queue\n'
    entries[dist+'LICENSE']=license_text;entries[dist+'NOTICE']=notice.encode()
    record=io.StringIO(newline='');writer=csv.writer(record,lineterminator='\n')
    for name,data in sorted(entries.items()):
        token=base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode()
        writer.writerow([name,'sha256='+token,len(data)])
    writer.writerow([dist+'RECORD','','']);entries[dist+'RECORD']=record.getvalue().encode()
    OUT.mkdir(parents=True,exist_ok=True)
    wheel=OUT/'Orca_Plate_Queue_win_x86_64.whl'
    wheel.write_bytes(archive_bytes(entries))
    source_names=set(SOURCES+EXTRA+['LICENSE','NOTICE'])
    sources={'orca-plate-queue/'+name:(ROOT/name).read_bytes() for name in sorted(source_names) if (ROOT/name).is_file()}
    sources['orca-plate-queue/BUILD-STANDALONE.txt']=(
        'Windows x64 MSVC v142 + SDK 10.0.19041; Python 3.12+.\n'
        'Extract vendor/open-bamboo-b14f880.tar.gz and set ORCA_QUEUE_UPSTREAM_SOURCE to its root.\n'
        'Set ORCA_QUEUE_MSVC_ROOT to the portable MSVC installation.\n'
        'Set ORCA_QUEUE_VCRT_DIR to Microsoft x64 CRT 14.40+ redistributable DLLs (all from one version).\n'
        'Obtain pinned b14f880 ABI 02.08.04 core via native/build_public_bridges.py.\n'
        'python native/build_owned_host.py --fixture\npython -m unittest test_owned_connection -v\n'
        'python native/build_owned_host.py\npython build_standalone_release.py\n'
        'The checked-in stable runtime defaults to native mode; this builder explicitly selects owned_cloud.\n').encode()
    (OUT/('source-'+VERSION+'.zip')).write_bytes(archive_bytes(sources))
    (OUT/'安装与测试说明.txt').write_text(instructions,encoding='utf-8')
    (OUT/'NOTICE').write_text(notice,encoding='utf-8')
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir() if p.is_file() and p.name not in ('SHA256SUMS.txt','validation.json')}
    (OUT/'SHA256SUMS.txt').write_text(''.join(digest+'  '+name+'\n' for name,digest in sorted(hashes.items())),encoding='utf-8')
    print(wheel)


if __name__=='__main__':
    main()
