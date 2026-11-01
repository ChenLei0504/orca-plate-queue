"""Pure task lifecycle reducer. It cannot send commands, touch files or swap plates."""
import copy

MONITOR_ACTIVE={'RUNNING','PAUSE','PREPARE','SLICING'}
MONITOR_TERMINAL={'FINISH','FAILED'}


def strong_identity(telemetry):
    values={k:str(telemetry[k]) for k in ('subtask_id','gcode_start_time','task_id')
            if str(telemetry.get(k,'')) not in ('','0','None')}
    # Additional identifiers can arrive separately from subtask_id.
    # Anchor the actual subtask; never freeze every optional field at startup.
    if 'subtask_id' in values:return {'subtask_id':values['subtask_id']}
    if 'gcode_start_time' in values:return {'gcode_start_time':values['gcode_start_time']}
    return {'task_id':values['task_id']} if 'task_id' in values else {}


def matches_task(telemetry,tag,identity=None):
    if telemetry.get('subtask_name')!=tag:return False
    if not identity:return bool(strong_identity(telemetry))
    return all(str(telemetry.get(k,''))==str(v) for k,v in identity.items())


def new_monitor(device):
    return dict(schema=1,stage='awaiting_start',identity={},observed_running=False,
        epoch=device.get('monitor_epoch',''),cursor=device.get('task_sequence',0),
        baseline_event=device.get('state_event',0),baseline_epoch=device.get('monitor_epoch',''),
        evidence=[])


def _evidence(m,kind,telemetry,origin,event,epoch):
    row=dict(kind=kind,state=telemetry.get('gcode_state',''),identity=strong_identity(telemetry),
             origin=origin,event=event,epoch=epoch)
    if not m['evidence'] or m['evidence'][-1]!=row:
        m['evidence'].append(row);m['evidence']=m['evidence'][-32:]


def reduce_task(active,device,now):
    """Return a durable monitor and decision from a fresh device snapshot/history.

    Only an ordered RUNNING/PAUSE -> terminal sequence for this unique attempt
    can complete automatically. Repeated polls are not independent evidence.
    """
    m=copy.deepcopy(active.get('monitor'))
    if not m:
        m=new_monitor({})
        m['legacy']=True
        if active.get('seen_running') and active.get('identity'):
            m.update(identity=strong_identity(active['identity']),observed_running=True,
                     run_event=active.get('start_event',0),run_epoch=device.get('monitor_epoch',''))
    t=device.get('telemetry',{});tag=active['tag'];epoch=device.get('monitor_epoch','')
    m.pop('connection_gap_since',None)
    age=device.get('state_age_ms',1e9);state=t.get('gcode_state','')
    fresh=age<=15000
    decision='wait';detail='等待打印机确认本次任务。'

    def observe(telemetry,origin,event,event_epoch):
        nonlocal decision,detail
        status=telemetry.get('gcode_state','')
        if not matches_task(telemetry,tag) or (m.get('identity') and not matches_task(telemetry,tag,m['identity'])):
            if origin=='callback' and m['observed_running'] and status in MONITOR_ACTIVE and telemetry.get('subtask_name') and strong_identity(telemetry):
                m['intervening_task']=dict(epoch=event_epoch,event=event)
                _evidence(m,'conflicting_activity',telemetry,origin,event,event_epoch)
            return
        candidate=strong_identity(telemetry)
        if status in ('RUNNING','PAUSE'):
            foreign=m.get('intervening_task')
            if origin=='callback' and foreign and (foreign['epoch']!=event_epoch or event>foreign['event']):
                m.pop('intervening_task',None)
            first=not m['observed_running']
            m.update(identity=m.get('identity') or candidate,observed_running=True,
                     stage='paused' if status=='PAUSE' else 'printing')
            if first:
                m.update(run_event=event,run_epoch=event_epoch,run_origin=origin)
                _evidence(m,'started',telemetry,origin,event,event_epoch)
            terminal=m.get('terminal')
            if terminal and (origin=='snapshot' or terminal.get('origin')!=origin or terminal['epoch']!=event_epoch or event>terminal['event']):
                m.pop('terminal',None)
        elif status in MONITOR_TERMINAL and m['observed_running'] and matches_task(telemetry,tag,m['identity']):
            newer=origin!=m.get('run_origin','snapshot') or event_epoch!=m.get('run_epoch','') or event>m.get('run_event',0)
            if newer:
                old=m.get('terminal')
                if not (old and old.get('origin')=='callback' and origin=='snapshot' and old['state']==status):
                    m['terminal']=dict(state=status,event=event,epoch=event_epoch,origin=origin)
                    _evidence(m,'terminal',telemetry,origin,event,event_epoch)

    # Consume significant callback transitions even when Python missed intermediate polls.
    # Epoch changes cannot compare counters. Filter old records by attempt creation time.
    cursor=m.get('cursor',0) if m.get('epoch')==epoch else 0
    for record in sorted(device.get('task_events',[]),key=lambda e:e['event']):
        if record['event']<=cursor:continue
        if record.get('age_ms',1e9)>max(0,now-active['created'])*1000+2000:continue
        if record.get('state_reported') is True:
            observe(record['telemetry'],'callback',record['event'],epoch)
    m['epoch']=epoch
    m['cursor']=max(cursor,device.get('task_sequence',0))
    # Baseline prevents treating a pre-dispatch state as new task activity.
    event=device.get('state_event',0)
    after_baseline=m.get('legacy') or epoch!=m.get('baseline_epoch') or event>m.get('baseline_event',0)
    if fresh and after_baseline:
        observe(t,'snapshot',event,epoch)

    owned=matches_task(t,tag,m.get('identity') or None)
    terminal=m.get('terminal')
    # A terminal callback is retained across a subsequent firmware IDLE/cleared title.
    # A different active task always blocks next-plate dispatch.
    settled=(owned and state in MONITOR_TERMINAL) or (state=='IDLE' and t.get('subtask_name') in ('',None,tag))
    if terminal and fresh and settled and not m.get('intervening_task'):
        decision='completed' if terminal['state']=='FINISH' else 'failed'
        m['stage']=decision
        detail='已核对本次任务的启动与结束回报。'
        m.pop('sync_since',None);m.pop('idle_since',None)
    elif m.get('intervening_task') or (not owned and state in MONITOR_ACTIVE|MONITOR_TERMINAL and (m['observed_running'] or state in MONITOR_ACTIVE)):
        # Delta messages / reconnect snapshots can temporarily omit identifiers.
        # Hold all actions while requesting a fresh state, before declaring a conflict.
        m.setdefault('sync_since',now);m['stage']='syncing'
        detail='正在重新核对本次任务状态，后续任务暂不发送。'
        if now-m['sync_since']>=15:
            decision='conflict';detail='任务身份持续不匹配，请核对设备；不会对其他任务执行操作。'
    else:
        m.pop('sync_since',None)
        if owned and state in ('PREPARE','SLICING') and not m['observed_running']:
            m['stage']='preparing';detail='设备正在准备本次任务，等待开始打印。'
        elif owned and state in ('RUNNING','PAUSE') and m['observed_running']:
            m['stage']='paused' if state=='PAUSE' else 'printing'
            detail='当前打印已暂停，可在本页或 Handy 继续打印。' if state=='PAUSE' else ''
        elif state in MONITOR_TERMINAL|{'IDLE'}:
            if not m['observed_running'] and now-active['created']<=240:
                m['stage']='awaiting_start';detail='等待打印机确认本次任务启动，暂不采用上一盘的结束状态。'
            else:
                m.setdefault('idle_since',now);m['stage']='verifying_finish'
                detail='正在补齐本盘的启动与完成记录，后续任务暂不发送。'
                if now-m['idle_since']>=45:
                    decision='ambiguous';detail='仍缺少可核对的本盘启动或结束记录，请人工核对；不会重发本盘。'
        else:
            m['stage']='awaiting_start'
    if not m['observed_running'] and m['stage'] not in ('preparing','syncing') and now-active['created']>600 and decision=='wait':
        decision='ambiguous';detail='等待本次任务启动超过十分钟，请核对设备和云端待发任务。'
    return dict(monitor=m,decision=decision,detail=detail,identity=m.get('identity',{}),
                observed_running=m['observed_running'])
