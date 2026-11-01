"""Bounded native picking-map tests; no live printer, external files or image libraries."""
import base64
from pathlib import Path
import struct
import unittest
import zipfile
import zlib
from object_preview import inspect_object_preview
from test_queue import temporary_directory


def png(width, height, pixels, mode=0):
    def chunk(tag, data):
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)
    raw, previous = bytearray(), bytes(width * 4)
    for y in range(height):
        row = bytes(c for pixel in pixels[y] for c in pixel)
        filtered = bytearray(row)
        for i in range(len(row)):
            left, above, corner = (row[i-4] if i >= 4 else 0), previous[i], (previous[i-4] if i >= 4 else 0)
            guess = left + above - corner
            a, b, c = abs(guess-left), abs(guess-above), abs(guess-corner)
            predictor = [0, left, above, (left+above)//2, left if a <= b and a <= c else above if b <= c else corner][mode]
            filtered[i] = (row[i] - predictor) & 255
        raw.extend(bytes([mode]) + filtered)
        previous = row
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')


class ObjectPreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = temporary_directory()
        self.root = Path(self.temp.__enter__())
        self.objects = [dict(id='300', name='same'), dict(id='414', name='same')]
        self.pixels = [[(0, 0, 0, 0) for x in range(8)] for y in range(8)]
        for x, y, identify in [(1,1,300),(2,1,300),(1,2,300),(2,2,300),(5,5,414),(5,6,414)]:
            self.pixels[y][x] = (identify & 255, identify >> 8 & 255, identify >> 16 & 255, 255)

    def tearDown(self):
        self.temp.__exit__(None,None,None)

    def make(self, **changes):
        parts = {'Metadata/slice_info.config': '<config><plate><metadata key="index" value="5"/><object identify_id="300"/><object identify_id="414"/></plate></config>',
                 'Metadata/top_5.png': png(8,8,self.pixels), 'Metadata/pick_5.png': png(8,8,self.pixels),
                 'Metadata/plate_5.json': '{"bbox_objects":[{"id":999,"name":"same"}]}'}
        parts.update(changes)
        path = self.root/'fixture.3mf'
        with zipfile.ZipFile(path,'w') as z:
            for name, data in parts.items():
                if data is not None: z.writestr(name,data)
        return path

    def test_exact_identify_ids_and_masks_ignore_bbox_ids_and_duplicate_names(self):
        result = inspect_object_preview(self.make(), '5', self.objects)
        self.assertTrue(result['available'],result)
        self.assertEqual([r['id'] for r in result['regions']],['300','414'])
        self.assertEqual(result['regions'][0]['box'],[1,1,3,3])
        self.assertEqual(result['regions'][0]['center'],[2,2])
        self.assertEqual(result['regions'][1]['box'],[5,5,6,7])
        self.assertEqual(result['regions'][0]['path'],'M1 1h2v1h-2zM1 2h2v1h-2z')

    def test_all_standard_png_filters_preserve_native_ids(self):
        for mode in range(5):
            result = inspect_object_preview(self.make(**{'Metadata/pick_5.png':png(8,8,self.pixels,mode)}),'5',self.objects)
            self.assertTrue(result['available'],(mode,result))
            self.assertEqual(result['regions'][0]['box'],[1,1,3,3])

    def test_never_uses_another_plates_pick_image(self):
        result = inspect_object_preview(self.make(**{'Metadata/pick_5.png':None,'Metadata/pick_1.png':png(8,8,self.pixels)}),'5',self.objects)
        self.assertFalse(result['available'])
        self.assertTrue(result['top'])
        self.assertEqual(result['regions'],[])

    def test_unknown_native_id_disables_picture_selection(self):
        self.pixels[0][0]=(231,3,0,255)
        result=inspect_object_preview(self.make(),'5',self.objects)
        self.assertFalse(result['available'])
        self.assertEqual(result['regions'],[])

    def test_missing_object_pixels_never_infer_position_from_order(self):
        self.pixels[5][5]=self.pixels[6][5]=(0,0,0,0)
        self.assertFalse(inspect_object_preview(self.make(),'5',self.objects)['available'])

    def test_slice_registration_mismatch_is_read_only_fallback(self):
        result=inspect_object_preview(self.make(),'5',[dict(id='300'),dict(id='319')])
        self.assertFalse(result['available'])
        self.assertIn('登记',result['note'])

    def test_image_dimensions_must_match(self):
        small=png(1,1,[[(44,1,0,255)]])
        result=inspect_object_preview(self.make(**{'Metadata/pick_5.png':small}),'5',self.objects)
        self.assertFalse(result['available'])
        self.assertIn('尺寸',result['note'])

    def test_corrupted_crc_is_rejected(self):
        raw=bytearray(png(8,8,self.pixels));raw[-1]^=1
        self.assertFalse(inspect_object_preview(self.make(**{'Metadata/pick_5.png':raw}),'5',self.objects)['available'])

    def test_bounded_decompression_rejects_wrong_decoded_size(self):
        raw=png(8,8,self.pixels);header=bytearray(raw);header[16:20]=struct.pack('>I',1);header[29:33]=struct.pack('>I',zlib.crc32(header[12:29])&0xffffffff)
        result=inspect_object_preview(self.make(**{'Metadata/top_5.png':header,'Metadata/pick_5.png':header}),'5',self.objects)
        self.assertFalse(result['available'])

    def test_no_archive_paths_or_markup_accepted_as_plate(self):
        path=self.make()
        for plate in ['../5','5.png','<script>']:
            self.assertFalse(inspect_object_preview(path,plate,self.objects)['available'])
