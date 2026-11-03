"""Provider selection and cloud ownership tests; no host/DLL/network required."""
import copy
import types
import unittest
from printer_connection import PrinterConnection

class Provider:
    def __init__(self):
        self.raw = dict(protocol=1, origin='orca-owned-cloud', cloud_session_reused=False,
                        attached=True, can_submit=True, devices=[], commands=[],
                        logged_in=True, cloud_connected=True)
        self.watch_ids = set()
        self.closed = 0
        self.refreshed = 0
        self.sent = []
    def snapshot(self): return copy.deepcopy(self.raw)
    def refresh(self): self.refreshed += 1
    def close(self): self.closed += 1
    def command(self, request): self.sent.append(request); return 0

class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.provider = Provider()
        self.connection = PrinterConnection(None, provider=self.provider, mode='owned_cloud')
    def test_explicit_selection_required(self):
        with self.assertRaises(ValueError): PrinterConnection(None, mode='owned_cloud')
        with self.assertRaises(ValueError): PrinterConnection(None, mode='unknown')
    def test_cannot_combine_connections(self):
        host=types.SimpleNamespace(queue_bridge_v1=object())
        with self.assertRaises(ValueError):
            PrinterConnection(host, provider=self.provider, mode='owned_cloud')
    def test_own_session_does_not_require_host_session(self):
        result=self.connection.snapshot()
        self.assertTrue(result['available'])
        self.assertTrue(result['can_submit'])
        self.assertEqual(result['connection_mode'], 'owned_cloud')
    def test_cannot_impersonate_native_session(self):
        for change in (dict(origin='orca-native-queue'), dict(cloud_session_reused=True), dict(protocol=2), dict(attached=False)):
            provider=Provider(); provider.raw.update(change)
            connection=PrinterConnection(None, provider=provider, mode='owned_cloud')
            self.assertFalse(connection.snapshot()['available'])
    def test_native_cannot_accept_owned_origin(self):
        connection=PrinterConnection(None, provider=self.provider)
        self.assertFalse(connection.snapshot()['available'])
    def test_only_selected_provider_receives_operations(self):
        self.connection.refresh()
        self.connection.watch('printer-a')
        self.connection.command({'action': 'pause'})
        self.assertEqual(self.provider.refreshed, 1)
        self.assertEqual(self.provider.watch_ids, {'printer-a'})
        self.assertEqual(self.provider.sent, [{'action': 'pause'}])
    def test_close_is_idempotent_and_blocks_reuse(self):
        self.connection.close(); self.connection.close()
        self.assertEqual(self.provider.closed, 1)
        self.assertFalse(self.connection.snapshot()['available'])
        with self.assertRaises(RuntimeError): self.connection.command({'action':'submit'})
        with self.assertRaises(RuntimeError): self.connection.refresh()
        with self.assertRaises(RuntimeError): self.connection.watch('printer-a')
        self.assertEqual(self.provider.sent, [])
    def test_host_connection_lifetime_is_not_owned(self):
        connection=PrinterConnection(None, provider=self.provider)
        connection.close()
        self.assertEqual(self.provider.closed, 0)
    def test_experimental_provider_cannot_submit(self):
        self.provider.raw['prototype']=True
        self.assertFalse(self.connection.snapshot()['can_submit'])
        with self.assertRaises(RuntimeError): self.connection.command({'action':'submit'})
        self.assertEqual(self.provider.sent, [])
    def test_raw_credentials_are_not_exposed(self):
        self.provider.raw.update(access_token='PRIVATE', password='PRIVATE', auth={'refresh_token':'PRIVATE'})
        self.assertNotIn('PRIVATE', repr(self.connection.snapshot()))


class HostProviderTests(unittest.TestCase):
    def setUp(self):
        self.provider = Provider()
        self.provider.raw.update(origin='orca-native-queue', cloud_session_reused=True,
                                 material_mapping_ready=True)
        self.host = types.SimpleNamespace(queue_bridge_v1=self.provider)
        self.connection = PrinterConnection(self.host)

    def test_host_refresh_and_lifetime(self):
        self.connection.refresh()
        self.assertEqual(self.provider.refreshed, 1)
        self.connection.close()
        self.assertEqual(self.provider.closed, 0)

    def test_live_queue_does_not_switch_when_host_property_changes(self):
        replacement = Provider()
        self.host.queue_bridge_v1 = replacement
        self.connection.refresh()
        self.connection.command({'action': 'pause'})
        self.assertTrue(self.connection.snapshot()['available'])
        self.assertEqual(self.provider.sent, [{'action': 'pause'}])
        self.assertEqual(replacement.sent, [])
        self.assertEqual(replacement.refreshed, 0)

    def test_explicit_owned_connection_cannot_be_replaced_by_late_host(self):
        host = types.SimpleNamespace()
        owned = Provider()
        connection = PrinterConnection(host, provider=owned, mode='owned_cloud')
        host.queue_bridge_v1 = self.provider
        connection.command({'action': 'pause'})
        self.assertEqual(owned.sent, [{'action': 'pause'}])
        self.assertEqual(self.provider.sent, [])

    def test_multi_printer_subscription_uses_validated_catalog(self):
        from test_setup import native_snapshot
        a1 = native_snapshot()['devices'][0]
        p1 = copy.deepcopy(a1); p1.update(id='test-p1', model='P1S')
        other = copy.deepcopy(a1); other.update(id='unsupported', model='unknown')
        self.provider.raw['devices'] = [a1, p1, other]
        for name in ('test-a1', 'test-p1', 'unknown-id', 'unsupported'):
            self.connection.watch(name)
        self.assertTrue(self.connection.snapshot()['available'])
        self.assertEqual(self.provider.sent[-1], dict(action='watch_many',
            request_id='watch_queue_devices', device_ids=['test-a1', 'test-p1']))
        self.provider.raw['devices'] = [p1]
        self.connection.snapshot()
        self.assertEqual(self.provider.sent[-1]['device_ids'], ['test-p1'])

    def test_host_watch_limit(self):
        for n in range(32): self.connection.watch(str(n))
        self.connection.watch('0')
        with self.assertRaises(ValueError): self.connection.watch('extra')

    def test_invalid_catalog_never_subscribes(self):
        self.connection.watch('test-a1')
        self.provider.raw['devices'] = [{}]
        self.assertFalse(self.connection.snapshot()['available'])
        self.assertEqual(self.provider.sent, [])

    def test_host_refusal_is_not_success(self):
        self.provider.command = lambda request: -6
        with self.assertRaises(RuntimeError): self.connection.command({'action': 'pause'})
        self.connection.watch('test-a1')
        self.assertFalse(self.connection.snapshot()['available'])

    def test_submit_preserves_mapping_and_requires_capability(self):
        request = dict(action='submit', use_ams=True, ams_mapping=[3], device_id='test-a1')
        self.connection.command(request)
        self.assertEqual(self.provider.sent, [request])
        self.provider.raw['material_mapping_ready'] = False
        with self.assertRaises(RuntimeError): self.connection.command(request)
        self.assertEqual(len(self.provider.sent), 1)

    def test_disconnected_and_prototype_host_cannot_control_print(self):
        for change in (dict(attached=False), dict(attached=None), dict(can_submit=False), dict(prototype=True)):
            with self.subTest(change=change):
                saved = copy.deepcopy(self.provider.raw)
                self.provider.raw.update(change)
                with self.assertRaises(RuntimeError): self.connection.command({'action': 'pause'})
                self.assertEqual(self.provider.sent, [])
                self.provider.raw = saved

if __name__ == '__main__': unittest.main()
