"""Build one self-contained .py plugin; no installation or execution in Orca."""
import inspect
from pathlib import Path
from queue_core import inspect_plate, plate_thumbnail, plate_materials
from release_info import QUEUE_VERSION, QUEUE_BUILD_ID
import re

root = Path(__file__).resolve().parent
out = root / 'plugin-dist'
out.mkdir(exist_ok=True)
header = '''# /// script
# requires-python = ">=3.12"
# dependencies = []
# [tool.orcaslicer.plugin]
# name = "Orca Plate Queue"
# description = "A1 / P1S 多打印机独立队列：原生连接、AMS/外挂、A1 换盘、零件跳过与停止恢复。"
# author = "Local workspace"
# version = "0.7.2"
# ///
from pathlib import Path
import hashlib
import base64
import struct
import json
import re
import uuid
import zipfile
import xml.etree.ElementTree as ET
QUEUE_BUILD_ID = '20261031.6'
'''
source = header + '\n' + inspect.getsource(plate_thumbnail) + '\n' + inspect.getsource(plate_materials) + '\n' + inspect.getsource(inspect_plate)
source += '\n' + (root / 'object_preview.py').read_text(encoding='utf-8')
source += '\n' + (root / 'printer_models.py').read_text(encoding='utf-8')
source += '\n' + (root / 'swap_support.py').read_text(encoding='utf-8').replace('from printer_models import canonical_model', '')
source += '\n' + (root / 'queue_domain.py').read_text(encoding='utf-8').replace('from printer_models import canonical_model', '')
source += '\n' + (root / 'native_connection.py').read_text(encoding='utf-8').replace('from printer_models import canonical_model', '')
source += '\n' + (root / 'printer_connection.py').read_text(encoding='utf-8').replace('from printer_models import canonical_model', '')
source += '\n' + (root / 'queue_imports.py').read_text(encoding='utf-8')
source += '\n' + (root / 'task_monitor.py').read_text(encoding='utf-8')
source += '\n' + (root / 'queue_engine.py').read_text(encoding='utf-8').replace('from queue_domain import blank_print_settings, find_device, validate_print_settings', '')
source=source.replace('from task_monitor import new_monitor, reduce_task, strong_identity, matches_task','')
source = source.replace('from printer_models import supports_auto_swap', '').replace('from object_preview import inspect_object_preview', '')
fleet = (root / 'queue_fleet.py').read_text(encoding='utf-8')
for line in ('from printer_models import canonical_model, supports_auto_swap', 'from queue_domain import blank_print_settings, bind_queue, find_device', 'from queue_engine import QueueService'):
    fleet = fleet.replace(line, '')
source += '\n' + fleet
page = (root / 'plugin_page.html').read_text(encoding='utf-8')
page = page.replace('<link rel="stylesheet" href="plugin_page.css">', '<style>\n' + (root / 'plugin_page.css').read_text(encoding='utf-8') + '\n</style>')
page = page.replace('<script src="plugin_page.js"></script>', '<script>\n' + (root / 'plugin_page.js').read_text(encoding='utf-8') + '\n</script>')
source += '\nQUEUE_PAGE_HTML = ' + repr(page) + '\n'
runtime = (root / 'plugin_runtime.py').read_text(encoding='utf-8')
runtime = re.sub(r'^from (?:queue_core|queue_domain|printer_models|printer_connection|queue_engine|queue_fleet|queue_imports|swap_support|release_info|page_assets) import .*\n', '', runtime, flags=re.M)
source += runtime
source = source.replace('from native_connection import NativeQueueBridge, NativeBridgeBindingError', '').replace('from queue_core import plate_materials, plate_thumbnail', '')
source = source.replace('# version = "0.7.2"', '# version = "'+QUEUE_VERSION+'"').replace("QUEUE_BUILD_ID = '20261031.6'", 'QUEUE_BUILD_ID = '+repr(QUEUE_BUILD_ID))
source = source.replace('QUEUE_BUILD_ID = '+repr(QUEUE_BUILD_ID), 'QUEUE_VERSION = '+repr(QUEUE_VERSION)+'\nQUEUE_BUILD_ID = '+repr(QUEUE_BUILD_ID), 1)
target = out / 'orca_plate_queue.py'
compile(source, str(target), 'exec')
target.write_text(source, encoding='utf-8')
print(target)
