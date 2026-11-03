"""Build the private Windows x64 host and pinned backend. Never installs into Orca."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import build_bridge

ROOT = Path(__file__).resolve().parent
SOURCE = Path(os.environ.get('ORCA_QUEUE_UPSTREAM_SOURCE', str(build_bridge.SOURCE)))
OUT = ROOT / 'owned-host-build'
PINNED = 'eec88c188dcd83c121f94c91f7cb0f3fcee4a21f603597e63ed6dbd6d37b27aa'
RUNTIME = ('msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll')


def build(fake=False):
    out = ROOT / 'owned-host-fixture' if fake else OUT
    out.mkdir(exist_ok=True)
    shutil.copyfile(ROOT / 'public-build/02.08.04/forwarders.inc', out / 'forwarders.inc')
    env = build_bridge.compiler_environment()
    tools = Path(env['PATH'].split(';')[0])
    cl = tools / 'cl.exe'
    args = [str(cl), '/nologo', '/std:c++17', '/EHsc', '/MD', '/O2', '/utf-8', '/W4', '/wd4190',
            '/DABI_VERSION=0x020804', '/D_ITERATOR_DEBUG_LEVEL=0', '/DNOMINMAX',
            '/I'+str(SOURCE/'include'), '/I'+str(ROOT), '/I'+str(out)]
    if fake:
        subprocess.run(args + ['/LD', str(ROOT/'test_owned_backend.cpp'), str(SOURCE/'src/json_lite.cpp'),
                              '/link', '/OUT:'+str(out/'orca_queue_owned_backend.dll')], cwd=out, env=env, check=True)
    else:
        backend = ROOT/'public-build/02.08.04/orca_queue_upstream_020804_b14f880.dll'
        if hashlib.sha256(backend.read_bytes()).hexdigest() != PINNED:
            raise ValueError('Pinned networking core hash does not match')
        shutil.copyfile(backend, out/'orca_queue_owned_backend.dll')
    subprocess.run(args + [str(ROOT/'owned_host.cpp'), str(ROOT/'queue_cache.cpp'), str(SOURCE/'src/json_lite.cpp'),
        '/link', '/OUT:'+str(out/'orca_queue_host.exe'), '/MANIFEST:EMBED',
        '/MANIFESTINPUT:'+str(ROOT/'owned_host.manifest')], cwd=out, env=env, check=True)
    runtime_dir = Path(os.environ.get('ORCA_QUEUE_VCRT_DIR', str(tools)))
    # A core compiled with recent STL mutex initialization crashes against the
    # old compiler's 14.29 CRT, despite importing the same DLL names.
    import ctypes
    version = ctypes.WinDLL('version.dll')
    version.GetFileVersionInfoSizeW.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p]
    version.GetFileVersionInfoW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p]
    version.VerQueryValueW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_uint)]
    runtime_version = None
    for name in RUNTIME:
        path = runtime_dir / name
        size = version.GetFileVersionInfoSizeW(str(path), None)
        if not size: raise ValueError('Cannot read Microsoft runtime version: '+str(path))
        data = ctypes.create_string_buffer(size)
        if not version.GetFileVersionInfoW(str(path), 0, size, data): raise ValueError('Invalid runtime metadata')
        pointer = ctypes.c_void_p(); length = ctypes.c_uint()
        if not version.VerQueryValueW(data, '\\', ctypes.byref(pointer), ctypes.byref(length)): raise ValueError('Invalid runtime version')
        fields = ctypes.cast(pointer, ctypes.POINTER(ctypes.c_uint32))
        current = (fields[2] >> 16, fields[2] & 65535, fields[3] >> 16, fields[3] & 65535)
        if current[:2] < (14, 40):
            raise ValueError('Set ORCA_QUEUE_VCRT_DIR to Microsoft x64 runtime 14.40+; old compiler CRT crashes the pinned core')
        if runtime_version and current != runtime_version:
            raise ValueError('Microsoft runtime files must come from the same release')
        runtime_version = current
        shutil.copyfile(path, out / name)
    files = ['orca_queue_host.exe', 'orca_queue_owned_backend.dll', *RUNTIME]
    manifest = {'protocol': 1, 'backend_revision': 'b14f880', 'fixture': fake, 'msvc_runtime': list(runtime_version),
                'files': {name: hashlib.sha256((out/name).read_bytes()).hexdigest() for name in files}}
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return out


if __name__ == '__main__':
    import sys
    print(build('--fixture' in sys.argv))
