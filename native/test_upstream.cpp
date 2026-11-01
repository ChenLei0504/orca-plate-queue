// Test-only local backend. No sockets, credentials or printer communication.
#include "obn/bambu_networking.hpp"
#include <thread>
#include <chrono>
#include <cassert>
#include <atomic>
#include "obn/json_lite.hpp"
#define API extern "C" __declspec(dllexport)
struct Fake {BBL::OnMessageFn cloud,lan;std::string selected="fixture-a1";};
std::atomic<int> start_calls{0},control_calls{0};
API int fixture_start_calls(){return start_calls;}
API int fixture_control_calls(){return control_calls;}
API void fixture_emit(void* a,std::string json){auto f=static_cast<Fake*>(a);if(f->cloud)f->cloud("fixture-a1",json);}
API void fixture_emit_device(void* a,std::string id,std::string json){auto f=static_cast<Fake*>(a);if(f->cloud)f->cloud(id,json);}
API int bambu_network_add_subscribe(void*,std::vector<std::string> ids){assert(ids.size()<=32);return 0;}
API void* bambu_network_create_agent(std::string){return new Fake;}
API int bambu_network_destroy_agent(void* a){delete static_cast<Fake*>(a);return 0;}
API std::string bambu_network_get_version(){return "02.03.00.99";}
API bool bambu_network_check_debug_consistent(bool){return true;}
API int bambu_network_set_on_message_fn(void* a,BBL::OnMessageFn f){static_cast<Fake*>(a)->cloud=std::move(f);return 0;}
API int bambu_network_set_on_local_message_fn(void* a,BBL::OnMessageFn f){static_cast<Fake*>(a)->lan=std::move(f);return 0;}
API int bambu_network_set_on_server_connected_fn(void*,BBL::OnServerConnectedFn f){if(f)f(0,42);return 0;}
API int bambu_network_set_on_user_login_fn(void*,BBL::OnUserLoginFn f){if(f)f(1,true);return 0;}
API int bambu_network_user_logout(void*,bool){return 0;}
API bool bambu_network_is_user_login(void*){return true;}
API bool bambu_network_is_server_connected(void*){return true;}
API std::string bambu_network_get_user_selected_machine(void* a){return static_cast<Fake*>(a)->selected;}
API int bambu_network_set_user_selected_machine(void* a,std::string id){static_cast<Fake*>(a)->selected=std::move(id);return 0;}
API int bambu_network_get_user_print_info(void*,unsigned int* code,std::string* body){
    std::this_thread::sleep_for(std::chrono::milliseconds(200));
    if(code)*code=200;
    if(body)*body=R"({"devices":[{"dev_id":"fixture-a1","dev_name":"Fixture A1","dev_model_name":"N2S","dev_online":true,"dev_access_code":"NEVER-EXPORTED"},{"dev_id":"fixture-p1","dev_name":"Fixture P1S","dev_model_name":"C12","dev_online":true}]})";
    return 0;
}
API int bambu_network_send_message(void* a,std::string id,std::string message,int qos,int flag){
    if((id!="fixture-a1"&&id!="fixture-p1")||flag!=0)return -80;
    auto f=static_cast<Fake*>(a);
    auto parsed=obn::json::parse(message);
    if(qos==1&&parsed){auto command=parsed->find("print.command").as_string();
        if(command=="stop"||command=="pause"||command=="resume"||command=="skip_objects"){++control_calls;return 0;}}
    if(qos!=0)return -80;
    if(message.find("pushall")!=std::string::npos){
        if(f->cloud)f->cloud(id,R"({"print":{"nozzle_temper":28,"bed_temper":25,"nozzle_diameter":"0.4","gcode_state":"IDLE","hw_switch_state":1,"ams":{"ams_exist_bits":"0"},"vt_tray":{"tray_type":"PETG","tray_color":"EBE6E6FF"}}})");
        return 0;
    }
    if(message.find("get_version")!=std::string::npos)return 0;
    return -90;
}
API int bambu_network_track_enable(void*,bool value){return value?123:456;}
API int bambu_network_start_print(void* a,BBL::PrintParams p,BBL::OnUpdateStatusFn update,BBL::WasCancelledFn cancelled,BBL::OnWaitFn wait){
    ++start_calls;
    assert((p.dev_id=="fixture-a1"||p.dev_id=="fixture-p1")&&p.plate_index==5&&p.task_name==p.project_name&&p.task_name.rfind("oq_",0)==0);
    assert(p.task_bed_leveling&&!p.task_vibration_cali&&!p.task_ext_change_assist);
    auto mapping=obn::json::parse(p.ams_mapping);assert(mapping&&mapping->as_array().size()==10);
    auto rich=obn::json::parse(p.ams_mapping2);assert(rich);
    auto detail=obn::json::parse(p.ams_mapping_info);assert(detail&&detail->as_array().size()==10);
    if(p.task_use_ams){
        assert(mapping->as_array()[8].as_int()==2&&rich->find("[8].ams_id").as_int()==0&&rich->find("[8].slot_id").as_int()==2);
        assert(detail->find("[8].ams").as_int()==2);
        for(size_t i=0;i<10;++i)if(i!=8) {
            assert(rich->as_array()[i].find("ams_id").as_int()==255);
            assert(rich->as_array()[i].find("slot_id").as_int()==255);
        }
    }else{
        for(const auto& item:mapping->as_array())assert(item.as_int()==-1);
        for(size_t i=0;i<10;++i)assert(rich->as_array()[i].find("ams_id").as_int()==255&&rich->as_array()[i].find("slot_id").as_int()==(i==8?0:255));
        for(const auto& item:detail->as_array())assert(item.find("ams").as_int()==-1);
    }
    assert(detail->find("[8].filamentId").as_string()=="GFG99");
    assert(detail->find("[8].filamentType").as_string()=="PETG"&&detail->find("[8].targetColor").as_string()=="EBE6E6FF");
    assert(detail->find("[8].nozzleId").as_int()==1&&detail->find("[0].ams").as_int()==-1);
    if(update)update(1,50,"SHOULD-NOT-EXPORT-RAW-SDK-MESSAGE");
    for(int i=0;i<20;++i){std::this_thread::sleep_for(std::chrono::milliseconds(5));if(cancelled&&cancelled())return -99;}
    if(wait)assert(wait(0,"unused"));
    auto raw=obn::json::Value(obn::json::Object{{"print",obn::json::Object{{"gcode_state","RUNNING"},{"subtask_name",p.project_name},{"subtask_id","fixture-task-1"},{"gcode_start_time","123"},{"vt_tray",obn::json::Object{{"tray_type","PETG"}}}}}}).dump();
    fixture_emit_device(a,p.dev_id,raw);
    return 0;
}
