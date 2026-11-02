"""Offline queue design. No printer communication or native library loading."""
from local_paths import fs_path, canonical_path, replace_file
from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib
import base64
import struct
import json
import re
import uuid
import zipfile
import xml.etree.ElementTree as ET


def plate_thumbnail(archive, index):
    """Only use this exact plate's bounded PNG preview; never another plate."""
    for name in (f'Metadata/plate_{index}.png', f'Metadata/top_{index}.png',
                 f'Metadata/plate_{index}_small.png'):
        try:
            entry = archive.getinfo(name)
            if not 24 <= entry.file_size <= 512_000:
                continue
            raw = archive.read(name)
            if raw[:8] != b'\x89PNG\r\n\x1a\n' or raw[12:16] != b'IHDR':
                continue
            width, height = struct.unpack('>II', raw[16:24])
            if not (0 < width <= 2048 and 0 < height <= 2048):
                continue
            return 'data:image/png;base64,' + base64.b64encode(raw).decode('ascii')
        except (KeyError, ValueError, zipfile.BadZipFile, RuntimeError, OSError):
            continue
    return ''


def plate_materials(plate):
    """Keep source filament IDs verbatim: they need not be contiguous or start at 1."""
    result = []
    seen = set()
    nozzle_maps = next((m.get('value', '').split() for m in plate.findall('metadata') if m.get('key') == 'filament_maps'), [])
    for f in plate.findall('filament'):
        source_id = f.get('id', '')
        if not source_id.isdecimal() or source_id in seen:
            raise ValueError('切片耗材编号缺失或重复，不能建立耗材映射。')
        seen.add(source_id)
        color = f.get('color', '')
        if color and not re.fullmatch(r'#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?', color):
            raise ValueError('切片耗材颜色格式不受支持。')
        result.append(dict(id=source_id, type=f.get('type', ''), color=color,
                           profile_id=f.get('tray_info_idx', ''),
                           nozzle=f.get('nozzle_diameter', ''),
                           used_g=f.get('used_g', ''), used_m=f.get('used_m', '')))
        index = int(source_id)-1
        if 0 <= index < len(nozzle_maps) and nozzle_maps[index] in ('1', '2'):
            # SelectMachine.hpp: sliced LEFT=1 / RIGHT=2 -> cloud LEFT=1 / RIGHT=0.
            result[-1]['nozzle_id'] = 1 if nozzle_maps[index] == '1' else 0
    return result


def inspect_plate(path):
    path = canonical_path(path)
    with zipfile.ZipFile(fs_path(path)) as z:
        gcodes = [n for n in z.namelist() if re.fullmatch(r'Metadata/plate_\d+\.gcode', n)]
        if len(gcodes) != 1:
            raise ValueError('请导出单盘切片文件；文件必须恰好包含一份正式 plate_N.gcode。')
        if z.getinfo(gcodes[0]).file_size > 300_000_000:
            raise ValueError('切片文件过大，请单独检查。')
        gcode = z.read(gcodes[0]).decode('utf-8-sig')
        if ';start change plate' in gcode.lower():
            raise ValueError('此文件已包含换盘动作，请使用未经合盘的单盘文件，避免重复换盘。')
        if z.getinfo('Metadata/slice_info.config').file_size > 2_000_000:
            raise ValueError('切片信息过大。')
        data = z.read('Metadata/slice_info.config')
        if len(data) > 2_000_000 or b'<!DOCTYPE' in data.upper():
            raise ValueError('不支持此切片信息格式。')
        root = ET.fromstring(data)
        index = re.search(r'plate_(\d+)\.gcode', gcodes[0])[1]
        plate = next((p for p in root.findall('plate') if any(
            m.get('key') == 'index' and m.get('value') == index for m in p.findall('metadata'))), None)
        if plate is None:
            raise ValueError('切片路径与盘号登记不一致。')
        meta = {m.get('key'): m.get('value') for m in plate.findall('metadata')}
        project = {}
        if 'Metadata/project_settings.config' in z.namelist():
            if z.getinfo('Metadata/project_settings.config').file_size > 2_000_000:
                raise ValueError('项目设置过大。')
            project = json.loads(z.read('Metadata/project_settings.config').decode('utf-8-sig'))
        filament_count = len(project.get('filament_type', []))
        if filament_count > 128:
            raise ValueError('耗材数量超出队列支持范围。')
        objects = [{'id': o.get('identify_id'), 'name': o.get('name', '未命名零件')}
                   for o in plate.findall('object')]
        if not objects or any(not o['id'] for o in objects) or len({o['id'] for o in objects}) != len(objects):
            raise ValueError('零件登记为空或编号重复。')
        # This flag is descriptive only, not a claim that Handy skipping will work.
        marked = meta.get('label_object_enabled') == 'true' and bool(re.search(r'^M624\b', gcode, re.M)) and bool(re.search(r'^M625\b', gcode, re.M))
        def number(value):
            try:
                n = float(value)
                return n if 0 <= n < 1e9 else None
            except (ValueError, TypeError):
                return None
        return dict(path=str(path), name=path.name, plate=index, objects=objects,
                    label_markers=marked, printer=meta.get('printer_model_id', ''),
                    thumbnail=plate_thumbnail(z, index),
                    duration_s=number(meta.get('prediction')),
                    weight_g=number(meta.get('weight')),
                    filament_types=sorted({f.get('type') for f in plate.findall('filament') if f.get('type')}),
                    filaments=plate_materials(plate), nozzle=meta.get('nozzle_diameters', ''),
                    filament_count=max(filament_count, max((int(f.get('id','0')) for f in plate.findall('filament')), default=0)),
                    bed_type=project.get('curr_bed_type', 'auto'),
                    sha256=hashlib.sha256(fs_path(path).read_bytes()).hexdigest())


@dataclass
class Job:
    id: str
    name: str
    path: str = ''
    sha256: str = ''
    object_count: int = 1
    status: str = '等待'
    skipped: int = 0
    label_markers: bool = False


class Queue:
    def __init__(self):
        self.jobs = []
        self.state = '待机'
        self.current = None
        self.attempt = ''
        self.stop_intent = None
        self.dirty_plate = False
        self.log = []
        self.transport = 'simulation'

    def note(self, message):
        self.log.append(message)

    def add(self, info, copies=1):
        if not 1 <= copies <= 100:
            raise ValueError('份数范围为 1–100。')
        for _ in range(copies):
            self.jobs.append(Job(uuid.uuid4().hex, info['name'], info.get('path', ''),
                                 info.get('sha256', ''), len(info['objects']),
                                 label_markers=info.get('label_markers', False)))
        self.note(f"加入 {info['name']} × {copies}")

    def selected(self):
        return next((j for j in self.jobs if j.id == self.current), None)

    def next_job(self):
        return next((j for j in self.jobs if j.status == '等待'), None)

    def start(self):
        if self.state not in ('待机', '已暂停', '队列完成'):
            raise ValueError('当前流程尚未结束。')
        if self.selected() and self.selected().status in ('打印中', '停止中', '待核对'):
            raise ValueError('先核对设备任务：原任务已停止，才能继续队列。')
        if not self.next_job():
            self.state = '队列完成'
            return
        if self.dirty_plate:
            self.state = '等待换盘准备确认'
            self.note('当前热床有已打印内容，先核对停止与换盘准备状态。')
            return
        self.dispatch()

    def dispatch(self):
        job = self.next_job()
        if not job:
            self.state = '队列完成'
            self.current = None
            self.note('队列已结束；最后一盘留在热床。')
            return
        self.current = job.id
        self.attempt = uuid.uuid4().hex
        self.stop_intent = None
        job.status = '打印中'
        self.state = '打印中'
        self.dirty_plate = True
        self.note(f'模拟开始：{job.name}（未向打印机发送）')

    def request_stop(self, continue_queue):
        if self.state != '打印中':
            raise ValueError('只有打印中可以结束本盘。')
        # Real adapter must durably commit this intent before sending STOP.
        self.stop_intent = 'continue' if continue_queue else 'pause'
        self.selected().status = '停止中'
        self.state = '等待停止确认'
        self.note('记录停止意图：' + ('换盘后继续' if continue_queue else '暂停队列'))

    def event(self, event, attempt):
        if attempt != self.attempt:
            self.note('忽略其他任务或旧任务的回报。')
            return
        job = self.selected()
        if event in ('disconnected', 'error'):
            self.state = '已暂停'
            if job and job.status in ('打印中', '停止中'):
                job.status = '待核对'
            self.stop_intent = None
            self.note('异常暂停；恢复前需要核对设备与热床，不自动重发。')
        elif event == 'finished' and self.state == '打印中':
            job.status = '完成'
            self.after_plate()
        elif event == 'stopped' and self.state in ('打印中', '等待停止确认'):
            job.status = '已结束'
            if self.stop_intent == 'continue':
                self.after_plate()
            else:
                self.state = '已暂停'
                self.note('打印已停止，队列暂停，不换盘。')
            self.stop_intent = None
        elif event == 'finished' and self.state == '等待停止确认':
            # STOP can race a successful finish. The saved pause intent wins.
            job.status = '完成'
            if self.stop_intent == 'continue':
                self.after_plate()
            else:
                self.state = '已暂停'
                self.note('打印恰好完成，仍遵守暂停队列的操作。')
            self.stop_intent = None
        elif event == 'stopped' and self.state in ('换盘中', '等待新板确认', '等待换盘准备确认'):
            self.pause_transition()
        else:
            self.note('忽略重复或不符合当前阶段的回报。')

    def after_plate(self):
        if self.next_job():
            self.state = '等待换盘准备确认'
            self.note('下一步需确认运动停止、喷头已避让、温度和套件条件满足。')
        else:
            self.state = '队列完成'
            self.note('最后一盘结束，保留热床，不执行空换盘。')

    def ready_to_swap(self):
        if self.state != '等待换盘准备确认':
            raise ValueError('当前不是换盘准备阶段。')
        self.state = '换盘中'
        self.attempt = uuid.uuid4().hex
        self.note('模拟执行独立换盘任务（未向打印机发送）。')

    def swap_finished(self, attempt):
        if attempt == self.attempt and self.state == '换盘中':
            self.state = '等待新板确认'
            self.note('换盘程序结束 ≠ 新板到位。第一版要求确认新板。')

    def confirm_new_plate(self):
        if self.state != '等待新板确认':
            raise ValueError('尚未完成换盘。')
        self.dirty_plate = False
        self.dispatch()

    def skip(self):
        if self.state != '打印中':
            raise ValueError('当前没有正在打印的零件。')
        job = self.selected()
        if job.object_count - job.skipped <= 1:
            self.request_stop(True)
        else:
            job.skipped += 1
            self.note('模拟跳过一个零件，继续打印其余零件；不改变盘任务。')

    def reconcile_stopped(self, plate_empty=False):
        if self.state != '已暂停':
            raise ValueError('仅暂停后可以核对设备。')
        job = self.selected()
        if job and job.status in ('打印中', '停止中', '待核对'):
            job.status = '已结束'
        self.dirty_plate = not plate_empty
        self.note('人工核对：设备已停止；' + ('热床已清空。' if plate_empty else '热床需要换盘。'))

    def pause_transition(self):
        if self.state in ('换盘中', '等待新板确认', '等待换盘准备确认'):
            self.state = '已暂停'
            self.stop_intent = None
            self.note('暂停换盘流程；实际接入时，换盘动作须由其专用停止/收尾流程处理。')

    def save(self, path):
        path = Path(path)
        data = dict(schema=1, jobs=[asdict(j) for j in self.jobs], state=self.state,
                    current=self.current, attempt=self.attempt, stop_intent=self.stop_intent,
                    dirty_plate=self.dirty_plate, log=self.log, transport='simulation')
        tmp = path.with_suffix('.tmp')
        fs_path(tmp).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        replace_file(tmp, path)

    @classmethod
    def load(cls, path):
        data = json.loads(fs_path(path).read_text(encoding='utf-8'))
        if data.get('schema') != 1 or data.get('transport') != 'simulation':
            raise ValueError('不支持此队列存档。')
        q = cls()
        q.jobs = [Job(**j) for j in data['jobs']]
        q.current = data['current']
        q.dirty_plate = data['dirty_plate']
        q.log = data['log']
        q.state = '已暂停'
        if q.selected() and q.selected().status in ('打印中', '停止中'):
            q.selected().status = '待核对'
        q.note('存档已恢复，队列保持暂停，丢弃旧停止意图和旧回报编号。')
        return q
