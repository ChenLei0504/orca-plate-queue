"""Local browser-to-plugin file transfer, independent of devices and queue settings."""
from pathlib import Path
import base64
import re
import uuid


class LocalImports:
    def __init__(self, storage, enqueue):
        self.storage = storage
        self.enqueue = enqueue
        self.pending = {}

    def close(self):
        for item in self.pending.values():
            try:
                item['path'].unlink(missing_ok=True)
            except OSError:
                pass
        self.pending.clear()

    def handle(self, action, data):
        if action == 'upload_begin':
            name, size, copies = data.get('name', ''), data.get('size'), data.get('copies', 1)
            if not isinstance(name, str) or not name.lower().endswith('.3mf'):
                raise ValueError('只接受 Orca 导出的单盘切片 .3mf 文件。')
            if type(size) is not int or not 0 < size <= 100 * 1024 * 1024:
                raise ValueError('单个文件须大于 0，且不超过 100 MB。')
            if type(copies) is not int or not 1 <= copies <= 100:
                raise ValueError('份数范围为 1–100。')
            if len(self.pending) >= 3:
                raise ValueError('已有导入正在进行，请稍后再试。')
            token = uuid.uuid4().hex
            folder = Path(self.storage()) / 'queue_uploads'
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / ('queue-upload-' + token + '.part')
            path.write_bytes(b'')
            self.pending[token] = dict(path=path, size=size, received=0, seq=0,
                                       name=re.split(r'[\\/]', name)[-1], copies=copies, queue_id=data.get('queue_id'))
            return dict(token=token, chunk_size=192 * 1024)
        item = self.pending.get(data.get('token'))
        if item is None:
            raise ValueError('导入已失效，请重新拖入文件。')
        if item['queue_id'] != data.get('queue_id'):
            raise ValueError('文件属于另一台打印机的导入，请切回原队列处理。')
        if action == 'upload_abort':
            item['path'].unlink(missing_ok=True)
            del self.pending[data['token']]
            return dict(aborted=True)
        if action == 'upload_chunk':
            seq, encoded = data.get('seq'), data.get('content')
            if type(seq) is not int or seq != item['seq']:
                raise ValueError('文件数据顺序不一致，请重新导入。')
            if not isinstance(encoded, str) or not 0 < len(encoded) <= 262144:
                raise ValueError('文件分块大小不合法。')
            raw = base64.b64decode(encoded, validate=True)
            if not raw or item['received'] + len(raw) > item['size']:
                raise ValueError('导入内容为空，或超过声明的文件大小。')
            with item['path'].open('ab') as f:
                f.write(raw)
            item['received'] += len(raw)
            item['seq'] += 1
            return dict(received=item['received'], seq=item['seq'])
        if action == 'upload_end':
            if item['received'] != item['size']:
                raise ValueError('文件数据未传完整，未加入队列。')
            final = item['path'].with_suffix('.3mf')
            item['path'].replace(final)
            try:
                note = self.enqueue(str(final), item['copies'], display_name=item['name'])
            except Exception:
                final.unlink(missing_ok=True)
                raise
            finally:
                del self.pending[data['token']]
            return dict(note=note, complete=True)
        raise ValueError('不支持的文件导入操作。')
