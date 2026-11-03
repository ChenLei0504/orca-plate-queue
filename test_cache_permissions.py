"""Private cache operations stay on ordinary paths for cloud-installed queues."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from local_paths import fs_path
from queue_engine import QueueService
from queue_fleet import QueueFleet
from test_fleet import FleetTransport


class CachePermissionTests(unittest.TestCase):
    def setUp(self):
        base=Path(__file__).parent/'.test-temp';base.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(prefix='cp-',dir=base)
        self.base=Path(self.temp.name).resolve()
        self.addCleanup(self.temp.cleanup)
        # Same 153-character fleet root as the reported cloud subscription.
        self.root=self.base/('r'*(149-len(str(self.base))))/'v3'
        self.assertEqual(len(str(self.root)),153)
        self.transport=FleetTransport();self.fleets=[]
        self.addCleanup(self.close_fleets)
        self.source=self.base/'model.3mf';self.source.write_bytes(b'fixture-sliced-content')
        self.info=dict(path=str(self.source),sha256=hashlib.sha256(self.source.read_bytes()).hexdigest())

    def close_fleets(self):
        for fleet in self.fleets:fleet.close()

    def open(self):
        def factory(*a,**kw):return QueueService(*a,**kw,start_worker=False)
        fleet=QueueFleet(self.root,self.transport,lambda p:None,lambda p:None,'',service_factory=factory)
        self.fleets.append(fleet);return fleet

    def test_cloud_secondary_import_does_not_request_extended_file_paths(self):
        fleet=self.open();fleet.select('a1',self.transport.snapshot())
        service=fleet.select('p1',self.transport.snapshot())
        self.assertGreater(len(str(self.root/'printers'/('a'*64)/'assets'/('a'*32+'.part'))),248)
        opened=[];original=Path.open
        def audited(path,*args,**kwargs):
            opened.append(str(path))
            if str(path).startswith('\\\\?\\'):raise PermissionError('fixture host cannot recognize extended private path')
            return original(path,*args,**kwargs)
        with patch.object(Path,'open',audited):
            for n in range(3):
                self.source.write_bytes(('content-'+str(n)).encode())
                self.info['sha256']=hashlib.sha256(self.source.read_bytes()).hexdigest()
                asset=service.freeze(self.info)
                self.assertEqual(service.digest(asset['path']),self.info['sha256'])
                self.assertLess(len(str(asset['path'])),248)
        self.assertTrue(any(p.endswith('.part') for p in opened))
        self.assertTrue(all(not p.startswith('\\\\?\\') for p in opened))
        self.assertTrue(Path(asset['path']).is_relative_to(self.root))

    def test_old_task_path_is_preserved_and_new_import_is_short_after_reload(self):
        fleet=self.open();fleet.select('a1',self.transport.snapshot());service=fleet.select('p1',self.transport.snapshot())
        legacy=service.root/'assets'/(self.info['sha256']+'.3mf')
        fs_path(legacy.parent).mkdir(exist_ok=True)
        fs_path(legacy).write_bytes(self.source.read_bytes())
        service.commit(lambda:service.data['jobs'].append(dict(id='legacy',status='等待',path=str(legacy),sha256=self.info['sha256'])))
        fleet.close();fresh=self.open();service=fresh.services['p1']
        self.assertEqual(service.data['jobs'][0]['path'],str(legacy))
        self.assertTrue(fs_path(legacy).exists())
        asset=service.freeze(self.info)
        self.assertLess(len(asset['path']),248)
        self.assertEqual(fs_path(legacy).read_bytes(),Path(asset['path']).read_bytes())
        self.assertFalse(service.data['running'])
        self.assertEqual(self.transport.requests,[])

    def test_longer_profile_keeps_database_uploads_preferences_and_assets_short(self):
        import base64
        import sqlite3
        from queue_imports import LocalImports
        from page_preferences import PagePreferences
        self.root=self.base/('r'*(186-len(str(self.base))))/'v3'
        self.assertEqual(len(str(self.root)),190)
        original=Path.open;connect=sqlite3.connect;opened=[]
        def audited(path,*args,**kwargs):
            opened.append(str(path))
            self.assertLess(len(str(path)),248)
            return original(path,*args,**kwargs)
        def database(path,*args,**kwargs):
            self.assertLess(len(str(path)+'-journal'),248)
            return connect(path,*args,**kwargs)
        with patch.object(Path,'open',audited), patch.object(sqlite3,'connect',database):
            fleet=self.open();fleet.select('a1',self.transport.snapshot())
            service=fleet.select('p1',self.transport.snapshot())
            service.commit(lambda:service.data.update(path_test=True))
            seen=[]
            def enqueue(path,copies,**kw):
                data=Path(path).read_bytes()
                asset=service.freeze(dict(path=path,sha256=hashlib.sha256(data).hexdigest()))
                seen.append(asset);Path(path).unlink();return 'ok'
            imports=LocalImports(lambda:self.root.parent,enqueue)
            for action in ('upload_end','upload_abort'):
                token=imports.handle('upload_begin',dict(name='中文.3mf',size=3))['token']
                imports.handle('upload_chunk',dict(token=token,seq=0,content=base64.b64encode(b'123').decode()))
                imports.handle(action,dict(token=token))
            imports.close()
            preferences=PagePreferences(self.root.parent);preferences.set_language('en')
            self.assertEqual(PagePreferences(self.root.parent).language,'en')
            self.assertEqual(service.digest(seen[0]['path']),hashlib.sha256(b'123').hexdigest())
            Path(seen[0]['path']).unlink()
            fleet.close();self.assertTrue(self.open().services['p1'].data['path_test'])
        self.assertTrue(opened)
        self.assertEqual(self.transport.requests,[])

    def test_existing_legacy_database_is_reopened_without_moving_or_resetting(self):
        fleet=self.open();fleet.select('a1',self.transport.snapshot())
        service=fleet.select('p1',self.transport.snapshot())
        service.commit(lambda:service.data.update(legacy_marker='retained'))
        old=service.root;fleet.close()
        legacy=self.root/'printers'/hashlib.sha256(b'p1').hexdigest()
        legacy.parent.mkdir();old.rename(legacy)
        restored=self.open().services['p1']
        self.assertEqual(restored.root,legacy)
        self.assertEqual(restored.data['legacy_marker'],'retained')
        self.assertFalse(old.exists())

    def test_short_digest_name_collision_never_reuses_different_contents(self):
        fleet=self.open();service=fleet.select('a1',self.transport.snapshot())
        target=service.assets/(self.info['sha256'][:32]+'.3mf')
        target.write_bytes(b'other-content')
        with self.assertRaisesRegex(ValueError,'副本已变化'):
            service.freeze(self.info)
        self.assertEqual(target.read_bytes(),b'other-content')

    def test_queues_do_not_share_owned_copies(self):
        fleet=self.open();a=fleet.select('a1',self.transport.snapshot()).freeze(self.info)
        b=fleet.select('p1',self.transport.snapshot()).freeze(self.info)
        Path(b['path']).unlink()
        self.assertEqual(Path(a['path']).read_bytes(),self.source.read_bytes())

    def test_wrong_namespace_owner_is_rejected_without_overwriting_and_releases_lock(self):
        fleet=self.open();fleet.select('a1',self.transport.snapshot());service=fleet.select('p1',self.transport.snapshot())
        owner=service.assets/'owner';expected=owner.read_text();fleet.close()
        owner.write_text('f'*64)
        with self.assertRaisesRegex(ValueError,'另一条队列'):self.open()
        self.assertEqual(owner.read_text(),'f'*64)
        owner.write_text(expected)
        self.assertEqual(self.open().services['p1'].data['device_id'],'p1')


if __name__=='__main__':unittest.main()
