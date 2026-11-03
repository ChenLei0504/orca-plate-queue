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

if __name__ == '__main__': unittest.main()
