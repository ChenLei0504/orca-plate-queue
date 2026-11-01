import tempfile
import unittest
import zipfile
import base64
import xml.etree.ElementTree as ET
from pathlib import Path
from queue_core import Queue, inspect_plate, plate_thumbnail, plate_materials

TEST_ROOT = Path(__file__).resolve().parent / '.test-temp'
TEST_ROOT.mkdir(exist_ok=True)

def temporary_directory():
    return tempfile.TemporaryDirectory(dir=TEST_ROOT)


def queue(n=3):
    q = Queue()
    for i in range(n):
        q.add(dict(name=str(i), objects=[{}, {}]))
    q.start()
    return q


class Transitions(unittest.TestCase):
    def test_source_nozzle_mapping_uses_plate_metadata_and_cloud_enum(self):
        plate=ET.fromstring('<plate><metadata key="filament_maps" value="1 1 1 1 1 1 1 1 2"/><filament id="9" type="PETG"/></plate>')
        self.assertEqual(plate_materials(plate)[0]['nozzle_id'],0)
        plate.find('metadata').set('value','1 1 1 1 1 1 1 1 1')
        self.assertEqual(plate_materials(plate)[0]['nozzle_id'],1)

    def test_finish_swap_next(self):
        q = queue()
        first = q.current
        print_id = q.attempt
        q.event('finished', print_id)
        self.assertEqual(q.state, '等待换盘准备确认')
        q.ready_to_swap()
        swap_id = q.attempt
        q.event('finished', print_id)
        self.assertEqual(q.state, '换盘中')
        q.swap_finished(swap_id)
        self.assertEqual(q.current, first)
        q.confirm_new_plate()
        self.assertNotEqual(q.current, first)
        self.assertEqual(q.state, '打印中')

    def test_stop_continue_requires_ack(self):
        q = queue()
        q.request_stop(True)
        self.assertEqual(q.state, '等待停止确认')
        with self.assertRaises(ValueError): q.ready_to_swap()
        q.event('stopped', q.attempt)
        self.assertEqual(q.state, '等待换盘准备确认')

    def test_stop_pause(self):
        q = queue()
        q.request_stop(False)
        q.event('stopped', q.attempt)
        self.assertEqual(q.state, '已暂停')
        self.assertTrue(q.dirty_plate)

    def test_external_stop_defaults_pause(self):
        q = queue()
        q.event('stopped', q.attempt)
        self.assertEqual(q.state, '已暂停')

    def test_skip_one_keeps_printing(self):
        q = queue()
        q.skip()
        self.assertEqual(q.state, '打印中')
        self.assertEqual(q.selected().skipped, 1)

    def test_last_object_ends_plate(self):
        q = queue()
        q.skip()
        q.skip()
        self.assertEqual(q.state, '等待停止确认')
        self.assertEqual(q.stop_intent, 'continue')

    def test_single_object(self):
        q = Queue()
        q.add(dict(name='one', objects=[{}]))
        q.start()
        q.skip()
        q.event('stopped', q.attempt)
        self.assertEqual(q.state, '队列完成')

    def test_final_plate_not_swapped(self):
        q = queue(1)
        q.event('finished', q.attempt)
        self.assertEqual(q.state, '队列完成')
        q.start()
        self.assertEqual(q.state, '队列完成')

    def test_duplicate_finish_cannot_dispatch(self):
        q = queue()
        token = q.attempt
        q.event('finished', token)
        q.event('finished', token)
        self.assertEqual(q.state, '等待换盘准备确认')
        self.assertEqual(sum(j.status == '完成' for j in q.jobs), 1)

    def test_unrelated_task_ignored(self):
        q = queue()
        q.event('finished', 'another-task')
        self.assertEqual(q.state, '打印中')

    def test_disconnect_clears_continue_intent(self):
        q = queue()
        q.request_stop(True)
        q.event('disconnected', q.attempt)
        q.event('stopped', q.attempt)
        self.assertEqual(q.state, '已暂停')
        with self.assertRaises(ValueError): q.start()

    def test_finish_stop_race_pause_wins(self):
        q = queue()
        q.request_stop(False)
        q.event('finished', q.attempt)
        self.assertEqual(q.state, '已暂停')

    def test_resume_after_external_stop_requires_swap(self):
        q = queue()
        q.event('stopped', q.attempt)
        q.start()
        self.assertEqual(q.state, '等待换盘准备确认')

    def test_restart_does_not_resend(self):
        with temporary_directory() as d:
            q = queue()
            q.request_stop(True)
            path = Path(d) / 'queue.json'
            q.save(path)
            restored = Queue.load(path)
            self.assertEqual(restored.state, '已暂停')
            self.assertIsNone(restored.stop_intent)
            with self.assertRaises(ValueError): restored.start()
            restored.event('stopped', q.attempt)
            self.assertEqual(restored.selected().status, '待核对')
            restored.reconcile_stopped()
            restored.start()
            self.assertEqual(restored.state, '等待换盘准备确认')

    def test_cancel_during_swap_pauses(self):
        q = queue()
        q.event('finished', q.attempt)
        q.ready_to_swap()
        token = q.attempt
        q.event('stopped', token)
        q.swap_finished(token)
        self.assertEqual(q.state, '已暂停')

    def test_later_added_job_requires_clean_bed(self):
        q = queue(1)
        q.event('finished', q.attempt)
        q.add(dict(name='new', objects=[{}]))
        q.start()
        self.assertEqual(q.state, '等待换盘准备确认')


class FileInspection(unittest.TestCase):
    def make(self, folder, count=1, swap=False, mismatch=False):
        path = Path(folder) / 'plate.3mf'
        with zipfile.ZipFile(path, 'w') as z:
            for i in range(count):
                z.writestr(f'Metadata/plate_{i+1}.gcode', ';start change plate' if swap else 'M624 AA==\nM625\n')
            z.writestr('Metadata/slice_info.config', '<config><plate><metadata key="index" value="'+('9' if mismatch else '1')+'"/><metadata key="label_object_enabled" value="true"/><object identify_id="1" name="sample"/></plate></config>')
        return path

    def test_single_plate(self):
        with temporary_directory() as d:
            info = inspect_plate(self.make(d))
            self.assertTrue(info['label_markers'])
            self.assertEqual(len(info['sha256']), 64)

    def test_multiplate_rejected(self):
        with temporary_directory() as d:
            with self.assertRaises(ValueError): inspect_plate(self.make(d, count=2))

    def test_merged_swap_rejected(self):
        with temporary_directory() as d:
            with self.assertRaises(ValueError): inspect_plate(self.make(d, swap=True))

    def test_index_mismatch(self):
        with temporary_directory() as d:
            with self.assertRaises(ValueError): inspect_plate(self.make(d, mismatch=True))

    def test_exact_plate_thumbnail_and_metadata(self):
        with temporary_directory() as d:
            p = self.make(d)
            png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a7xkAAAAASUVORK5CYII=')
            with zipfile.ZipFile(p, 'a') as z:
                z.writestr('Metadata/plate_1.png', png)
                z.writestr('Metadata/plate_2.png', b'not the selected plate')
            info = inspect_plate(p)
            self.assertEqual(base64.b64decode(info['thumbnail'].split(',')[1]), png)
            self.assertIsNone(info['duration_s'])

    def test_missing_thumbnail_does_not_use_other_plate(self):
        with temporary_directory() as d:
            p = self.make(d)
            png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a7xkAAAAASUVORK5CYII=')
            with zipfile.ZipFile(p, 'a') as z: z.writestr('Metadata/plate_2.png', png)
            self.assertEqual(inspect_plate(p)['thumbnail'], '')

    def test_bad_thumbnail_falls_back_to_small(self):
        with temporary_directory() as d:
            p = self.make(d)
            png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a7xkAAAAASUVORK5CYII=')
            with zipfile.ZipFile(p, 'a') as z:
                z.writestr('Metadata/plate_1.png', b'x' * 512001)
                z.writestr('Metadata/plate_1_small.png', png)
            self.assertEqual(base64.b64decode(inspect_plate(p)['thumbnail'].split(',')[1]), png)


if __name__ == '__main__': unittest.main(verbosity=2)
