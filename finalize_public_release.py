"""Collect completed isolated checks and write a reviewable distribution ZIP."""
from pathlib import Path
import datetime
import hashlib
import html
import json
import re
import zipfile
from release_info import QUEUE_VERSION, QUEUE_BUILD_ID

ROOT=Path(__file__).resolve().parent
OUT=ROOT/('public-release-'+QUEUE_VERSION)


def main():
    py=(ROOT/'verification/split-python-tests.log').read_text(encoding='utf8')
    dom=(ROOT/'verification/split-dom-tests.log').read_text(encoding='utf8')
    native=(ROOT/'verification/ams-native-tests.log').read_text(encoding='utf8')
    installer=(ROOT/'verification/split-installer-tests.log').read_text(encoding='utf8')
    assert 'PASS standalone installer:' in installer
    package_tests=(ROOT/'verification/split-package-tests.log').read_text(encoding='utf8')
    assert '\nOK' in package_tests and 'FAILED' not in package_tests
    assert '\nOK' in py and 'FAILED' not in py
    count=int(re.search(r'Ran (\d+) tests',py)[1])
    pages=int(re.search(r'(\d+) page workflow tests passed',dom)[1])
    for series in ('02.03.00','02.08.01','02.08.04'):assert 'PASS isolated SDK ABI '+series in native
    assert 'PASS production cloud serializer preserves unused versus external markers' in native
    layouts={}
    local_path=ROOT/'verification/split-local-install.json'
    local=json.loads(local_path.read_text(encoding='utf8')) if local_path.is_file() else None
    if local and local.get('version')!=QUEUE_VERSION:local=None
    # Distribution reports must never copy workstation backup paths or queue contents.
    local_public=dict(queue_entry_staged=True,native_files_unchanged=local['native_files_unchanged'],requires_plugin_reload=local['requires_plugin_reload']) if local else None
    for name in ('desktop','narrow'):
        source=(ROOT/f'verification/public-release/{name}.html').read_text(encoding='utf8')
        match=re.search(r'data-report="([^"]+)"',source);assert match
        report=json.loads(html.unescape(match[1]));assert not report['overflow']
        assert report['scroll']<=report['width']
        layouts[name]=dict(width=report['width'],horizontal_overflow=False,inspected=True)
    report=dict(version=QUEUE_VERSION,build_id=QUEUE_BUILD_ID,channel='public-testing',date=datetime.datetime.now().astimezone().isoformat(),
        python_tests=count,python_result='passed',page_workflow_tests=pages,page_result='passed',
        final_package_tests=int(re.search(r'Ran (\d+) tests',package_tests)[1]),
        native_series={s:'isolated fake SDK host passed' for s in ('02.03.00','02.08.01','02.08.04')},
        package_checks='RECORD hashes, modular preferred runtime source, no DLL/executable/installer/development scripts inside queue wheel, exact separately packaged native hashes, separate complete source and original notices, private-data exclusions passed',
        connection_checks='standalone C# installer fixture-only check/install/no-op/backup/restore, running-Orca guard, tampering and unknown SDK rejection, external-update preservation, camera preservation, install and restore rollback passed; queue page rejects installer actions',
        runtime_boundaries='no process execution, dynamic Python execution, environment lookup or connection installer code; native calls bind an existing Orca module handle; no filesystem-based third-party DLL loading',
        marketplace_audit='not rerun on Orca Cloud; native code capability remains disclosed; no guaranteed risk rating',
        standalone_installer='visible .NET Framework x64 GUI; no PowerShell, Python, network, subprocess or SDK execution; unsigned; source and checksums supplied',
        task_monitor='pure reducer with durable ordered start/end evidence; per-device bounded native callback history and epochs; missed polling replay through FINISH/IDLE; primary identity and supplemental ID handling; temporary identity gaps and 60-second reconnect; external stop and foreign activity interlocks; no progress-only completion',
        material_mapping='ams_mapping_info passed through every reviewed SDK ABI; sparse source IDs, source/target colors, preset/type and available nozzle map preserved; unused entries use 255/255 while actually used external entries use 255/0; production upstream cloud serializer verified offline; mismatched/absent details rejected before upload; submit requires material revision 2; real AMS feed outcome unverified',
        visual_checks=layouts,real_printer_controls_sent=0,
        real_printer_end_to_end='not executed; see 公开测试清单.txt',
        installed_on_development_machine=bool(local),local_installation=local_public,publicly_published=False,
        existing_development_queue='not opened for writing or migrated by release tooling')
    (OUT/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    manifest=json.loads((OUT/'manifest.json').read_text(encoding='utf8'))
    manifest['files']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(OUT.iterdir()) if p.is_file() and p.name not in ('manifest.json','SHA256SUMS.txt')}
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    hashes=dict(manifest['files']);hashes['manifest.json']=hashlib.sha256((OUT/'manifest.json').read_bytes()).hexdigest()
    (OUT/'SHA256SUMS.txt').write_text('\n'.join(d+'  '+n for n,d in sorted(hashes.items()))+'\n',encoding='utf8')
    archive=ROOT/('Orca-Plate-Queue-'+QUEUE_VERSION+'-Windows-x64-Public.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as package:
        for path in sorted(OUT.iterdir()):
            if path.is_file():package.write(path,'Orca-Plate-Queue-'+QUEUE_VERSION+'/'+path.name)
    with zipfile.ZipFile(archive) as package:assert package.testzip() is None
    print(json.dumps(dict(archive=str(archive),bytes=archive.stat().st_size,python_tests=count,page_tests=pages),ensure_ascii=False))


if __name__=='__main__':main()
