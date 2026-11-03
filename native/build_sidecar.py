"""Build and test the proposed independent DLL using a fake host only."""
from pathlib import Path
import os
import shutil
import subprocess
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'sidecar-build'

def main():
    OUT.mkdir(exist_ok=True)
    if os.name=='nt':
        if shutil.which('cl'):
            env=os.environ.copy()
        else:
            from build_bridge import compiler_environment
            env=compiler_environment()
        cl=shutil.which('cl',path=env['PATH'])
        common=[cl,'/nologo','/std:c++17','/EHsc','/MD','/O2','/utf-8','/W4','/I'+str(ROOT)]
        commands=[common+['/LD',str(ROOT/'queue_sidecar.cpp'),'/link','/OUT:orca_plate_queue.dll','/IMPLIB:orca_plate_queue.lib'],
                  common+[str(ROOT/'test_sidecar.cpp'),'orca_plate_queue.lib','/Fe:test_sidecar.exe'],
                  [str(OUT/'test_sidecar.exe')]]
    else:
        env=os.environ.copy()
        common=[os.environ.get('CXX','c++'),'-std=c++17','-pthread','-Wall','-Wextra','-Werror','-I'+str(ROOT)]
        commands=[common+['-fPIC','-fvisibility=hidden','-shared',str(ROOT/'queue_sidecar.cpp'),'-o','liborca_plate_queue.so'],
                  common+[str(ROOT/'test_sidecar.cpp'),'-L.','-lorca_plate_queue','-Wl,-rpath,$ORIGIN','-o','test_sidecar'],
                  [str(OUT/'test_sidecar')]]
    for command in commands:subprocess.run(command,cwd=OUT,env=env,check=True)
    print('PASS independent provider prototype; fake host only, no SDK/login/printer calls.')
if __name__=='__main__':main()
