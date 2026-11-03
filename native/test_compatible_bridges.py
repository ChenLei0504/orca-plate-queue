"""Run new wrappers against fake SDKs only; never load real user/upstream cores."""
from pathlib import Path
import json,shutil,subprocess
from build_bridge import ROOT,SOURCE,compiler_environment

def main():
    env=compiler_environment();cl=str(Path(env['PATH'].split(';')[0])/'cl.exe')
    built=ROOT/'compatible-build'
    manifest=json.loads((built/'components.json').read_text())
    for key,spec in manifest['series'].items():
        out=built/'tests'/key;out.mkdir(parents=True,exist_ok=True)
        common=[cl,'/nologo','/std:c++17','/EHsc','/MD','/O2','/utf-8','/W4','/wd4190',
                '/DABI_VERSION=0x'+spec['abi'].replace('.',''),'/D_ITERATOR_DEBUG_LEVEL=0','/DNOMINMAX',
                '/I'+str(SOURCE/'include'),'/I'+str(ROOT)]
        for name in ('test_host.cpp','test_upstream.cpp'):
            source=(ROOT/name).read_text(encoding='utf8')
            source=source.replace('bambu_networking_02.03.00.dll',spec['bridge']).replace('orca_queue_upstream_020300_b14f880.dll',spec['backend']).replace('02.03.00',spec['abi'])
            (out/name).write_text(source,encoding='utf8')
        shutil.copyfile(built/key/spec['bridge'],out/spec['bridge'])
        def run(command):subprocess.run(command,cwd=out,env=env,check=True)
        run(common+['/LD',str(out/'test_upstream.cpp'),str(SOURCE/'src/json_lite.cpp'),'/link','/OUT:'+str(out/spec['backend'])])
        run(common+[str(out/'test_host.cpp'),str(SOURCE/'src/json_lite.cpp'),'/Fe:'+str(out/'test_host.exe')])
        run([str(out/'test_host.exe')])
        print('PASS adaptive wrapper',key,flush=True)
    print('All four adapter entries passed fake SDK tests; no real library or printer was used.')
if __name__=='__main__':main()