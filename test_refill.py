"""Cross-plate refill uses reported slots and a fake transport, never hardware."""
import copy
import unittest
from queue_domain import (blank_print_settings, configure_print_settings,
                          validate_print_settings, setup_report)


class RefillTests(unittest.TestCase):
    def setUp(self):
        self.asset = dict(printer='N2S', nozzle='.4', filaments=[dict(id='9', type='PETG', nozzle='.4')])
        self.slots = [dict(id=f'ams/0/tray/{i}', label=f'AMS 1 / {i+1}', kind='ams',
                           present=True, type='PETG', color='#EBE6E6FF') for i in range(4)]
        self.connection = dict(available=True, can_submit=True, devices=[dict(id='a1', online=True,
            age_ms=0, cloud_connected=True, model='N2S', nozzle=.4, slots=self.slots,
            supported_options=['bed_leveling', 'flow_calibration', 'timelapse'])])
        self.draft = blank_print_settings('a1')
        self.draft.update(mapping={'9': self.slots[0]['id']}, refill={'9': dict(slots=[self.slots[1]['id']])})

    def configure(self, previous=None):
        return configure_print_settings(self.asset, self.draft, self.connection, 'a1', previous)

    def ready(self, saved):
        return validate_print_settings(self.asset, saved, self.connection, 'a1', require_send=True)

    def test_server_captures_reported_identity_not_browser_claim(self):
        self.draft['refill']['9'].update(type='PLA', color='000000FF')
        saved = self.configure()
        self.assertEqual(saved['refill']['9']['type'], 'PETG')
        self.assertEqual(saved['refill']['9']['color'], 'EBE6E6FF')

    def test_empty_primary_selects_backup_and_preserves_saved_preference(self):
        saved = self.configure()
        self.slots[0].update(present=False, type='', color='')
        self.assertEqual(self.ready(saved)['mapping']['9'], self.slots[1]['id'])
        self.assertEqual(saved['mapping']['9'], self.slots[0]['id'])
        report = setup_report(self.asset, saved, self.connection, 'a1')
        self.assertTrue(report['ready'])
        self.assertEqual(report['resolved_mapping']['9'], self.slots[1]['id'])

    def test_primary_preferred_then_backups_in_explicit_order(self):
        self.draft['refill']['9']['slots'] = [self.slots[2]['id'], self.slots[1]['id']]
        saved = self.configure()
        self.assertEqual(self.ready(saved)['mapping']['9'], self.slots[0]['id'])
        self.slots[0]['present'] = False
        self.assertEqual(self.ready(saved)['mapping']['9'], self.slots[2]['id'])
        self.slots[2]['present'] = False
        self.assertEqual(self.ready(saved)['mapping']['9'], self.slots[1]['id'])

    def test_rgba_normalization(self):
        self.slots[0]['color'] = '#ebe6e6'
        self.assertEqual(self.configure()['refill']['9']['color'], 'EBE6E6FF')

    def test_unknown_color_placeholder_never_qualifies_as_a_matching_spool(self):
        saved = self.configure()
        self.slots[1]['color'] = '#00000000'
        with self.assertRaises(ValueError): self.configure()
        self.slots[0]['present'] = False
        with self.assertRaises(ValueError): self.ready(saved)

    def test_no_unselected_slot_or_unknown_presence_is_used(self):
        saved = self.configure()
        self.slots[0]['present'] = False
        for state in (False, None):
            self.slots[1]['present'] = state
            with self.assertRaisesRegex(ValueError, '均无可用'): self.ready(saved)

    def test_changed_backup_material_or_color_never_used(self):
        saved = self.configure()
        self.slots[0]['present'] = False
        for change in (dict(type='PLA'), dict(type='PETG', color='#FFFFFF'), dict(color='')):
            self.slots[1].update(change)
            with self.assertRaisesRegex(ValueError, '均无可用'): self.ready(saved)

    def test_new_group_rejects_missing_identity_and_different_backup(self):
        for change in (dict(type='PLA'), dict(type='PETG', color='#FFFFFF'), dict(color='')):
            self.slots[1].update(change)
            with self.assertRaises(ValueError): self.configure()

    def test_changed_primary_color_is_not_silently_used(self):
        saved = self.configure()
        self.slots[0]['color'] = '#000000'
        self.assertEqual(self.ready(saved)['mapping']['9'], self.slots[1]['id'])

    def test_saved_group_can_be_edited_after_primary_loses_metadata(self):
        saved = self.configure()
        self.slots[0].update(present=False, type='', color='')
        self.draft = copy.deepcopy(saved)
        self.draft['refill']['9']['color'] = '000000FF'
        again = self.configure(saved)
        self.assertEqual(again['refill']['9']['color'], 'EBE6E6FF')
        self.assertEqual(self.ready(again)['mapping']['9'], self.slots[1]['id'])

    def test_all_empty_draft_stays_configured_but_cannot_send(self):
        saved = self.configure()
        for slot in self.slots: slot.update(present=False, type='', color='')
        self.draft = copy.deepcopy(saved)
        self.configure(saved)
        report = setup_report(self.asset, saved, self.connection, 'a1')
        self.assertTrue(report['configured'])
        self.assertFalse(report['ready'])
        with self.assertRaises(ValueError): self.ready(saved)

    def test_saved_empty_backup_with_partial_metadata_can_be_retained(self):
        saved = self.configure()
        self.draft = copy.deepcopy(saved)
        self.slots[1].update(present=False, color='')
        self.assertEqual(self.configure(saved)['refill'],saved['refill'])
        self.slots[1]['type']='PLA'
        with self.assertRaises(ValueError):self.configure(saved)

    def test_multicolor_groups_cannot_share_primary_or_backup(self):
        self.asset['filaments'].append(dict(id='10', type='PETG', nozzle='.4'))
        self.draft['mapping']['10'] = self.slots[2]['id']
        for backups in ([self.slots[0]['id']], [self.slots[1]['id']], [self.slots[2]['id']]):
            self.draft['refill']['10'] = dict(slots=backups)
            with self.assertRaisesRegex(ValueError, '不能重复'): self.configure()

    def test_each_color_resolves_independently(self):
        self.asset['filaments'].append(dict(id='10', type='PETG', nozzle='.4'))
        self.slots[2]['color'] = self.slots[3]['color'] = '#000000'
        self.draft['mapping']['10'] = self.slots[2]['id']
        self.draft['refill']['10'] = dict(slots=[self.slots[3]['id']])
        saved = self.configure()
        self.slots[0]['present'] = self.slots[2]['present'] = False
        self.assertEqual(self.ready(saved)['mapping'], {'9': self.slots[1]['id'], '10': self.slots[3]['id']})

    def test_no_opt_in_keeps_existing_empty_slot_block(self):
        self.draft.pop('refill')
        saved = self.configure()
        self.slots[0]['present'] = False
        with self.assertRaisesRegex(ValueError, '无料'): self.ready(saved)

    def test_external_groups_rejected(self):
        self.slots[0].update(id='external', kind='external')
        self.draft.update(source='external', mapping={'9': 'external'})
        with self.assertRaisesRegex(ValueError, '外挂'): self.configure()

    def test_offline_or_stale_never_resolves(self):
        saved = self.configure()
        self.connection['devices'][0]['age_ms'] = 15001
        with self.assertRaises(ValueError): self.ready(saved)

    def test_bad_group_shapes_rejected(self):
        for group in (None, [], {}, dict(slots=[]), dict(slots=['x','x']), dict(slots=[{}])):
            self.draft['refill']['9'] = group
            with self.assertRaises(ValueError): self.configure()


if __name__ == '__main__':
    unittest.main()
