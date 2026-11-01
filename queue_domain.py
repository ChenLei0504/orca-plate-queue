"""Queue setup rules. No host, UI, connection, or filesystem side effects."""
import copy
import math
import re
from printer_models import canonical_model


def blank_print_settings(device_id=''):
    return dict(device_id=device_id, source='ams', mapping={}, external_ready=False,
                options=dict(bed_leveling=True, flow_calibration=False, timelapse=False))


def fresh_queue(default_swap_file):
    return dict(schema=3, jobs=[], previews={}, auto_export=False, device_id='',
                a1_swap=dict(path=default_swap_file, nozzle=.4, enabled=True,
                             validated=False, settings=blank_print_settings()))


def find_device(connection, device_id):
    return next((d for d in connection.get('devices', []) if d['id'] == device_id), None)


def refill_identity(slot):
    """Compare reported type and RGBA color; a missing color is never a match."""
    kind = str(slot.get('type', '')).strip().upper()
    color = str(slot.get('color', '')).strip().lstrip('#').upper()
    if (not kind or not re.fullmatch(r'[0-9A-F]{6}(?:[0-9A-F]{2})?', color)
            or (len(color) == 8 and color.endswith('00'))):
        return None
    return dict(type=kind, color=color + ('FF' if len(color) == 6 else ''))


def configure_print_settings(asset, settings, connection, bound_device, previous=None):
    """Capture backup identities from real reports, never trust browser fingerprints."""
    if not isinstance(settings, dict):
        raise ValueError('打印设置格式错误。')
    draft = copy.deepcopy(settings)
    if not isinstance(draft.get('mapping'), dict):
        raise ValueError('耗材槽映射格式错误。')
    groups = draft.get('refill', {})
    if not isinstance(groups, dict):
        raise ValueError('备用槽设置格式错误。')
    device = find_device(connection, bound_device) or {}
    slots = {s['id']: s for s in device.get('slots', [])}
    captured = {}
    for source, group in groups.items():
        if not isinstance(group, dict) or not isinstance(group.get('slots'), list):
            raise ValueError('请选择备用耗材槽。')
        primary = draft.get('mapping', {}).get(source)
        identity = refill_identity(slots.get(primary, {}))
        # An unchanged saved primary may have lost its metadata after running out.
        old = (previous or {}).get('refill', {}).get(source, {})
        if ((previous or {}).get('device_id') == bound_device
                and (previous or {}).get('source') == 'ams'
                and (previous or {}).get('mapping', {}).get(source) == primary and old):
            identity = {k: old.get(k) for k in ('type', 'color')}
        if not identity:
            raise ValueError('主槽缺少类型或颜色，请装料并刷新后设置备用槽。')
        for slot_id in group['slots']:
            slot = slots.get(slot_id) if isinstance(slot_id, str) else None
            if not slot or slot.get('kind') != 'ams':
                raise ValueError('备用槽不存在或不是 AMS 槽位。')
            actual = refill_identity(slot)
            known_type = str(slot.get('type', '')).strip().upper()
            partial = refill_identity(dict(type=identity['type'], color=slot.get('color', '')))
            retained_empty = (slot.get('present') is False and slot_id in old.get('slots', [])
                              and (not known_type or known_type == identity['type'])
                              and (not slot.get('color') or partial == identity))
            if actual != identity and not retained_empty:
                raise ValueError('备用槽必须与主槽的耗材类型、颜色一致，请刷新后检查。')
            if actual is None and slot_id not in old.get('slots', []):
                raise ValueError('新备用槽缺少类型或颜色，请装料并刷新后设置。')
        captured[source] = dict(slots=copy.deepcopy(group['slots']), **identity)
    draft['refill'] = captured
    return validate_print_settings(asset, draft, connection, bound_device, require_ready=False)


def resolve_refill(mapping, groups, slots, materials, require_ready):
    """Resolve independent, explicit groups without changing the saved primary."""
    if not isinstance(groups, dict) or not set(groups).issubset(mapping):
        raise ValueError('备用槽对应的切片耗材编号无效。')
    occupied = set(mapping.values())
    result = copy.deepcopy(mapping)
    for source, group in groups.items():
        if not isinstance(group, dict):
            raise ValueError('备用槽设置格式错误。')
        backups = group.get('slots')
        identity = {k: group.get(k) for k in ('type', 'color')}
        if (not isinstance(backups, list) or not 1 <= len(backups) <= 63
                or any(not isinstance(s, str) or not s for s in backups)
                or len(set(backups)) != len(backups)):
            raise ValueError('每种耗材请选择不重复的备用槽。')
        if refill_identity(identity) != identity or identity['type'] != materials[source]['type'].strip().upper():
            raise ValueError('备用槽的耗材登记无效，请重新保存设置。')
        for slot_id in backups:
            if slot_id in occupied:
                raise ValueError('不同切片耗材的主槽、备用槽不能重复。')
            occupied.add(slot_id)
        if require_ready:
            candidates = [mapping[source], *backups]
            result[source] = next((slot_id for slot_id in candidates
                if (slot := slots.get(slot_id)) and slot['kind'] == 'ams'
                and slot['present'] is True and refill_identity(slot) == identity), '')
            if not result[source]:
                raise ValueError('切片耗材 '+source+' 的主槽和备用槽均无可用的同类型、同颜色耗材；队列已暂停。')
    return result


def validate_print_settings(asset, settings, connection, bound_device, require_send=False, require_ready=True):
    """Check against the latest real snapshot; never infer a tray from its position."""
    if not connection.get('available'):
        raise ValueError(connection.get('reason') or '尚未接通设备连接。')
    if require_send:
        require_ready = True
        if not connection.get('can_submit'):
            raise ValueError('设备信息可读，但真实发送接口尚未接通。')
    if not isinstance(settings, dict):
        raise ValueError('打印设置格式错误。')
    device_id = settings.get('device_id')
    if not device_id or device_id != bound_device:
        raise ValueError('任务必须使用当前队列绑定的打印机。')
    device = find_device(connection, device_id)
    if not device or not device['online'] or device['age_ms'] > 15000:
        raise ValueError('目标打印机离线，或设备信息超过 15 秒未更新。')
    model = canonical_model(device['model'])
    if not model or canonical_model(asset.get('printer')) != model:
        raise ValueError('切片机型与这条队列的实际打印机不一致，或该机型尚未支持。')
    if asset.get('motion_only') and model != 'N2S':
        raise ValueError('套件默认机械换盘程序仅适用于 A1，不能发送到其他机型。')
    if not device['cloud_connected']:
        raise ValueError('需要保留云端连接，以便 Bambu Handy 远程操作。')
    if device['nozzle'] is None:
        raise ValueError('尚未收到打印机喷嘴规格，请刷新设备状态。')
    try:
        nozzle = float(asset.get('nozzle', ''))
    except (ValueError, TypeError):
        raise ValueError('切片缺少明确的喷嘴规格，请重新导出。')
    if not math.isfinite(nozzle) or abs(nozzle - device['nozzle']) > .0001:
        raise ValueError('切片喷嘴与目标打印机喷嘴不一致。')
    if asset.get('motion_only'):
        # Only the exact, inspected kit archive qualifies. Its formal G-code
        # contains mechanical movement, heater-off commands and no extrusion.
        return dict(device_id=device_id, source='external', mapping={},
                    options=dict(bed_leveling=False, flow_calibration=False, timelapse=False))
    materials = asset.get('filaments', [])
    if not materials or any(not f['type'] for f in materials):
        raise ValueError('切片缺少完整耗材登记，不能发送。')
    for material in materials:
        try:
            material_nozzle = float(material['nozzle'])
            if not math.isfinite(material_nozzle) or abs(material_nozzle - nozzle) > .0001:
                raise ValueError()
        except (ValueError, TypeError, KeyError):
            raise ValueError('切片耗材的喷嘴登记不完整或不一致。')
    source, mapping = settings.get('source'), settings.get('mapping')
    if source not in ('ams', 'external') or not isinstance(mapping, dict):
        raise ValueError('请选择 AMS 或外挂耗材，并逐项映射。')
    if source == 'external' and len(materials) != 1:
        raise ValueError('多耗材切片不能作为单一外挂耗材自动打印；请改用 AMS 或重新切片。')
    if set(mapping) != {f['id'] for f in materials}:
        raise ValueError('必须为本盘每一种切片耗材指定槽位，不能遗漏或增加编号。')
    if any(not isinstance(v, str) for v in mapping.values()) or len(set(mapping.values())) != len(mapping):
        raise ValueError('每种切片耗材必须选择独立的实际槽位。')
    slots = {s['id']: s for s in device['slots']}
    groups = settings.get('refill', {})
    if source != 'ams' and groups:
        raise ValueError('外挂耗材不能设置 AMS 备用槽。')
    mapping = resolve_refill(mapping, groups, slots, {f['id']: f for f in materials}, require_ready)
    for material in materials:
        slot = slots.get(mapping[material['id']])
        if not require_ready and material['id'] in groups:
            # The pinned group remains configured after a primary spool is empty.
            continue
        if require_ready and slot and slot.get('present') is None and not (source == 'external' and settings.get('external_ready') is True):
            raise ValueError('尚未确认所选耗材是否在位，请刷新打印机完整状态。')
        if not slot or slot['kind'] != source or (require_ready and slot['present'] is False):
            raise ValueError('所选耗材槽已变化、无料，或与供料方式不符。')
        if material['type'].strip().upper() != slot['type'].strip().upper():
            raise ValueError('切片耗材 ' + material['id'] + ' 的类型与所选实际耗材不一致。')
    options = settings.get('options')
    if not isinstance(options, dict) or set(options) != {'bed_leveling', 'flow_calibration', 'timelapse'} or any(type(v) is not bool for v in options.values()):
        raise ValueError('打印选项不完整。')
    if any(enabled and key not in device['supported_options'] for key, enabled in options.items()):
        raise ValueError('目标打印机不支持所启用的打印选项。')
    if require_send and not connection.get('can_submit'):
        raise ValueError('设备信息可读，但真实发送接口尚未接通。')
    # Whitelist stored fields; never pass arbitrary browser input to the printer.
    return dict(device_id=device_id, source=source, mapping=copy.deepcopy(mapping), refill=copy.deepcopy(groups), external_ready=settings.get('external_ready') is True, options=copy.deepcopy(options))


def setup_report(asset, settings, connection, bound_device):
    mapping = settings.get('mapping', {}) if isinstance(settings, dict) else {}
    configured = bool(isinstance(settings, dict) and bound_device and settings.get('device_id')==bound_device
                      and (asset.get('motion_only') or (asset.get('filaments') and isinstance(mapping,dict)
                           and set(mapping)=={f['id'] for f in asset['filaments']} and all(isinstance(v,str) and v for v in mapping.values()))))
    try:
        validate_print_settings(asset, settings, connection, bound_device, require_ready=False)
    except (ValueError, TypeError, KeyError) as exc:
        return dict(ready=False, configured=configured, label='待检查' if configured else '待配置', reason=str(exc))
    try:
        resolved = validate_print_settings(asset, settings, connection, bound_device)
        changed = resolved['mapping'] != mapping
        return dict(ready=True, configured=True, label='备用槽就绪' if changed else '已就绪',
                    resolved_mapping=resolved['mapping'],
                    reason='主槽不可用，将使用已指定的同类型、同颜色备用槽。发送前再次核对。' if changed else '发送前会重新核对文件、设备和耗材。')
    except (ValueError, TypeError, KeyError) as exc:
        return dict(ready=False, configured=True, label='待检查', reason=str(exc))


def material_signature(asset):
    """Only explicitly selected jobs with identical sliced materials share a draft."""
    def diameter(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    return (asset.get('printer'), diameter(asset.get('nozzle')), tuple(sorted(
        (f['id'], f.get('type','').strip().upper(), f.get('color','').upper(),
         f.get('profile_id',''), diameter(f.get('nozzle')))
        for f in asset.get('filaments', []))))


def bind_queue(data, device_id, connection):
    device = find_device(connection, device_id)
    if not device or not device['online'] or not canonical_model(device['model']) or not device['cloud_connected'] or device['age_ms'] > 15000:
        raise ValueError('请选择云端在线且信息有效的受支持打印机。')
    if any(j['status'] != '等待' for j in data['jobs']):
        raise ValueError('已有执行记录时不能更换队列打印机。')
    if data['device_id'] == device_id:
        return
    data['device_id'] = device_id
    for row in data['jobs']:
        row['settings'] = blank_print_settings(device_id)
    data['a1_swap']['settings'] = blank_print_settings(device_id)
