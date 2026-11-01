"""Compile/run isolated native tests. No test calls a real printer or logs in."""
from pathlib import Path
import shutil
import subprocess
from build_bridge import ROOT, SOURCE, BACKEND_NAME, compiler_environment

env=compiler_environment()
cl=str(Path(env['PATH'].split(';')[0])/'cl.exe')
out=ROOT/'build-test';out.mkdir(exist_ok=True)
common=[cl,'/nologo','/std:c++17','/EHsc','/MD','/O2','/utf-8','/W4','/wd4190',
        '/DABI_VERSION=0x020300','/D_ITERATOR_DEBUG_LEVEL=0','/DNOMINMAX',
        '/I'+str(SOURCE/'include'),'/I'+str(ROOT)]
def run(args):subprocess.run(args,cwd=out,env=env,check=True)
run(common+[str(ROOT/'test_cache.cpp'),str(ROOT/'queue_cache.cpp'),str(SOURCE/'src/json_lite.cpp'),'/Fe:'+str(out/'test_cache.exe')])
run([str(out/'test_cache.exe')])
shutil.copyfile(ROOT/'build/bambu_networking_02.03.00.dll',out/'bambu_networking_02.03.00.dll')
run(common+['/LD',str(ROOT/'test_upstream.cpp'),str(SOURCE/'src/json_lite.cpp'),'/link','/OUT:'+str(out/BACKEND_NAME)])
run(common+[str(ROOT/'test_host.cpp'),str(SOURCE/'src/json_lite.cpp'),'/Fe:'+str(out/'test_host.exe')])
run([str(out/'test_host.exe')])
print('Native bridge tests passed. Test backend is confined to build-test.')
