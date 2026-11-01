"""A1 swap-file metadata and preflight. Never executes printer movements."""
from printer_models import canonical_model
from pathlib import Path
import hashlib
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from queue_core import plate_materials, plate_thumbnail
DEFAULT_SWAP_FILE = ''
MOTION_ONLY_SWAP_SHA256 = '4e2e3a0431b8d8bc2e333e65808cfcd71fbdfaec399b2c05087244cdd09e9443'


def inspect_swap_file(path, nozzle=0.4):
    if not isinstance(path, str) or not path.strip():
        raise ValueError('请选择套件提供的 A1 独立换盘 3MF 文件。')
    p = Path(path.strip().strip('"')).resolve()
    if p.suffix.lower() != '.3mf' or not p.is_file():
        raise ValueError('换盘文件不存在，或文件不是 .3mf。')
    if type(nozzle) not in (int, float) or nozzle not in (0.2, 0.4, 0.6, 0.8):
        raise ValueError('请选择当前打印机的喷嘴规格：0.2、0.4、0.6 或 0.8。')
    with zipfile.ZipFile(p) as z:
        gcodes = [n for n in z.namelist() if re.fullmatch(r'Metadata/plate_\d+\.gcode', n)]
        if len(gcodes) != 1 or z.getinfo(gcodes[0]).file_size > 300_000_000:
            raise ValueError('请选择只包含一个正式盘任务的独立换盘文件。')
        gcode = z.read(gcodes[0]).decode('utf-8-sig')
        starts = list(re.finditer(r'^\s*;start change plate\b', gcode, re.M | re.I))
        ends = list(re.finditer(r'^\s*;end change plate\b', gcode, re.M | re.I))
        if len(starts) != 1 or len(ends) != 1 or starts[0].start() >= ends[0].start():
            raise ValueError('未找到完整的一组套件换盘标记；不将普通模型或合盘文件作为换盘任务。')
        settings_info = z.getinfo('Metadata/project_settings.config')
        if settings_info.file_size > 2_000_000:
            raise ValueError('换盘文件设置过大。')
        settings = json.loads(z.read(settings_info).decode('utf-8-sig'))
        model = canonical_model(settings.get('printer_model'))
        if not model:
            raise ValueError('换盘文件的机型尚未支持。')
        diameters = settings.get('nozzle_diameter')
        try:
            if not isinstance(diameters, list) or len(diameters) != 1 or abs(float(diameters[0]) - nozzle) > .0001:
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError('换盘文件喷嘴规格与所选喷嘴不一致，请改用对应版本的文件。')
        plate_index = re.search(r'plate_(\d+)\.gcode', gcodes[0])[1]
        filaments = []
        if 'Metadata/slice_info.config' in z.namelist():
            if z.getinfo('Metadata/slice_info.config').file_size > 2_000_000:
                raise ValueError('换盘文件切片登记过大。')
            raw = z.read('Metadata/slice_info.config')
            if b'<!DOCTYPE' in raw.upper():
                raise ValueError('换盘文件切片登记格式不受支持。')
            root = ET.fromstring(raw)
            plate = next((plate for plate in root.findall('plate') if any(
                m.get('key') == 'index' and m.get('value') == plate_index for m in plate.findall('metadata'))), None)
            if plate is not None:
                filaments = plate_materials(plate)
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        return dict(path=str(p), name=p.name, sha256=digest,
                    printer=settings['printer_model'], nozzle=nozzle, plate=plate_index,
                    filaments=filaments, filament_count=len(settings.get('filament_type', [])),
                    motion_only=digest == MOTION_ONLY_SWAP_SHA256,
                    bed_type=settings.get('curr_bed_type', 'auto'),
                    gcode=gcodes[0], thumbnail=plate_thumbnail(z, plate_index), validated=True)


def swap_plan(jobs, settings):
    """Describe transitions between models. This is a plan, not a dispatcher."""
    if not settings.get('enabled', True):
        return []
    waiting = [j for j in jobs if j['status'] in ('等待','发送中','打印中')]
    return [dict(after_id=a['id'], before_id=b['id'], file=settings.get('path', DEFAULT_SWAP_FILE),
                 status='等待', nozzle=settings.get('nozzle', .4)) for a, b in zip(waiting, waiting[1:])]
