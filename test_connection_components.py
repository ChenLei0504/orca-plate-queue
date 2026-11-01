"""Isolated file transactions only: no AppData writes or printer connections."""
import hashlib
import json
from pathlib import Path
import struct
import unittest
from unittest.mock import patch
from connection_components import ConnectionComponents
from test_queue import temporary_directory


def pe(label):
    raw=bytearray(128);raw[:2]=b'MZ';struct.pack_into('<I',raw,0x3c,64)
    raw[64:68]=b'PE\0\0';struct.pack_into('<H',raw,68,0x8664)
    return bytes(raw)+label.encode()


class ComponentsTests(unittest.TestCase):
    def setUp(self):
        self.temp=temporary_directory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name);self.bundle=root/'bundle';self.bundle.mkdir()
        self.target=root/'plugins';self.target.mkdir();self.store=root/'store'
        self.files={};series={}
        for version in ('02.03.00','02.08.01','02.08.04'):
            bridge=f'bambu_networking_{version}.dll';backend='backend_'+version+'.dll'
            for name,role in ((bridge,'bridge'),(backend,'backend')):
                data=pe(name);(self.bundle/name).write_bytes(data)
                self.files[name]=dict(sha256=hashlib.sha256(data).hexdigest(),role=role)
            series[version]=dict(bridge=bridge,backend=backend)
        data=pe('default');(self.bundle/'bambu_networking.dll').write_bytes(data)
        self.files['bambu_networking.dll']=dict(sha256=hashlib.sha256(data).hexdigest(),role='bridge')
        data=pe('sidecar');(self.bundle/'live555.dll').write_bytes(data)
        self.files['live555.dll']=dict(sha256=hashlib.sha256(data).hexdigest(),role='sidecar',preserve_existing=True)
        self.manifest=dict(schema=1,files=self.files,series=series);self.save_manifest()
        self.manager=self.make()

    def save_manifest(self):
        (self.bundle/'components.json').write_text(json.dumps(self.manifest),encoding='utf8')

    def make(self,**kw):return ConnectionComponents(self.bundle,self.store,self.target,probe=lambda:[],**kw)

    def test_fresh_install_and_restore_removes_only_owned_files(self):
        keep=self.target/'untouched.conf';keep.write_text('private')
        self.manager.install();self.assertTrue(self.manager.status()['installed'])
        self.assertTrue(self.manager.status()['restart_required'])
        self.manager.restore();self.assertEqual(list(self.target.iterdir()),[keep])
        self.assertFalse(self.manager.status()['restore_available'])

    def test_existing_open_bamboo_is_detected_and_exact_bytes_restored(self):
        spec=self.manifest['series']['02.03.00'];original=(self.bundle/spec['backend']).read_bytes()
        (self.target/spec['bridge']).write_bytes(original)
        self.assertEqual(self.manager.status()['series'][0]['kind'],'open_bamboo')
        self.manager.install();self.manager.restore()
        self.assertEqual((self.target/spec['bridge']).read_bytes(),original)

    def test_unknown_existing_is_backed_up_without_deleting_other_versions(self):
        name='bambu_networking_02.08.01.dll';old=pe('another build')
        (self.target/name).write_bytes(old);other=self.target/'bambu_networking_99.00.00.dll';other.write_bytes(b'future')
        self.manager.install();self.manager.restore()
        self.assertEqual((self.target/name).read_bytes(),old);self.assertEqual(other.read_bytes(),b'future')

    def test_noop_install_keeps_original_recovery_receipt(self):
        self.manager.install();before=(self.store/'latest-install.json').read_bytes()
        self.manager.install();self.assertEqual((self.store/'latest-install.json').read_bytes(),before)
        self.manager.restore();self.assertFalse(any(self.target.iterdir()))

    def test_loaded_compatible_series_reuses_existing_session(self):
        self.manager.install();self.manager=self.make();self.manager.probe=lambda:[dict(series='02.08.01',queue_api=True)]
        self.assertTrue(self.manager.status()['ready'])
        self.manager.probe=lambda:[dict(series='02.08.01',queue_api=False)]
        self.assertFalse(self.manager.status()['ready'])

    def test_unversioned_current_library_is_detected(self):
        self.manager.install();self.manager=self.make();self.manager.probe=lambda:[dict(series='default',queue_api=True)]
        self.assertTrue(self.manager.status()['ready'])

    def test_reviewed_legacy_bridge_is_accepted(self):
        self.manager.install();spec=self.manifest['series']['02.03.00'];old=pe('reviewed queue bridge')
        spec['compatible_bridge_hashes']=[hashlib.sha256(old).hexdigest()];self.save_manifest()
        (self.target/spec['bridge']).write_bytes(old);m=self.make();m.probe=lambda:[dict(series='02.03.00',queue_api=True)]
        self.assertTrue(m.status()['ready'])

    def test_busy_install_and_restore_do_not_touch_files(self):
        busy=self.make(busy=lambda:True)
        with self.assertRaisesRegex(ValueError,'运行中'):busy.install()
        self.assertFalse(any(self.target.iterdir()))
        self.manager.install();before={p.name:p.read_bytes() for p in self.target.iterdir()}
        with self.assertRaisesRegex(ValueError,'待核对'):busy.restore()
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.target.iterdir()})

    def test_corrupt_bundle_fails_before_writing_target(self):
        (self.bundle/'live555.dll').write_bytes(b'tamper')
        with self.assertRaisesRegex(ValueError,'校验失败'):self.manager.install()
        self.assertFalse(any(self.target.iterdir()))

    def test_wrong_pe_architecture_is_rejected(self):
        data=bytearray(pe('arm'));struct.pack_into('<H',data,68,0xaa64)
        (self.bundle/'live555.dll').write_bytes(data);self.files['live555.dll']['sha256']=hashlib.sha256(data).hexdigest();self.save_manifest()
        with self.assertRaisesRegex(ValueError,'架构'):self.make().install()

    def test_failure_after_write_rolls_back_all_changed_files(self):
        original=pe('old');name='bambu_networking_02.03.00.dll';(self.target/name).write_bytes(original)
        real=self.manager.place;calls=[]
        def fail(source,target,expected):
            real(source,target,expected);calls.append(target.name)
            if len(calls)==3:raise OSError('injected post-copy failure')
        with patch.object(self.manager,'place',side_effect=fail):
            with self.assertRaisesRegex(OSError,'post-copy'):self.manager.install()
        self.assertEqual({p.name:p.read_bytes() for p in self.target.iterdir()},{name:original})

    def test_restore_refuses_overwriting_later_external_update(self):
        self.manager.install();name='bambu_networking_02.03.00.dll';(self.target/name).write_bytes(pe('later update'))
        before={p.name:p.read_bytes() for p in self.target.iterdir()}
        with self.assertRaisesRegex(ValueError,'其他安装器'):self.manager.restore()
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.target.iterdir()})

    def test_concurrent_installer_change_aborts_and_rolls_back_own_changes(self):
        real=self.manager.place;changed='bambu_networking_02.08.04.dll'
        def race(source,target,expected):
            real(source,target,expected)
            if target.name.startswith('backend_'):(self.target/changed).write_bytes(pe('external'))
        with patch.object(self.manager,'place',side_effect=race):
            with self.assertRaisesRegex(ValueError,'其他安装器'):self.manager.install()
        self.assertEqual(list(self.target.iterdir()),[self.target/changed])

    def test_real_live555_is_preserved(self):
        (self.target/'live555.dll').write_bytes(pe('existing real camera library'))
        self.manager.install();self.assertEqual((self.target/'live555.dll').read_bytes(),pe('existing real camera library'))

    def test_path_traversal_manifest_is_rejected(self):
        self.files['../bad.dll']=dict(sha256='0'*64);self.save_manifest()
        with self.assertRaises(ValueError):self.make()

    def test_corrupt_backup_prevents_partial_restore(self):
        name='bambu_networking_02.08.01.dll';(self.target/name).write_bytes(pe('old'));self.manager.install()
        backup=json.loads((self.store/'latest-install.json').read_text())['backup']
        (self.store/'backups'/backup/name).write_bytes(b'tamper')
        before={p.name:p.read_bytes() for p in self.target.iterdir()}
        with self.assertRaisesRegex(ValueError,'备份'):self.manager.restore()
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.target.iterdir()})

    def test_restore_write_failure_returns_to_complete_installed_set(self):
        for version,spec in self.manifest['series'].items():(self.target/spec['bridge']).write_bytes(pe('original '+version))
        self.manager.install();before={p.name:p.read_bytes() for p in self.target.iterdir()}
        real=self.manager.restore_row;calls=[]
        def fail(backup,row):
            real(backup,row);calls.append(row['name'])
            if len(calls)==3:raise OSError('injected restore failure')
        with patch.object(self.manager,'restore_row',side_effect=fail):
            with self.assertRaisesRegex(OSError,'restore failure'):self.manager.restore()
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.target.iterdir()})
        self.assertTrue(self.manager.status()['restore_available'])

    def test_changed_components_require_real_restart_even_if_old_bridge_is_loaded(self):
        self.manager.install();self.manager.probe=lambda:[dict(series='02.03.00',queue_api=True)]
        self.assertFalse(self.manager.status()['ready']);self.assertTrue(self.manager.status()['restart_required'])


if __name__=='__main__':unittest.main()
