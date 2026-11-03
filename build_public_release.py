"""Build a redistributable offline Orca wheel; never install or contact printers."""
from pathlib import Path
import base64
import csv
import datetime
import hashlib
import io
import json
import re
import runpy
import shutil
import sys
import zipfile

ROOT=Path(__file__).resolve().parent
from release_info import QUEUE_VERSION, QUEUE_BUILD_ID, CONNECTION_VERSION, CONNECTION_DOWNLOAD_URL, CONNECTION_SHA256
OUT=ROOT/('public-release-'+QUEUE_VERSION)
WHEEL_NAME='Orca_Plate_Queue_win_x86_64.whl'
SOURCES=['build_plugin.py','build_public_release.py','printer_models.py',
    'queue_core.py','object_preview.py','queue_domain.py','queue_imports.py','queue_engine.py','task_monitor.py','test_task_monitor.py',
    'queue_fleet.py','native_connection.py','printer_connection.py','swap_support.py','plugin_runtime.py',
    'plugin_page.html','plugin_page.css','plugin_page.js','queue_tab.svg',
    'test_native_connection.py','test_engine.py','test_fleet.py','test_object_preview.py','test_page.cjs',
    'test_plugin.py','test_queue.py','test_refill.py','test_setup.py','test_public_release.py','preview_release.cjs','finalize_public_release.py','verification/capture_public_release.py',
    '.ui-test-tools/package.json','.ui-test-tools/package-lock.json',
    'release_info.py','local_paths.py','page_assets.py','page_preferences.py','page_messages.js','page_i18n.js','ConnectionInstaller.cs','ConnectionInstallerTests.cs','build_connection_installer.py','test_split_release.py','test_page_preferences.py','test_local_paths.py','test_initialization.py','vendor/open-bamboo-b14f880.tar.gz','发布版说明.txt','发布页文案.txt','公开测试清单.txt','连接组件安装说明.txt']
SOURCES+=['test_cache_permissions.py','native/verify_upstream_compatibility.py','docs/open-bamboo-0.2.45-compatibility.md']
SOURCES+=['ConnectionCompatibility.cs','ConnectionCompatibilityTests.cs','build_compatible_connection.py','native/test_compatible_bridges.py','兼容适配器说明.txt']
SOURCES+=['docs/standalone-cloud.md','test_connection_provider.py','native/owned_cloud.cpp','native/test_owned_backend.cpp','native/test_owned_cloud.py','native/public-build/02.08.04/forwarders.inc']
SOURCES+=['docs/provider-contract.md','native/queue_provider_api.h','native/queue_sidecar.cpp','native/build_sidecar.py','native/test_sidecar.cpp']
SOURCES+=['native/'+name for name in ('build_bridge.py','build_public_bridges.py','queue_bridge.cpp',
    'queue_commands.inc','queue_cache.cpp','queue_cache.hpp','queue_models.hpp','test_cache.cpp',
    'test_host.cpp','test_upstream.cpp','test_public_bridges.py','public-build/bridges.json','prior-reviewed-bridges.json')]
SOURCES+=['.gitignore','.github/workflows/compatibility.yml','.github/workflows/publish-orcacloud.yml','ci/publish_orcacloud.py',
    'ci/test_publish_orcacloud.py','GitHub自动发布说明.txt','兼容性检查.txt']


SOURCES+=['tools/legacy_path_host/README.md','tools/legacy_path_host/LegacyPythonHost.cs','tools/legacy_path_host/legacy-host.manifest','tools/legacy_path_host/verify_legacy_paths.py']
SOURCES+=['README.md','docs/render_screenshots.cjs','docs/capture_screenshots.py']
SOURCES+=['docs/images/'+name for name in ('icon.png','overview.png','materials.png','objects.png','swap.png','connection.png','overview-en.png','materials-en.png','objects-en.png','swap-en.png','connection-en.png')]


def sha(data):return hashlib.sha256(data).hexdigest()


def public_source(source):
    source=re.sub(r'^DEFAULT_SWAP_FILE\s*=.*$',"DEFAULT_SWAP_FILE = ''",source,flags=re.M)
    source=source.replace('# author = "Local workspace"','# author = "Orca Plate Queue contributors"')
    return source


def archive_bytes(entries):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name,data in sorted(entries.items()):
            info=zipfile.ZipInfo(name,(2026,10,31,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o644<<16;archive.writestr(info,data)
    return stream.getvalue()


def runtime_entries():
    modules=['local_paths','queue_core','object_preview','printer_models','swap_support','queue_domain',
        'native_connection','printer_connection','queue_imports','task_monitor','queue_engine',
        'queue_fleet','page_assets','page_preferences','release_info']
    entries={}
    for name in modules+['plugin_runtime']:
        source=public_source((ROOT/(name+'.py')).read_text(encoding='utf8'))
        for dependency in modules:
            source=re.sub(r'^from '+dependency+r' import ', 'from .'+dependency+' import ',source,flags=re.M)
        target='core' if name=='plugin_runtime' else name
        entries['orca_plate_queue/'+target+'.py']=source.encode('utf8')
    entries['orca_plate_queue/__init__.py']=b'from .core import *\n'
    for name in ('plugin_page.html','plugin_page.css','plugin_page.js','page_messages.js','page_i18n.js','queue_tab.svg'):
        entries['orca_plate_queue/'+name]=(ROOT/name).read_bytes()
    return entries


def wheel_bytes(package,license_text,notice):
    package=dict(package)
    package['orca_plate_queue/LICENSE']=license_text
    package['orca_plate_queue/NOTICE']=notice
    package['orca_plate_queue/README.txt']=(ROOT/'发布版说明.txt').read_bytes()
    package['orca_plate_queue/permissions.json']=json.dumps(dict(
        version=QUEUE_VERSION,connection_installation=False,other_plugin_file_modification=False,
        bundled_native_libraries=False,process_execution=False,dynamic_code_execution=False,
        environment_variable_access=False,private_storage_writes=True,
        native_calls='read and call the existing Orca-loaded bridge handle only',
        user_selected_file_reads='single plate and swap 3MF files',
        deletion='only plugin-owned temporary imports and pending files',
        source='Preferred runtime Python, HTML, CSS and JavaScript sources are the installed package files.'),indent=2).encode()
    dist='orca_plate_queue-'+QUEUE_VERSION+'.dist-info/'
    package[dist+'METADATA']=(
        'Metadata-Version: 2.4\nName: orca-plate-queue\nVersion: '+QUEUE_VERSION+'\n'
        'Summary: A1/P1S queues using a separately installed Orca connection bridge\n'
        'Author: Orca Plate Queue contributors\nRequires-Python: >=3.12\n'
        'Import-Name: orca_plate_queue\nLicense-Expression: AGPL-3.0-or-later\n'
        'License-File: LICENSE\nLicense-File: NOTICE\nDescription-Content-Type: text/plain; charset=UTF-8\n\n'
        'Windows x64. Networking bridge installation and restoration are separate from this queue plugin.\n'
        'Runtime preferred source is included as readable Python and page assets; no DLLs or development scripts are bundled.\n').encode()
    package[dist+'WHEEL']=b'Wheel-Version: 1.0\nGenerator: OrcaPlateQueue\nRoot-Is-Purelib: true\nTag: py3-none-any\n'
    package[dist+'top_level.txt']=b'orca_plate_queue\n'
    package[dist+'LICENSE']=license_text;package[dist+'NOTICE']=notice
    record=io.StringIO(newline='');writer=csv.writer(record,lineterminator='\n')
    for name,data in sorted(package.items()):
        token=base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode()
        writer.writerow([name,'sha256='+token,len(data)])
    writer.writerow([dist+'RECORD','','']);package[dist+'RECORD']=record.getvalue().encode()
    return archive_bytes(package)


def build_adapter_release(connection_zip):
    """Package a queue-only release with the reviewed adapter, never an old core."""
    data=connection_zip.read_bytes()
    if sha(data)!=CONNECTION_SHA256:
        raise ValueError('Connection adapter hash mismatch')
    prefix='Orca-Queue-Connection-'+CONNECTION_VERSION+'/'
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        manifest=json.loads(package.read(prefix+'components.json'))
        if manifest['schema']!=2 or manifest['version']!=CONNECTION_VERSION:
            raise ValueError('Expected current adapter-only manifest')
        for name,row in manifest['files'].items():
            if row['role']!='bridge' or sha(package.read(prefix+'bin/'+name))!=row['sha256']:
                raise ValueError('Adapter payload mismatch: '+name)
        binaries={n[len(prefix+'bin/'):] for n in package.namelist() if n.startswith(prefix+'bin/')}
        if binaries!=set(manifest['files']):
            raise ValueError('Unexpected bundled networking core')
        license_text=package.read(prefix+'LICENSE')
        adapter_notice=package.read(prefix+'NOTICE')
    OUT.mkdir(exist_ok=True)
    runpy.run_path(str(ROOT/'build_plugin.py'))
    notice=('Orca Plate Queue '+QUEUE_VERSION+' — Open Bamboo compatibility preview\n'
        'Queue and forwarding adapter: AGPL-3.0-or-later.\n'
        'The queue wheel contains no native networking library or installer.\n'
        'The adapter preserves the user-installed compatible Open Bamboo core; no core binary is bundled.\n'
        'Original baseline source/notices and adapter changes are in the separate connection ZIP.\n'
        'Independent community project; no official endorsement.\n').encode()
    source={}
    for name in SOURCES:
        content=(ROOT/name).read_bytes()
        if name=='swap_support.py':content=public_source(content.decode('utf8')).encode('utf8')
        source['orca-queue/'+name]=content
    source['orca-queue/LICENSE']=license_text
    source['orca-queue/NOTICE']=notice+adapter_notice
    source['orca-queue/BUILD.txt']=(
        'Queue-only build: place the reviewed adapter ZIP in connection-dist/, then run python build_public_release.py.\n'
        'Adapter build: follow the source-baseline and source/ instructions in the connection ZIP.\n'
        'Run python build_plugin.py, python -m unittest discover -q and node test_page.cjs.\n').encode()
    artifacts={WHEEL_NAME:wheel_bytes(runtime_entries(),license_text,notice),
        connection_zip.name:data, 'source-'+QUEUE_VERSION+'.zip':archive_bytes(source),
        'LICENSE':license_text,'NOTICE':notice}
    for name in ('发布版说明.txt','公开测试清单.txt','连接组件安装说明.txt','兼容适配器说明.txt'):
        artifacts[name]=(ROOT/name).read_bytes()
    for name,content in artifacts.items():(OUT/name).write_bytes(content)
    summary=dict(version=QUEUE_VERSION,build_id=QUEUE_BUILD_ID,release_channel='local-compatibility-preview',
        platform='windows-x64',tested_host='OrcaSlicer 2.5.0-rc',
        target_open_bamboo='0.2.45',target_source_revision='32e31a3f0985ebf481ae738290a7482b92d3072f',
        adapter_source_baseline='b14f880',bundled_networking_core=False,publicly_published=False,
        real_printer_acceptance='pending',connection_version=CONNECTION_VERSION,
        connection_download_url=CONNECTION_DOWNLOAD_URL,files={n:sha(b) for n,b in artifacts.items()})
    (OUT/'manifest.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
    print('Prepared adapter-only compatibility release: '+str(OUT))


def main(upstream_wheel=None):
    adapter=ROOT/'connection-dist'/('Orca-Queue-Connection-'+CONNECTION_VERSION+'-Windows-x64.zip')
    if adapter.is_file():
        with zipfile.ZipFile(adapter) as archive:
            entry='Orca-Queue-Connection-'+CONNECTION_VERSION+'/components.json'
            if json.loads(archive.read(entry)).get('schema')==2:
                return build_adapter_release(adapter)
    OUT.mkdir(exist_ok=True)
    runpy.run_path(str(ROOT/'build_plugin.py'))
    native=ROOT/'native/public-build'
    bridges=json.loads((native/'bridges.json').read_text(encoding='utf8'))
    resources={};files={};series={}
    prior=json.loads((ROOT/'native/prior-reviewed-bridges.json').read_text(encoding='utf8'))
    prior03=['327db41359e6a1fff9a079e1fc96f0dc06bb80cd95d8c693a72b99f2ebc62935',
        '93136b28df28b4466ef90b371060d214c7f3f89dfe7b502fe3bedd0493de6f0d',
        '84253779ccdfa3a7d123ce20f1c65a9c74b4442d88ed1604b4b02af922df9039']
    for version,spec in bridges.items():
        for field,role in (('backend','backend'),('bridge','bridge')):
            name=spec[field];data=(native/version/name).read_bytes()
            if sha(data)!=spec[field+'_sha256']:raise ValueError('Native hash mismatch: '+name)
            resources['bin/'+name]=data;files[name]=dict(sha256=sha(data),role=role)
        series[version]=dict(bridge=spec['bridge'],backend=spec['backend'],compatible_bridge_hashes=list(dict.fromkeys((prior03 if version=='02.03.00' else [])+prior.get(version,[]))))
    resources['bin/bambu_networking.dll']=resources['bin/'+series['02.08.04']['bridge']]
    files['bambu_networking.dll']=dict(sha256=sha(resources['bin/bambu_networking.dll']),role='bridge')
    for name in ('BambuSource.dll','live555.dll'):
        data=(native/name).read_bytes();resources['bin/'+name]=data
        files[name]=dict(sha256=sha(data),role='sidecar',preserve_existing=True)
    manifest=dict(schema=1,version=QUEUE_VERSION,upstream_revision='b14f880',files=files,series=series)
    resources['components.json']=json.dumps(manifest,ensure_ascii=False,indent=2).encode('utf8')
    upstream={}
    with zipfile.ZipFile(upstream_wheel) as archive:
        for name in ('NOTICE','LICENSE.AGPL','LICENSE'):
            member=next(n for n in archive.namelist() if n.endswith('.dist-info/'+name))
            upstream[name]=archive.read(member)
        if b'b14f880' not in upstream['NOTICE']:raise ValueError('Expected reviewed upstream notice')
        for version,spec in bridges.items():
            origin='bambu_networking.dll' if version=='02.08.04' else f'bambu_networking_{version}.dll'
            member=next(n for n in archive.namelist() if n.endswith('/bin/win_x64/'+origin))
            if sha(archive.read(member))!=spec['backend_sha256']:raise ValueError('Upstream mismatch')
    notice=('Orca Plate Queue '+QUEUE_VERSION+' — split public testing release\n'
        'Queue plugin and native bridge modifications: AGPL-3.0-or-later.\n'
        'The queue wheel contains readable preferred runtime source; it contains no native DLLs or installers.\n'
        'Open Bamboo binaries, their exact corresponding source and original notices are in the separate Connection ZIP.\n'
        'The full project source, build scripts and tests are distributed separately in source-'+QUEUE_VERSION+'.zip.\n'
        'Independent community project; no official endorsement.\n').encode('utf8')
    source_entries={}
    for name in SOURCES:
        data=(ROOT/name).read_bytes()
        if name=='swap_support.py':data=public_source(data.decode('utf8')).encode('utf8')
        source_entries['orca-queue/'+name]=data
    source_entries['orca-queue/LICENSE']=upstream['LICENSE.AGPL']
    source_entries['orca-queue/NOTICE']=notice+upstream['NOTICE']
    source_entries['orca-queue/BUILD.txt']=('Python 3.12+, Windows x64, MSVC v142 and Windows SDK 10.0.19041.0.\n'
        'Unpack the pinned upstream tar to vendor/sources/open-bamboo-networking-b14f880.\n'
        'Supply reviewed Open Bamboo 0.2.43 wheel b14f880; portable compiler under vendor/msvc.\n'
        'python native/build_public_bridges.py PATH_TO_UPSTREAM_WHEEL\n'
        'python native/test_public_bridges.py\n'
        'python build_public_release.py PATH_TO_UPSTREAM_WHEEL\n'
        'python -m unittest discover -q\n'
        'npm ci --prefix .ui-test-tools --ignore-scripts; node test_page.cjs\n'
        'python build_connection_installer.py runs fixture-only installer checks.\n'
        'No tests, build scripts or compilers are inside the queue wheel.\n'
        + 'For queue-only releases, place the published connection ZIP in connection-dist/; obtain it from '+CONNECTION_DOWNLOAD_URL+' and verify SHA256 '+CONNECTION_SHA256+'.\n').encode()
    for version in bridges:
        source_entries[f'orca-queue/native/public-build/{version}/forwarders.inc']=(native/version/'forwarders.inc').read_bytes()
    source_zip=archive_bytes(source_entries)
    resources['source-'+QUEUE_VERSION+'.zip']=source_zip
    resources['LICENSE']=upstream['LICENSE.AGPL'];resources['NOTICE']=notice+upstream['NOTICE']
    resources['licenses/Open-Bamboo-Installer-GPL.txt']=upstream['LICENSE']
    installer_name='Orca-Queue-Connection-'+CONNECTION_VERSION+'-Windows-x64.zip'
    if CONNECTION_VERSION != QUEUE_VERSION:
        pinned=ROOT/'connection-dist'/installer_name
        if not pinned.is_file():
            raise ValueError('Place the published connection ZIP at '+str(pinned)+'; download it manually from '+CONNECTION_DOWNLOAD_URL)
        installer=pinned.read_bytes()
        if sha(installer)!=CONNECTION_SHA256:raise ValueError('Published connection installer hash mismatch')
        with zipfile.ZipFile(io.BytesIO(installer)) as archive:
            prefix='Orca-Queue-Connection-'+CONNECTION_VERSION+'/'
            for name in files:
                if sha(archive.read(prefix+'bin/'+name))!=files[name]['sha256']:raise ValueError('Connection binary changed; a new connection release is required')
    else:
        from build_connection_installer import build
        build()
        resources['OrcaQueueConnectionSetup.exe']=(ROOT/'installer-dist/OrcaQueueConnectionSetup.exe').read_bytes()
        resources['ConnectionInstaller.cs']=(ROOT/'ConnectionInstaller.cs').read_bytes()
        resources['使用说明.txt']=(ROOT/'连接组件安装说明.txt').read_bytes()
        installer=archive_bytes({'Orca-Queue-Connection-'+CONNECTION_VERSION+'/'+n:d for n,d in resources.items()})
    (OUT/installer_name).write_bytes(installer)
    package=runtime_entries()
    (OUT/WHEEL_NAME).write_bytes(wheel_bytes(package,upstream['LICENSE.AGPL'],notice))
    (OUT/('source-'+QUEUE_VERSION+'.zip')).write_bytes(source_zip)
    for name in ('发布版说明.txt','发布页文案.txt','公开测试清单.txt','连接组件安装说明.txt','兼容性检查.txt'):
        shutil.copyfile(ROOT/name,OUT/name)
    (OUT/'LICENSE').write_bytes(upstream['LICENSE.AGPL']);(OUT/'NOTICE').write_bytes(notice)
    summary=dict(version=QUEUE_VERSION,build_id=QUEUE_BUILD_ID,release_channel='public-testing',platform='windows-x64',
        tested_host='OrcaSlicer 2.5.0 beta',upstream_revision='b14f880',native_series=list(bridges),
        distribution='queue wheel + separate connection installer + corresponding project source',
        existing_queue_storage='v3 unchanged',publicly_published=False,
        connection_version=CONNECTION_VERSION,connection_download_url=CONNECTION_DOWNLOAD_URL,
        files={p.name:sha(p.read_bytes()) for p in OUT.iterdir() if p.is_file() and p.name not in ('manifest.json','validation.json','SHA256SUMS.txt')})
    (OUT/'manifest.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
    print('Prepared split release: '+str(OUT))


if __name__=='__main__':main(Path(sys.argv[1]) if len(sys.argv)>1 else None)
