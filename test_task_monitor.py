"""Deterministic replay of callback loss, deltas, stale state and task boundaries."""
import copy
import unittest
from task_monitor import new_monitor,reduce_task,strong_identity


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.now=1000
        self.device=dict(monitor_epoch='session-a',state_event=500,state_age_ms=0,task_sequence=10,task_events=[],
                         telemetry=dict(gcode_state='IDLE',subtask_name='previous',subtask_id='previous'))
        self.active=dict(created=1000,tag='oq_unique_attempt',identity={},seen_running=False,start_event=0,
                         monitor=new_monitor(self.device))

    def telemetry(self,state,**kw):return dict(gcode_state=state,subtask_name=self.active['tag'],subtask_id='actual',**kw)
    def snapshot(self,state,**kw):
        self.now+=1;self.device['state_event']+=1;self.device['telemetry']=self.telemetry(state,**kw)
        return self.reduce()
    def reduce(self):
        result=reduce_task(self.active,self.device,self.now)
        self.active.update(monitor=result['monitor'],identity=result['identity'],seen_running=result['observed_running'])
        return result
    def record(self,state,reported=True,age=0,**kw):
        self.device['task_sequence']+=1
        record=dict(event=self.device['task_sequence'],age_ms=age,state_reported=reported,telemetry=self.telemetry(state,**kw))
        self.device['task_events'].append(record);return record

    def test_normal_snapshot_lifecycle(self):
        self.assertEqual(self.snapshot('PREPARE')['monitor']['stage'],'preparing')
        self.assertFalse(self.active['identity'])
        self.assertEqual(self.snapshot('RUNNING')['monitor']['stage'],'printing')
        self.assertEqual(self.snapshot('FINISH')['decision'],'completed')

    def test_entire_running_phase_can_be_recovered_from_native_history(self):
        self.record('PREPARE');self.record('RUNNING');self.record('FINISH')
        self.device['telemetry']=self.telemetry('FINISH',mc_percent=100)
        result=self.reduce()
        self.assertEqual(result['decision'],'completed')
        self.assertEqual([e['kind'] for e in result['monitor']['evidence']],['started','terminal'])

    def test_finish_followed_by_idle_and_cleared_title_uses_ordered_history(self):
        self.record('RUNNING');self.record('FINISH');self.device['telemetry']=dict(gcode_state='IDLE')
        self.assertEqual(self.reduce()['decision'],'completed')

    def test_buffered_failure_never_becomes_success(self):
        self.record('RUNNING');self.record('FAILED');self.device['telemetry']=dict(gcode_state='IDLE')
        self.assertEqual(self.reduce()['decision'],'failed')

    def test_new_task_title_with_old_finish_does_not_complete(self):
        result=self.snapshot('FINISH',mc_percent=100)
        self.assertFalse(result['observed_running']);self.assertEqual(result['decision'],'wait')
        self.now+=46
        self.assertEqual(self.reduce()['decision'],'wait') # Within startup allowance.
        self.now+=250;self.assertEqual(self.reduce()['monitor']['stage'],'verifying_finish')
        self.now+=46;self.assertEqual(self.reduce()['decision'],'ambiguous')

    def test_pre_dispatch_history_is_not_reused(self):
        self.device['task_events']=[dict(event=9,age_ms=0,state_reported=True,telemetry=self.telemetry('RUNNING')),
                                    dict(event=10,age_ms=0,state_reported=True,telemetry=self.telemetry('FINISH'))]
        self.device['telemetry']=self.telemetry('FINISH')
        self.assertFalse(self.reduce()['observed_running'])

    def test_no_progress_or_repeated_finish_can_manufacture_running(self):
        for _ in range(10):
            result=self.snapshot('FINISH',mc_percent=100)
            self.assertEqual(result['decision'],'wait');self.assertFalse(result['observed_running'])

    def test_partial_delta_without_explicit_running_state_is_not_start_evidence(self):
        self.record('RUNNING',reported=False);self.record('FINISH')
        self.device['telemetry']=self.telemetry('FINISH');result=self.reduce()
        self.assertEqual(result['decision'],'wait');self.assertFalse(result['observed_running'])

    def test_other_task_history_never_completes_this_attempt(self):
        for state in ('RUNNING','FINISH'):
            r=self.record(state);r['telemetry']['subtask_name']='different'
        self.device['telemetry']=self.telemetry('FINISH')
        self.assertEqual(self.reduce()['decision'],'wait')

    def test_other_current_active_task_blocks_an_old_matching_terminal(self):
        self.record('RUNNING');self.record('FINISH')
        self.device['telemetry']=dict(gcode_state='RUNNING',subtask_name='foreign',subtask_id='foreign')
        self.assertEqual(self.reduce()['monitor']['stage'],'syncing')
        self.now+=16;self.assertEqual(self.reduce()['decision'],'conflict')

    def test_foreign_task_in_buffer_blocks_old_completion_even_if_currently_idle(self):
        self.record('RUNNING');self.record('FINISH')
        other=self.record('RUNNING');other['telemetry'].update(subtask_name='foreign',subtask_id='foreign')
        other=self.record('FINISH');other['telemetry'].update(subtask_name='foreign',subtask_id='foreign')
        self.device['telemetry']=dict(gcode_state='IDLE')
        self.assertEqual(self.reduce()['monitor']['stage'],'syncing');self.now+=16
        self.assertEqual(self.reduce()['decision'],'conflict')

    def test_same_tag_but_different_subtask_in_history_is_a_real_conflict(self):
        self.record('RUNNING');self.record('FINISH');other=self.record('RUNNING');other['telemetry']['subtask_id']='foreign'
        self.device['telemetry']=self.telemetry('FINISH')
        self.assertEqual(self.reduce()['decision'],'wait');self.now+=16
        self.assertEqual(self.reduce()['decision'],'conflict')

    def test_restored_actual_running_callback_resolves_transient_history_conflict(self):
        self.record('RUNNING');other=self.record('RUNNING');other['telemetry']['subtask_name']='transient'
        self.record('RUNNING');self.record('FINISH');self.device['telemetry']=self.telemetry('FINISH')
        self.assertEqual(self.reduce()['decision'],'completed')

    def test_optional_task_id_changes_do_not_break_subtask_binding(self):
        self.snapshot('RUNNING',task_id='provisional')
        result=self.snapshot('FINISH',task_id='arrived-later')
        self.assertEqual(result['decision'],'completed');self.assertEqual(result['identity'],{'subtask_id':'actual'})

    def test_primary_subtask_change_requires_recheck_and_never_finishes_other_job(self):
        self.snapshot('RUNNING');self.device['telemetry']=self.telemetry('FINISH');self.device['telemetry']['subtask_id']='foreign'
        self.assertEqual(self.reduce()['decision'],'wait');self.now+=16
        self.assertEqual(self.reduce()['decision'],'conflict')

    def test_missing_identity_recovers_without_manual_intervention_if_restored(self):
        self.snapshot('RUNNING');self.device['telemetry']=dict(gcode_state='RUNNING')
        self.assertEqual(self.reduce()['monitor']['stage'],'syncing')
        self.now+=3;self.assertEqual(self.snapshot('RUNNING')['monitor']['stage'],'printing')
        self.assertEqual(self.snapshot('FINISH')['decision'],'completed')

    def test_stale_finish_waits_for_fresh_state(self):
        self.snapshot('RUNNING');self.device['state_age_ms']=20000
        self.assertEqual(self.snapshot('FINISH')['decision'],'wait')
        self.device['state_age_ms']=0
        self.assertEqual(self.snapshot('FINISH')['decision'],'completed')

    def test_temperature_updates_without_new_state_do_not_finish(self):
        self.snapshot('RUNNING');self.device['telemetry']=self.telemetry('FINISH')
        self.assertEqual(self.reduce()['decision'],'wait')

    def test_callback_and_snapshot_counters_are_different_domains(self):
        self.snapshot('RUNNING') # state_event > 500, callback sequence ~ 10.
        self.record('FINISH');self.device['telemetry']=dict(gcode_state='IDLE')
        self.assertEqual(self.reduce()['decision'],'completed')

    def test_later_running_invalidates_buffered_finish(self):
        self.record('RUNNING');self.record('FINISH');self.record('RUNNING')
        self.device['telemetry']=self.telemetry('RUNNING')
        result=self.reduce();self.assertEqual(result['decision'],'wait');self.assertNotIn('terminal',result['monitor'])

    def test_old_records_after_epoch_change_are_filtered_by_attempt_age(self):
        self.device['monitor_epoch']='new-session';self.device['task_sequence']=2
        self.device['task_events']=[dict(event=i,age_ms=100000,state_reported=True,telemetry=self.telemetry(state)) for i,state in [(1,'RUNNING'),(2,'FINISH')]]
        self.device['telemetry']=self.telemetry('FINISH')
        self.assertFalse(self.reduce()['observed_running'])

    def test_persisted_evidence_survives_python_monitor_reconstruction(self):
        self.snapshot('RUNNING');saved=copy.deepcopy(self.active)
        self.active=copy.deepcopy(saved);self.device['monitor_epoch']='new-session';self.device['state_event']=1
        self.device['telemetry']=self.telemetry('FINISH')
        self.assertEqual(self.reduce()['decision'],'completed')

    def test_repeated_poll_does_not_grow_evidence_or_create_new_transition(self):
        first=self.snapshot('RUNNING')['monitor']
        for _ in range(10):self.assertEqual(self.reduce()['monitor'],first)

    def test_reducer_never_mutates_caller_data(self):
        before=copy.deepcopy((self.active,self.device));reduce_task(self.active,self.device,self.now)
        self.assertEqual((self.active,self.device),before)

    def test_long_preparation_is_not_the_old_four_minute_completion_timeout(self):
        self.now+=400;self.assertEqual(self.snapshot('PREPARE')['monitor']['stage'],'preparing')
        self.assertEqual(self.snapshot('RUNNING')['decision'],'wait')

    def test_unconfirmed_attempt_eventually_becomes_reviewable(self):
        self.now+=601;self.assertEqual(self.reduce()['decision'],'ambiguous')

    def test_identity_priority_does_not_freeze_optional_fields(self):
        self.assertEqual(strong_identity(dict(subtask_id='actual',task_id='later',gcode_start_time='123')),{'subtask_id':'actual'})
        self.assertEqual(strong_identity(dict(task_id='fallback')),{'task_id':'fallback'})


if __name__=='__main__':unittest.main()
