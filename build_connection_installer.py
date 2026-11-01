"""Compile the visible standalone installer and its fixture-only tests."""
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'installer-dist'
CSC=Path(r'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe')
REFERENCES=['System.Windows.Forms.dll','System.Drawing.dll','System.Runtime.Serialization.dll','System.Core.dll']

def build():
    OUT.mkdir(exist_ok=True)
    common=[str(CSC),'/nologo','/optimize+','/platform:x64','/utf8output']+['/reference:'+r for r in REFERENCES]
    subprocess.run(common+['/target:winexe','/out:'+str(OUT/'OrcaQueueConnectionSetup.exe'),str(ROOT/'ConnectionInstaller.cs')],check=True)
    subprocess.run(common+['/target:exe','/main:ConnectionInstallerTests','/out:'+str(OUT/'ConnectionInstallerTests.exe'),str(ROOT/'ConnectionInstaller.cs'),str(ROOT/'ConnectionInstallerTests.cs')],check=True)

def test(bundle=None):
    import uuid
    folder=ROOT/'verification'/('installer-fixture-'+uuid.uuid4().hex)
    args=[str(OUT/'ConnectionInstallerTests.exe'),str(folder)]
    if bundle:args.append(str(Path(bundle).resolve()))
    subprocess.run(args,check=True)
    return folder

if __name__=='__main__':
    build()
    print(test(sys.argv[1] if len(sys.argv)>1 else None))
