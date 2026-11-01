"""Read exact native object masks from a frozen single-plate 3MF. No printer I/O."""
import base64
import struct
import zipfile
import zlib
import xml.etree.ElementTree as ET


def preview_png(archive, name):
    info = archive.getinfo(name)
    if not 33 <= info.file_size <= 512_000:
        raise ValueError('预览图片大小超出限制。')
    raw = archive.read(name)
    if raw[:8] != b'\x89PNG\r\n\x1a\n' or raw[12:16] != b'IHDR':
        raise ValueError('预览不是有效 PNG。')
    w, h, depth, kind, compression, filtering, interlace = struct.unpack('>IIBBBBB', raw[16:29])
    if not (0 < w <= 1024 and 0 < h <= 1024) or (depth, kind, compression, filtering, interlace) not in ((8, 6, 0, 0, 0), (8, 2, 0, 0, 0)):
        raise ValueError('预览图片格式不受支持。')
    return raw, w, h, 4 if kind == 6 else 3


def decode_preview_png(raw, width, height, channels):
    offset, packed, ended = 8, bytearray(), False
    while offset + 12 <= len(raw):
        size = struct.unpack('>I', raw[offset:offset + 4])[0]
        if offset + size + 12 > len(raw):
            raise ValueError('拾取图片数据不完整。')
        tag, data = raw[offset + 4:offset + 8], raw[offset + 8:offset + 8 + size]
        crc = struct.unpack('>I', raw[offset + 8 + size:offset + 12 + size])[0]
        if zlib.crc32(tag + data) & 0xffffffff != crc:
            raise ValueError('拾取图片校验失败。')
        if tag == b'IDAT':
            packed.extend(data)
        if tag == b'IEND':
            ended = True
            break
        offset += size + 12
    if not ended:
        raise ValueError('拾取图片缺少结束标记。')
    stride = width * channels
    expected = height * (stride + 1)
    decoder = zlib.decompressobj()
    decoded = decoder.decompress(bytes(packed), expected + 1)
    if len(decoded) != expected or not decoder.eof or decoder.unconsumed_tail or decoder.unused_data:
        raise ValueError('拾取图片解压长度无效。')
    previous = bytearray(stride)
    for y in range(height):
        start = y * (stride + 1)
        mode, row = decoded[start], bytearray(decoded[start + 1:start + 1 + stride])
        if mode > 4:
            raise ValueError('拾取图片滤波格式无效。')
        if mode:
            for i in range(stride):
                left = row[i - channels] if i >= channels else 0
                above = previous[i]
                corner = previous[i - channels] if i >= channels else 0
                if mode == 1:
                    predictor = left
                elif mode == 2:
                    predictor = above
                elif mode == 3:
                    predictor = (left + above) // 2
                else:
                    guess = left + above - corner
                    a, b, c = abs(guess - left), abs(guess - above), abs(guess - corner)
                    predictor = left if a <= b and a <= c else above if b <= c else corner
                row[i] = (row[i] + predictor) & 255
        yield y, row
        previous = row


def inspect_object_preview(path, plate, objects):
    """RGB encodes identify_id little-endian, matching Orca's native picking pass.

    Never use bbox JSON IDs, names, array order or nearest objects to guess IDs.
    Missing/unsupported/mismatching masks fall back to the verified text list.
    """
    result = dict(available=False, top='', width=512, height=512, regions=[], note='此文件没有可核对的零件拾取图，请使用下方列表。')
    try:
        if not str(plate).isdecimal() or not 1 <= len(objects) <= 256:
            raise ValueError('盘号或零件数量不受支持。')
        ids = {int(o['id']) for o in objects}
        if len(ids) != len(objects) or any(not 0 < i < 0x1000000 for i in ids):
            raise ValueError('零件编号不能与拾取图建立唯一对应。')
        with zipfile.ZipFile(path) as archive:
            if archive.getinfo('Metadata/slice_info.config').file_size > 2_000_000:
                raise ValueError('切片登记过大。')
            config = archive.read('Metadata/slice_info.config')
            if b'<!DOCTYPE' in config.upper():
                raise ValueError('切片登记格式无效。')
            root = ET.fromstring(config)
            record = next((p for p in root.findall('plate') if any(m.get('key') == 'index' and m.get('value') == str(plate) for m in p.findall('metadata'))), None)
            registered = [int(o.get('identify_id', '')) for o in record.findall('object')] if record is not None else []
            if len(registered) != len(objects) or set(registered) != ids:
                raise ValueError('本盘零件编号与切片登记不一致。')
            top, width, height, _ = preview_png(archive, f'Metadata/top_{plate}.png')
            result.update(top='data:image/png;base64,' + base64.b64encode(top).decode('ascii'), width=width, height=height)
            pick, pw, ph, channels = preview_png(archive, f'Metadata/pick_{plate}.png')
            if (pw, ph) != (width, height):
                raise ValueError('俯视图和拾取图尺寸不一致。')
        masks = {i: [] for i in ids}
        stats = {i: [width, height, -1, -1, 0, 0, 0] for i in ids}
        unknown, rectangle_count = False, 0
        for y, row in decode_preview_png(pick, width, height, channels):
            x = 0
            while x < width:
                offset = x * channels
                identify = row[offset] | row[offset + 1] << 8 | row[offset + 2] << 16
                opaque = channels == 3 or row[offset + 3] == 255
                if not opaque or identify == 0:
                    x += 1
                    continue
                if identify not in ids:
                    unknown = True
                    x += 1
                    continue
                start = x
                while x < width:
                    k = x * channels
                    if (row[k] | row[k + 1] << 8 | row[k + 2] << 16) != identify or channels == 4 and row[k + 3] != 255:
                        break
                    x += 1
                run = x - start
                masks[identify].append(f'M{start} {y}h{run}v1h-{run}z')
                rectangle_count += 1
                if rectangle_count > 20_000:
                    raise ValueError('拾取轮廓过于复杂，请使用列表。')
                a = stats[identify]
                a[0], a[1], a[2], a[3] = min(a[0], start), min(a[1], y), max(a[2], x), max(a[3], y + 1)
                a[4] += (start + x) * run / 2
                a[5] += (y + .5) * run
                a[6] += run
        if unknown or any(not a[6] for a in stats.values()):
            raise ValueError('拾取图不能完整对应本盘零件，已禁用图片选择，请使用列表。')
        result.update(available=True, note='点击模型或编号选择，下方勾选会同步高亮。', regions=[dict(id=str(o['id']), path=''.join(masks[int(o['id'])]), box=stats[int(o['id'])][:4], center=[round(stats[int(o['id'])][4] / stats[int(o['id'])][6], 2), round(stats[int(o['id'])][5] / stats[int(o['id'])][6], 2)]) for o in objects])
    except (KeyError, ValueError, TypeError, OSError, zipfile.BadZipFile, RuntimeError, ET.ParseError, zlib.error, struct.error) as exc:
        result['note'] = str(exc) if isinstance(exc, ValueError) else '无法读取本盘拾取图，请使用下方列表。'
    return result
