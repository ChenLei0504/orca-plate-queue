// SPDX-License-Identifier: AGPL-3.0-or-later
#include "queue_cache.hpp"
#include <cassert>
#include <iostream>
using namespace queue_bridge;

int main() {
    Cache c;c.login(true);c.cloud(true);
    c.catalog(R"({"devices":[{"dev_id":"fixture-a1","dev_name":"验证设备","dev_model_name":"N2S","dev_online":true,"dev_access_code":"SECRET-NOT-EXPORTED"}]})");
    c.select("fixture-a1");
    assert(c.selected_a1()=="fixture-a1");
    auto before=c.snapshot(false);assert(before.find("devices[0].nozzle").is_null());
    assert(before.find("devices[0].age_ms").as_number()>15000);
    assert(before.dump().find("SECRET")==std::string::npos);
    c.ingest("fixture-a1",R"({"print":{"command":"pause","result":"success"}})","cloud");
    assert(c.snapshot(false).find("devices[0].state_messages").as_int()==0);
    c.ingest("fixture-a1",R"({"print":{"gcode_state":"IDLE","nozzle_temper":28.5,"bed_temper":25.5,"nozzle_diameter":"0.4","hw_switch_state":1,"ams":{"ams_exist_bits":"0","tray_exist_bits":"0"},"vt_tray":{"id":"254","tray_type":"PETG","tray_color":"EBE6E6FF"},"access_code":"SECRET-ALSO-NOT-EXPORTED"}})","lan");
    auto a=c.snapshot(false);assert(a.find("devices[0].nozzle").as_number()==.4);
    assert(a.find("devices[0].telemetry.nozzle_temper").as_number()==28.5);
    assert(a.find("devices[0].slots[0].id").as_string()=="external");
    assert(a.find("devices[0].slots[0].present").as_bool());
    assert(a.find("devices[0].slots[0].color").as_string()=="#EBE6E6FF");
    assert(a.dump().find("SECRET")==std::string::npos);
    c.ingest("fixture-a1",R"({"info":{"command":"get_version","module":[]}})","lan");
    assert(c.snapshot(false).find("devices[0].state_messages").as_int()==1);
    c.ingest("fixture-a1","{broken","lan");
    assert(c.snapshot(false).find("devices[0].state_messages").as_int()==1);
    c.ingest("fixture-a1",R"({"print":{"nozzle_temper":29}})","lan");
    assert(c.snapshot(false).find("devices[0].slots[0].type").as_string()=="PETG");
    c.ingest("fixture-a1",R"({"print":{"ams":{"ams_exist_bits":"1","tray_exist_bits":"5","ams":[{"id":"0","tray":[{"id":"0","tray_type":"PETG","tray_color":"112233FF"},{"id":"2","tray_type":"PLA","tray_color":"445566FF"}]}]}}})","lan");
    a=c.snapshot(false);assert(a.find("devices[0].slots[0].id").as_string()=="ams/0/tray/0");
    assert(a.find("devices[0].slots[1].id").as_string()=="ams/0/tray/2");
    assert(a.find("devices[0].slots[0].present").as_bool());
    assert(a.find("devices[0].slots[2].present").is_null());
    c.ingest("fixture-a1",R"({"print":{"ams":{"tray_now":"254"}}})","lan");
    assert(c.snapshot(false).find("devices[0].slots[2].present").as_bool());
    c.ingest("fixture-a1",R"({"print":{"ams":{"ams":[{"id":"0","tray":[{"id":"2","tray_type":"ABS"}]}]}}})","lan");
    a=c.snapshot(false);assert(a.find("devices[0].slots[0].type").as_string()=="PETG");
    assert(a.find("devices[0].slots[1].type").as_string()=="ABS");
    c.ingest("fixture-a1",R"({"t_utc":2000,"print":{"subtask_name":"new-task","subtask_id":"new-id","gcode_state":"RUNNING"}})","lan");
    c.ingest("fixture-a1",R"({"t_utc":1000,"print":{"gcode_state":"FINISH","subtask_id":"old-id"}})","cloud");
    assert(c.snapshot(false).find("devices[0].telemetry.gcode_state").as_string()=="RUNNING");
    c.ingest("fixture-a1",R"({"t_utc":3000,"print":{"subtask_name":"next-task"}})","lan");
    assert(c.snapshot(false).find("devices[0].telemetry.subtask_id").is_null());
    c.cloud(false);a=c.snapshot(false);
    assert(!a.find("devices[0].cloud_connected").as_bool());
    assert(a.find("devices[0].age_ms").as_number()>15000);
    assert(a.find("devices[0].slots").as_array().empty());
    assert(a.find("devices[0].telemetry.gcode_state").is_null());
    c.login(false);assert(c.snapshot(false).find("devices").as_array().empty());
    Cache history;history.login(true);history.cloud(true);
    history.ingest("fixture-a1",R"({"print":{"subtask_name":"oq_one","subtask_id":"actual","gcode_state":"PREPARE"}})","cloud");
    history.ingest("fixture-a1",R"({"print":{"gcode_state":"RUNNING"}})","cloud");
    for(int i=0;i<100;++i)history.ingest("fixture-a1",R"({"print":{"gcode_state":"RUNNING","mc_percent":50,"nozzle_temper":230}})","cloud");
    history.ingest("fixture-a1",R"({"print":{"gcode_state":"FINISH","mc_percent":100}})","cloud");
    history.ingest("fixture-a1",R"({"print":{"gcode_state":"IDLE","subtask_name":""}})","cloud");
    auto journal=history.snapshot(false);auto events=journal.find("devices[0].task_events").as_array();
    assert(events.size()==4);assert(events[1].find("telemetry.gcode_state").as_string()=="RUNNING");
    assert(events[2].find("telemetry.gcode_state").as_string()=="FINISH");
    assert(events[2].find("telemetry.subtask_id").as_string()=="actual");
    assert(events[2].find("state_reported").as_bool());
    assert(!journal.find("devices[0].monitor_epoch").as_string().empty());
    history.ingest("fixture-a1",R"({"print":{"subtask_name":"oq_two","subtask_id":"second"}})","cloud");
    events=history.snapshot(false).find("devices[0].task_events").as_array();
    assert(!events.back().find("state_reported").as_bool());
    assert(events.back().find("telemetry.subtask_id").as_string()=="second");
    auto epoch=journal.find("devices[0].monitor_epoch").as_string();
    history.cloud(false);assert(history.snapshot(false).find("devices[0].task_events").as_array().size()==events.size());
    history.cloud(true);
    for(int i=0;i<100;++i)history.ingest("fixture-a1",i%2?R"({"print":{"gcode_state":"RUNNING"}})":R"({"print":{"gcode_state":"PAUSE"}})","cloud");
    assert(history.snapshot(false).find("devices[0].task_events").as_array().size()==32);
    history.reset();history.ingest("fixture-a1",R"({"print":{"gcode_state":"IDLE"}})","cloud");
    assert(history.snapshot(false).find("devices[0].monitor_epoch").as_string()!=epoch);
    epoch=history.snapshot(false).find("devices[0].monitor_epoch").as_string();
    history.catalog(R"({"devices":[]})");
    history.ingest("fixture-a1",R"({"print":{"gcode_state":"IDLE"}})","cloud");
    assert(history.snapshot(false).find("devices[0].monitor_epoch").as_string()!=epoch);
    std::cout<<"Native cache checks passed\n";
}
