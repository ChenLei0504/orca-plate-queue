// SDK ABI boundary test, running against test_upstream.cpp only.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include "obn/bambu_networking.hpp"
#include "obn/json_lite.hpp"
#include <cassert>
#include <chrono>
#include <iostream>
#include <thread>
#include <fstream>
#include <atomic>

template<class F> F fn(HMODULE h,const char* name){auto p=GetProcAddress(h,name);assert(p);return reinterpret_cast<F>(p);}
int main(){
    auto h=LoadLibraryW(L"bambu_networking_02.03.00.dll");assert(h);
    auto version=fn<std::string(__cdecl*)()>(h,"bambu_network_get_version")();assert(version=="02.03.00.99");
    auto agent=fn<void*(__cdecl*)(std::string)>(h,"bambu_network_create_agent")("fixture");assert(agent);
    std::atomic<int> callbacks{0};
    fn<int(__cdecl*)(void*,BBL::OnMessageFn)>(h,"bambu_network_set_on_message_fn")(agent,[&](std::string id,std::string raw){assert(id=="fixture-a1"||id=="fixture-p1");assert(raw.find("PETG")!=std::string::npos);++callbacks;});
    fn<int(__cdecl*)(void*,BBL::OnServerConnectedFn)>(h,"bambu_network_set_on_server_connected_fn")(agent,[&](int status,int reason){assert(status==0&&reason==42);++callbacks;});
    fn<int(__cdecl*)(void*,BBL::OnUserLoginFn)>(h,"bambu_network_set_on_user_login_fn")(agent,[&](int online,bool login){assert(online==1&&login);++callbacks;});
    auto snap=fn<int(__cdecl*)(char*,unsigned int)>(h,"obn_queue_snapshot_v1");
    auto snapshot=[&]{auto n=snap(nullptr,0);assert(n>0&&n<2000000);std::string b(n+1024,'\0');auto actual=snap(b.data(),static_cast<unsigned int>(b.size()));assert(actual>0&&actual<=b.size());assert(b[actual-1]=='\0');b.resize(actual-1);return b;};
    auto refresh=fn<int(__cdecl*)()>(h,"obn_queue_refresh_v1");
    auto start=std::chrono::steady_clock::now();assert(refresh()==0);
    assert(std::chrono::steady_clock::now()-start<std::chrono::milliseconds(100));
    assert(refresh()==1);
    for(int i=0;i<100;++i){auto p=obn::json::parse(snapshot());assert(p);if(!p->find("refreshing").as_bool())break;std::this_thread::sleep_for(std::chrono::milliseconds(10));}
    auto raw=snapshot();auto p=obn::json::parse(raw);assert(p);
    assert(p->find("devices[0].slots[0].type").as_string()=="PETG");
    assert(p->find("devices[0].cloud_connected").as_bool());
    assert(raw.find("NEVER-EXPORTED")==std::string::npos);
    assert(callbacks==3);
    auto command=fn<int(__cdecl*)(const char*,unsigned int)>(h,"obn_queue_command_v1");
    using V=obn::json::Value;using O=obn::json::Object;using A=obn::json::Array;
    auto submit=[&](O value){auto raw=V(value).dump();return command(raw.data(),static_cast<unsigned int>(raw.size()));};
    auto record=[&](const std::string& id){auto parsed=obn::json::parse(snapshot());assert(parsed);auto list=parsed->find("commands");for(const auto& value:list.as_array())if(value.find("request_id").as_string()==id)return value;return V();};
    auto wait_record=[&](const std::string& id){for(int i=0;i<200;++i){auto value=record(id);if(value.find("status").as_string()!="working")return value;std::this_thread::sleep_for(std::chrono::milliseconds(5));}assert(false);return V();};
    std::ofstream("fixture.3mf",std::ios::binary)<<"abc";
    O request{{"action","submit"},{"request_id","request_test_0001"},{"device_id","fixture-a1"},{"tag","oq_fixture_0001"},
        {"path","fixture.3mf"},{"sha256","ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"},
        {"plate",5.0},{"ams_mapping",A{V(-1.0),V(-1.0),V(-1.0),V(-1.0),V(-1.0),V(-1.0),V(-1.0),V(-1.0),V(2.0),V(-1.0)}},
        {"use_ams",true},{"options",O{{"bed_leveling",true},{"flow_calibration",false},{"timelapse",false}}}};
    A details;for(int i=0;i<10;++i)details.emplace_back(O{{"ams",i==8?2.0:-1.0},{"targetColor",i==8?"EBE6E6FF":""},{"filamentId",i==8?"GFG99":""},{"filamentType",i==8?"PETG":""}});
    details[8]=O{{"ams",2.0},{"sourceColor","EBE6E6FF"},{"targetColor","EBE6E6FF"},{"filamentId","GFG99"},{"filamentType","PETG"},{"nozzleId",1.0}};
    request["ams_mapping_info"]=details;
    auto mismatch=request;mismatch["ams_mapping_info"]=A{};assert(submit(mismatch)==-2);
    mismatch=request;auto wrong_details=details;wrong_details[8]=O{{"ams",0.0},{"targetColor","EBE6E6FF"},{"filamentId","GFG99"},{"filamentType","PETG"}};mismatch["ams_mapping_info"]=wrong_details;assert(submit(mismatch)==-2);
    mismatch=request;mismatch["use_ams"]=false;assert(submit(mismatch)==-2);
    assert(fn<unsigned int(__cdecl*)()>(h,"obn_queue_material_revision_v1")()==2);
    start=std::chrono::steady_clock::now();assert(submit(request)==0);
    assert(std::chrono::steady_clock::now()-start<std::chrono::milliseconds(100));
    assert(submit(request)==1); // same request is accepted exactly once
    auto different=request;different["tag"]="oq_other_0001";assert(submit(different)==-3);
    auto receipt=wait_record("request_test_0001");assert(receipt.find("status").as_string()=="sent");
    assert(receipt.find("stage").as_int()==1); // upload progress, not a print-finished event
    auto real_backend=GetModuleHandleW(L"orca_queue_upstream_020300_b14f880.dll");assert(real_backend);
    assert(fn<int(__cdecl*)()>(real_backend,"fixture_start_calls")()==1);
    assert(snapshot().find("SHOULD-NOT-EXPORT")==std::string::npos);
    O control{{"request_id","control_test_0001"},{"device_id","fixture-a1"},{"tag","oq_fixture_0001"},
        {"identity",O{{"subtask_id","fixture-task-1"},{"gcode_start_time","123"}}},{"action","skip"},{"objects",A{V(1419.0)}}};
    assert(submit(control)==0);assert(submit(control)==1);
    auto wrong=control;wrong["request_id"]="control_wrong_0001";wrong["identity"]=O{{"subtask_id","other"}};
    assert(submit(wrong)==-8);
    assert(fn<int(__cdecl*)()>(real_backend,"fixture_control_calls")()==1);
    control["request_id"]="control_stop_0001";control["action"]="stop";assert(submit(control)==0);
    assert(fn<int(__cdecl*)()>(real_backend,"fixture_control_calls")()==2);
    auto emit=fn<void(__cdecl*)(void*,std::string)>(real_backend,"fixture_emit");
    emit(agent,R"({"print":{"gcode_state":"FINISH","vt_tray":{"tray_type":"PETG"}}})");
    auto bad=request;bad["request_id"]="request_bad_hash_0001";bad["sha256"]=std::string(64,'0');
    assert(submit(bad)==0);assert(wait_record("request_bad_hash_0001").find("status").as_string()=="failed");
    assert(fn<int(__cdecl*)()>(real_backend,"fixture_start_calls")()==1);
    request["request_id"]="request_cancel_0001";request["tag"]="oq_cancel_0001";assert(submit(request)==0);
    assert(submit(O{{"request_id","cancel_test_0001"},{"action","cancel_submit"},{"target","request_cancel_0001"}})==0);
    assert(wait_record("request_cancel_0001").find("status").as_string()=="failed");
    assert(submit(O{{"action","watch_many"},{"request_id","watch_multi_0001"},{"device_ids",A{V("fixture-a1"),V("fixture-p1")}}})==0);
    assert(submit(O{{"action","watch_many"},{"request_id","watch_wrong_0001"},{"device_ids",A{V("not-in-catalog")}}})==-8);
    std::this_thread::sleep_for(std::chrono::milliseconds(5100));assert(refresh()==0);
    for(int i=0;i<100;++i){auto state=obn::json::parse(snapshot());if(!state->find("refreshing").as_bool())break;std::this_thread::sleep_for(std::chrono::milliseconds(10));}
    p=obn::json::parse(snapshot());assert(p->find("devices[1].model").as_string()=="C12");
    assert(p->find("devices[1].telemetry.gcode_state").as_string()=="IDLE");
    assert(fn<std::string(__cdecl*)(void*)>(h,"bambu_network_get_user_selected_machine")(agent)=="fixture-a1");
    auto second=request;second["request_id"]="request_second_0001";second["device_id"]="fixture-p1";second["tag"]="oq_second_0001";
    auto unsupported=second;unsupported["request_id"]="request_p1_flow_0001";unsupported["options"]=O{{"bed_leveling",true},{"flow_calibration",true},{"timelapse",false}};
    assert(submit(unsupported)==-2);
    assert(submit(second)==0);assert(wait_record("request_second_0001").find("status").as_string()=="sent");
    assert(record("request_second_0001").find("device_id").as_string()=="fixture-p1");
    auto second_control=control;second_control["request_id"]="control_second_0001";second_control["device_id"]="fixture-p1";second_control["tag"]="oq_second_0001";
    assert(submit(second_control)==0);
    second_control["request_id"]="control_cross_0001";second_control["device_id"]="fixture-a1";
    assert(submit(second_control)==-8);
    emit(agent,R"({"print":{"gcode_state":"FINISH","vt_tray":{"tray_type":"PETG"}}})");
    auto external=request;external["request_id"]="request_external_0001";external["tag"]="oq_external_0001";external["use_ams"]=false;
    A external_mapping;auto external_details=details;
    for(int i=0;i<10;++i){external_mapping.emplace_back(-1.0);auto row=external_details[i].as_object();row["ams"]=-1.0;external_details[i]=row;}
    external["ams_mapping"]=external_mapping;external["ams_mapping_info"]=external_details;
    assert(submit(external)==0);assert(wait_record("request_external_0001").find("status").as_string()=="sent");
    char tiny[4]={'a','b','c','d'};assert(snap(tiny,4)>4);assert(tiny[0]=='a'&&tiny[3]=='d');
    assert(fn<int(__cdecl*)(void*,bool)>(h,"bambu_network_track_enable")(agent,true)==123);
    assert(fn<int(__cdecl*)(void*,bool)>(h,"bambu_network_user_logout")(agent,true)==0);
    p=obn::json::parse(snapshot());assert(p->find("devices").as_array().empty());
    assert(fn<int(__cdecl*)(void*)>(h,"bambu_network_destroy_agent")(agent)==0);
    p=obn::json::parse(snapshot());assert(!p->find("attached").as_bool());
    std::cout<<"Native SDK forwarding, callback, snapshot, async refresh and lifecycle checks passed\n";
}
