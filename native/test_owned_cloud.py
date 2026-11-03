"""Build the isolated agent experiment and test only against a fake SDK."""
from pathlib import Path
import ctypes
import json
import os
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
if os.name != 'nt':
    raise SystemExit('This lifecycle experiment currently targets Windows x64.')
import build_bridge
SOURCE = Path(os.environ.get('ORCA_QUEUE_UPSTREAM_SOURCE', str(build_bridge.SOURCE)))
OUT = ROOT / 'owned-cloud-test'
OUT.mkdir(exist_ok=True)
# Build into the isolated test directory. Never use a production networking binary.
(OUT / 'forwarders.inc').write_bytes((ROOT / 'public-build/02.08.04/forwarders.inc').read_bytes())
env = build_bridge.compiler_environment()
cl = str(Path(env['PATH'].split(';')[0]) / 'cl.exe')
common = [cl, '/nologo', '/std:c++17', '/EHsc', '/MD', '/O2', '/utf-8', '/W4', '/wd4190',
          '/DABI_VERSION=0x020804', '/D_ITERATOR_DEBUG_LEVEL=0', '/DNOMINMAX',
          '/I'+str(SOURCE/'include'), '/I'+str(ROOT), '/I'+str(OUT)]
def run(args):
    subprocess.run(args, cwd=OUT, env=env, check=True)
run(common + ['/LD', str(ROOT/'test_owned_backend.cpp'), str(SOURCE/'src/json_lite.cpp'),
              '/link', '/OUT:'+str(OUT/'orca_queue_owned_backend.dll')])
run(common + ['/LD', str(ROOT/'owned_cloud.cpp'), str(ROOT/'queue_cache.cpp'), str(SOURCE/'src/json_lite.cpp'),
              '/link', '/OUT:'+str(OUT/'orca_queue_owned_cloud.dll')])
dll = ctypes.CDLL(str(OUT/'orca_queue_owned_cloud.dll'))
for name in ('oq_owned_open_v1', 'oq_owned_ticket_v1'):
    f = getattr(dll, name)
    f.argtypes = [ctypes.c_char_p, ctypes.c_uint32]
    f.restype = ctypes.c_int
for name in ('oq_owned_connect_v1', 'oq_owned_refresh_v1', 'oq_owned_close_v1'):
    f = getattr(dll, name)
    f.argtypes = []
    f.restype = ctypes.c_int
dll.oq_owned_snapshot_v1.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
dll.oq_owned_snapshot_v1.restype = ctypes.c_int
def snap():
    n = dll.oq_owned_snapshot_v1(None, 0)
    assert 0 < n < 2*1024*1024
    buffer = ctypes.create_string_buffer(n + 4096)
    actual = dll.oq_owned_snapshot_v1(buffer, len(buffer))
    assert 0 < actual <= len(buffer)
    return json.loads(buffer.value)
def op(value):
    data = json.dumps(value).encode()
    return dll.oq_owned_open_v1(data, len(data))
assert snap()['attached'] is False
assert dll.oq_owned_connect_v1() == -1
assert dll.oq_owned_close_v1() == 0
assert op({'storage': 'relative', 'region': 'CN'}) == -2
with tempfile.TemporaryDirectory(prefix='owned-', dir=OUT) as storage:
    assert op({'storage': storage, 'region': 'other'}) == -2
    assert op({'storage': storage, 'region': 'CN'}) == 0
    assert op({'storage': storage, 'region': 'CN'}) == -3
    assert dll.oq_owned_connect_v1() == -1
    ticket = b'fixture-ticket'
    assert dll.oq_owned_ticket_v1(ticket, len(ticket)) == 0
    assert dll.oq_owned_ticket_v1(ticket, len(ticket)) == -3
    assert dll.oq_owned_connect_v1() == 0
    assert dll.oq_owned_refresh_v1() in (0, 1)
    import time
    for _ in range(100):
        state = snap()
        if state.get('devices') and not state.get('refreshing'): break
        time.sleep(.02)
    assert len(state['devices']) == 2
    assert state['origin'] == 'orca-owned-cloud'
    assert state['cloud_session_reused'] is False
    assert state['can_submit'] is False and state['prototype'] is True
    assert 'TEST-SECRET' not in json.dumps(state) and 'NEVER-EXPORTED' not in json.dumps(state)
    tiny = ctypes.create_string_buffer(b'abc', 4)
    assert dll.oq_owned_snapshot_v1(tiny, 4) > 4 and tiny.raw == b'abc\x00'
    assert dll.oq_owned_close_v1() == 0
    assert dll.oq_owned_close_v1() == 0
    assert snap()['attached'] is False
    assert dll.oq_owned_refresh_v1() == -1
print('PASS: owned agent lifecycle, login ticket boundary and private snapshots; fake SDK only.')
