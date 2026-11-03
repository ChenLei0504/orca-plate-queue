import sys,os,json,unittest,uuid,shutil
sys.path.insert(0,os.getcwd())
sys.stdout.reconfigure(encoding='utf-8');sys.stderr.reconfigure(encoding='utf-8')
from local_paths import fs_path,canonical_path
from pathlib import Path
base=Path.cwd()/'.test-temp'/('legacy-host-'+uuid.uuid4().hex)
assert base.resolve().is_relative_to((Path.cwd()/'.test-temp').resolve())
base.mkdir(parents=True)
try:
    directory=base/('_subscribed_'+'a'*60)/('b'*64)/('c'*64)/'assets'
    fs_path(directory).mkdir(parents=True)
    target=directory/('d'*32+'.part')
    unprefixed_failed=False
    try:
        target.write_bytes(b'baseline')
    except OSError as exc:
        unprefixed_failed=True
        print('BASELINE unprefixed cache creation failed:',type(exc).__name__,getattr(exc,'winerror',None),flush=True)
    assert unprefixed_failed,'verification host unexpectedly allows unprefixed long paths'
    fs_path(target).write_bytes(b'fixed')
    assert fs_path(target).read_bytes()==b'fixed'
    print('FIXED extended cache creation passed:',len(str(target)),'characters',flush=True)
finally:
    shutil.rmtree(fs_path(base,force=True))
import test_local_paths, test_cache_permissions
suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromModule(module) for module in (test_local_paths, test_cache_permissions))
result=unittest.TextTestRunner(verbosity=2).run(suite)
assert result.wasSuccessful(),'long path tests failed in a legacy embedded host'
print('PASS legacy embedded host: old failure reproduced; all fixed-path tests passed.',flush=True)
