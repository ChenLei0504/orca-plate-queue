"""Build an adapter-only package. No Open Bamboo core is redistributed or installed.

The manifest describes an ABI contract, not an allowlist of core file hashes.
Only bundled wrappers are pinned; a user's compatible core is preserved verbatim.
"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'native'))
from build_bridge import SOURCE,compiler_environment,exports,make_forwarders
VERSION='0.7.4'
OUT=ROOT/'native/compatible-build'

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--build-only',action='store_true')
    parser.add_argument('--package-only',action='store_true')
    args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    if args.package_only:
        manifest=json.loads((OUT/'components.json').read_text())
    else:
        env=compiler_environment();cl=str(Path(env['PATH'].split(';')[0])/'cl.exe')
        baseline=json.loads((ROOT/'native/public-build/bridges.json').read_text())
        prior=json.loads((ROOT/'native/prior-reviewed-bridges.json').read_text())
        manifest=dict(schema=2,version=VERSION,files={},series={})
        for key,abi in [('02.03.00','02.03.00'),('02.08.01','02.08.01'),('02.08.04','02.08.04'),('default','02.08.04')]:
            spec=baseline[abi];folder=OUT/key;folder.mkdir(exist_ok=True)
            backend='orca_queue_backend_'+('default' if key=='default' else abi.replace('.',''))+'.dll'
            bridge='bambu_networking.dll' if key=='default' else 'bambu_networking_'+abi+'.dll'
            names=exports(ROOT/'native/public-build'/abi/spec['backend'])
            (folder/'forwarders.inc').write_text(make_forwarders(names,int(abi.replace('.',''),16)),encoding='utf8')
            command=[cl,'/nologo','/std:c++17','/EHsc','/MD','/O2','/utf-8','/W4','/wd4190',
                     '/DABI_VERSION=0x'+abi.replace('.',''),'/D_ITERATOR_DEBUG_LEVEL=0','/DNOMINMAX',
                     '/DQB_BACKEND_FILENAME=L"'+backend+'"','/I'+str(SOURCE/'include'),'/I'+str(folder),'/I'+str(ROOT/'native'),'/LD',
                     str(ROOT/'native/queue_bridge.cpp'),str(ROOT/'native/queue_cache.cpp'),str(SOURCE/'src/json_lite.cpp'),
                     '/link','/OUT:'+str(folder/bridge)]
            subprocess.run(command,cwd=folder,env=env,check=True)
            assert set(names)<=set(exports(folder/bridge))
            manifest['files'][bridge]=dict(sha256=hashlib.sha256((folder/bridge).read_bytes()).hexdigest(),role='bridge')
            manifest['series'][key]=dict(abi=abi,bridge=bridge,backend=backend,exports=sorted(names),legacy_backend=spec['backend'],
                compatible_bridge_hashes=sorted(set([spec['bridge_sha256'],*prior.get(abi,[])])))
        (OUT/'components.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
    from build_connection_installer import build,test
    build()
    bundle=OUT/'package';(bundle/'bin').mkdir(parents=True,exist_ok=True)
    (bundle/'components.json').write_bytes((OUT/'components.json').read_bytes())
    for key,spec in manifest['series'].items():
        (bundle/'bin'/spec['bridge']).write_bytes((OUT/key/spec['bridge']).read_bytes())
    test(bundle)
    if args.build_only:return
    with zipfile.ZipFile(ROOT/'connection-dist/Orca-Queue-Connection-0.7.3-Windows-x64.zip') as old:
        oldbytes=(ROOT/'connection-dist/Orca-Queue-Connection-0.7.3-Windows-x64.zip').read_bytes()
        assert hashlib.sha256(oldbytes).hexdigest()=='2ada419c29fff877ea86c78cb2e59597e5fc429742d30b9e52770ca467522200'
        # Exact corresponding source for the pinned ABI declarations / JSON code.
        original_source=old.read('Orca-Queue-Connection-0.7.3/source-0.7.3.zip')
        license_bytes=old.read('Orca-Queue-Connection-0.7.3/LICENSE')
    entries={p.relative_to(bundle).as_posix():p.read_bytes() for p in bundle.rglob('*') if p.is_file()}
    entries['OrcaQueueConnectionSetup.exe']=(ROOT/'installer-dist/OrcaQueueConnectionSetup.exe').read_bytes()
    entries['LICENSE']=license_bytes
    entries['NOTICE']=(f'Orca Queue Compatibility Adapter {VERSION}\nAGPL-3.0-or-later.\n'
        'No Open Bamboo networking core, camera or live555 binary is bundled.\n'
        'The wrappers use reviewed ABI declarations and json_lite from Open Bamboo b14f880.\n'
        'Original corresponding source and notices: source-baseline-0.7.3.zip.\n'
        'Current adapter modifications and reproducible build scripts: source/.\n'
        'Installer static checks do not certify future binary behavior; real-device validation is still required.\n').encode()
    entries['使用说明.txt']=(ROOT/'兼容适配器说明.txt').read_bytes()
    entries['source-baseline-0.7.3.zip']=original_source
    for name in ('ConnectionInstaller.cs','ConnectionCompatibility.cs','ConnectionInstallerTests.cs',
                 'ConnectionCompatibilityTests.cs','build_connection_installer.py','build_compatible_connection.py','兼容适配器说明.txt',
                 'native/build_bridge.py','native/queue_bridge.cpp','native/queue_commands.inc','native/queue_cache.cpp',
                 'native/queue_cache.hpp','native/queue_models.hpp','native/test_host.cpp','native/test_upstream.cpp',
                 'native/test_compatible_bridges.py','native/public-build/bridges.json','native/prior-reviewed-bridges.json'):
        entries['source/'+name]=(ROOT/name).read_bytes()
    for key in manifest['series']:
        entries['source/native/compatible-build/'+key+'/forwarders.inc']=(OUT/key/'forwarders.inc').read_bytes()
    entries['SHA256SUMS.txt']='\n'.join(hashlib.sha256(b).hexdigest()+'  '+n for n,b in sorted(entries.items())).encode()
    output=ROOT/'connection-dist'/f'Orca-Queue-Adapter-{VERSION}-Windows-x64.zip'
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,data in sorted(entries.items()):archive.writestr('Orca-Queue-Adapter-'+VERSION+'/'+name,data)
    print(output)
    print('SHA256',hashlib.sha256(output.read_bytes()).hexdigest())

if __name__=='__main__':main()