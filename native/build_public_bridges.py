"""Build each reviewed ABI against its exact bundled upstream, never a user's DLL."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from build_bridge import ROOT, SOURCE, compiler_environment, exports, make_forwarders

SERIES = ('02.03.00','02.08.01','02.08.04')
OUTPUT = ROOT/'public-build'


def main(wheel):
    OUTPUT.mkdir(exist_ok=True)
    env=compiler_environment()
    cl=str(Path(env['PATH'].split(';')[0])/'cl.exe')
    entries={}
    with zipfile.ZipFile(wheel) as archive:
        for series in SERIES:
            short=series.replace('.','')
            upstream_name=f'orca_queue_upstream_{short}_b14f880.dll'
            origin=f'bambu_networking_{series}.dll' if series!='02.08.04' else 'bambu_networking.dll'
            member=next(n for n in archive.namelist() if n.endswith('/bin/win_x64/'+origin))
            folder=OUTPUT/series;folder.mkdir(exist_ok=True)
            upstream=folder/upstream_name;upstream.write_bytes(archive.read(member))
            raw=upstream.read_bytes()
            if (series+'.99').encode() not in raw:
                raise ValueError('Upstream series mismatch: '+origin)
            abi=int(short,16)
            names=exports(upstream)
            (folder/'forwarders.inc').write_text(make_forwarders(names,abi),encoding='utf8')
            command=[cl,'/nologo','/std:c++17','/EHsc','/MD','/O2','/utf-8','/W4',
                     '/DABI_VERSION=0x'+short,'/D_ITERATOR_DEBUG_LEVEL=0','/DNOMINMAX',
                     '/DQB_BACKEND_FILENAME=L"'+upstream_name+'"',
                     '/I'+str(SOURCE/'include'),'/I'+str(folder),'/I'+str(ROOT),'/LD',
                     str(ROOT/'queue_bridge.cpp'),str(ROOT/'queue_cache.cpp'),str(SOURCE/'src/json_lite.cpp'),
                     '/link','/OUT:'+str(folder/f'bambu_networking_{series}.dll')]
            subprocess.run(command,cwd=folder,env=env,check=True)
            built=folder/f'bambu_networking_{series}.dll'
            if not set(names)<=set(exports(built)):
                raise ValueError('Dropped native exports for '+series)
            entries[series]=dict(bridge=built.name,bridge_sha256=hashlib.sha256(built.read_bytes()).hexdigest(),
                                 backend=upstream_name,backend_sha256=hashlib.sha256(raw).hexdigest(),
                                 upstream_exports=len(names),source_revision='b14f880')
        for name in ('BambuSource.dll','live555.dll'):
            member=next(n for n in archive.namelist() if n.endswith('/bin/win_x64/'+name))
            (OUTPUT/name).write_bytes(archive.read(member))
    (OUTPUT/'bridges.json').write_text(json.dumps(entries,indent=2),encoding='utf8')
    print('Reviewed bridges built: '+', '.join(entries))


if __name__=='__main__':main(Path(sys.argv[1]))
