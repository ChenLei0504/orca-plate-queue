// SPDX-License-Identifier: AGPL-3.0-or-later
// Typed, normal DLL forwarding layer for Open Bamboo b14f880 / ABI 02.03.00.
// No process injection, memory patching, credential export or second login.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include "obn/bambu_networking.hpp"
#include "queue_cache.hpp"
#include "queue_models.hpp"
#include <atomic>
#include <algorithm>
#include <cctype>
#include <cstring>
#include <functional>
#include <map>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <thread>
#include <vector>
#include <wincrypt.h>
#pragma comment(lib,"advapi32.lib")

// Upstream deliberately exports C names with SDK C++ value types.
#pragma warning(disable:4190)
class BBLModelTask;

#ifndef QB_EXPORT
#define QB_EXPORT extern "C" __declspec(dllexport)
#endif
#ifndef QB_BACKEND_FILENAME
#define QB_BACKEND_FILENAME L"orca_queue_upstream_020300_b14f880.dll"
#endif

namespace {
HMODULE backend_module() {
    static HMODULE module=[] {
        HMODULE self=nullptr;
        if(!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                              reinterpret_cast<LPCWSTR>(&backend_module),&self))return static_cast<HMODULE>(nullptr);
        std::vector<wchar_t> path(32768);
        auto length=GetModuleFileNameW(self,path.data(),static_cast<DWORD>(path.size()));
        if(!length||length>=path.size())return static_cast<HMODULE>(nullptr);
        std::wstring filename(path.data(),length);
        auto slash=filename.find_last_of(L"\\/");if(slash==std::wstring::npos)return static_cast<HMODULE>(nullptr);
        filename.resize(slash+1);filename+=QB_BACKEND_FILENAME;
        return LoadLibraryExW(filename.c_str(),nullptr,LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR|LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
    }();
    return module;
}

template<class F> F backend_function(const char* name) {
    auto module=backend_module();if(!module)throw std::runtime_error("network backend unavailable");
    auto symbol=GetProcAddress(module,name);if(!symbol)throw std::runtime_error("network ABI unavailable");
    return reinterpret_cast<F>(symbol);
}

struct AgentState {
    void* agent=nullptr;
    queue_bridge::Cache cache;
    std::atomic<bool> alive{true},refreshing{false};
    std::mutex worker_mu;
    std::thread worker;
    queue_bridge::Clock::time_point refreshed{};
    std::mutex command_mu;
    std::thread command_worker;
    std::atomic<bool> commanding{false},cancel{false};
    std::map<std::string,queue_bridge::O> commands;
    std::map<std::string,std::string> payloads;
    std::vector<std::string> watched_devices;
    std::string upload_id;
};
struct Registry {std::mutex mu;std::map<void*,std::shared_ptr<AgentState>> agents;};
Registry& registry(){static auto* value=new Registry();return *value;}
std::shared_ptr<AgentState> state_for(void* agent) {
    auto& r=registry();std::lock_guard<std::mutex> lk(r.mu);
    auto it=r.agents.find(agent);return it==r.agents.end()?nullptr:it->second;
}
std::shared_ptr<AgentState> unique_state() {
    auto& r=registry();std::lock_guard<std::mutex> lk(r.mu);
    return r.agents.size()==1?r.agents.begin()->second:nullptr;
}
}

QB_EXPORT void* bambu_network_create_agent(std::string log_dir) {
    try {
        using Fn=void*(__cdecl*)(std::string);
        auto agent=backend_function<Fn>("bambu_network_create_agent")(std::move(log_dir));
        if(agent){auto state=std::make_shared<AgentState>();state->agent=agent;
            auto& r=registry();std::lock_guard<std::mutex> lk(r.mu);r.agents[agent]=state;}
        return agent;
    } catch(...){return nullptr;}
}
QB_EXPORT int bambu_network_destroy_agent(void* agent) {
    try {
        auto state=state_for(agent);
        if(state){state->alive=false;
            state->cancel=true;
            {std::lock_guard<std::mutex> lk(state->command_mu);}
            if(state->command_worker.joinable())state->command_worker.join();
            std::lock_guard<std::mutex> lk(state->worker_mu);
            if(state->worker.joinable())state->worker.join();}
        auto& r=registry();{std::lock_guard<std::mutex> lk(r.mu);r.agents.erase(agent);}
        using Fn=int(__cdecl*)(void*);
        return backend_function<Fn>("bambu_network_destroy_agent")(agent);
    } catch(...){return -1;}
}

QB_EXPORT int bambu_network_set_on_message_fn(void* agent,BBL::OnMessageFn fn) {
    try {
        using Fn=int(__cdecl*)(void*,BBL::OnMessageFn);auto original=backend_function<Fn>("bambu_network_set_on_message_fn");
        auto state=state_for(agent);if(!state||!fn)return original(agent,std::move(fn));
        return original(agent,[state,fn=std::move(fn)](std::string id,std::string json){
            try{if(state->alive)state->cache.ingest(id,json,"cloud");}catch(...){}
            fn(std::move(id),std::move(json));
        });
    }catch(...){return -1;}
}
QB_EXPORT int bambu_network_set_on_local_message_fn(void* agent,BBL::OnMessageFn fn) {
    try {
        using Fn=int(__cdecl*)(void*,BBL::OnMessageFn);auto original=backend_function<Fn>("bambu_network_set_on_local_message_fn");
        auto state=state_for(agent);if(!state||!fn)return original(agent,std::move(fn));
        return original(agent,[state,fn=std::move(fn)](std::string id,std::string json){
            try{if(state->alive)state->cache.ingest(id,json,"lan");}catch(...){}
            fn(std::move(id),std::move(json));
        });
    }catch(...){return -1;}
}
QB_EXPORT int bambu_network_set_on_server_connected_fn(void* agent,BBL::OnServerConnectedFn fn) {
    try {
        using Fn=int(__cdecl*)(void*,BBL::OnServerConnectedFn);auto original=backend_function<Fn>("bambu_network_set_on_server_connected_fn");
        auto state=state_for(agent);if(!state||!fn)return original(agent,std::move(fn));
        return original(agent,[state,fn=std::move(fn)](int code,int reason){
            try{if(state->alive)state->cache.cloud(code==0);}catch(...){}
            fn(code,reason);
        });
    }catch(...){return -1;}
}
QB_EXPORT int bambu_network_set_on_user_login_fn(void* agent,BBL::OnUserLoginFn fn) {
    try {
        using Fn=int(__cdecl*)(void*,BBL::OnUserLoginFn);auto original=backend_function<Fn>("bambu_network_set_on_user_login_fn");
        auto state=state_for(agent);if(!state||!fn)return original(agent,std::move(fn));
        return original(agent,[state,fn=std::move(fn)](int online,bool login){
            try{if(state->alive)state->cache.login(login);}catch(...){}
            fn(online,login);
        });
    }catch(...){return -1;}
}
QB_EXPORT int bambu_network_user_logout(void* agent,bool request) {
    try {
        if(auto state=state_for(agent))state->cache.reset();
        using Fn=int(__cdecl*)(void*,bool);
        return backend_function<Fn>("bambu_network_user_logout")(agent,request);
    }catch(...){return -1;}
}
QB_EXPORT int bambu_network_get_user_print_info(void* agent,unsigned int* code,std::string* body) {
    try {
        using Fn=int(__cdecl*)(void*,unsigned int*,std::string*);
        auto result=backend_function<Fn>("bambu_network_get_user_print_info")(agent,code,body);
        try{if(result==0&&body)if(auto state=state_for(agent))state->cache.catalog(*body);}catch(...){}
        return result;
    }catch(...){return -1;}
}
QB_EXPORT int bambu_network_set_user_selected_machine(void* agent,std::string id) {
    try {
        using Fn=int(__cdecl*)(void*,std::string);
        auto result=backend_function<Fn>("bambu_network_set_user_selected_machine")(agent,id);
        try{if(result==0)if(auto state=state_for(agent))state->cache.select(id);}catch(...){}
        return result;
    }catch(...){return -1;}
}

// C-only, bounded bridge interface called by the queue page in this process.
QB_EXPORT unsigned int obn_queue_abi_version_v1(){return 1;}
QB_EXPORT unsigned int obn_queue_monitor_revision_v1(){return 1;}
QB_EXPORT unsigned int obn_queue_material_revision_v1(){return 2;}
QB_EXPORT int obn_queue_snapshot_v1(char* buffer,unsigned int capacity) {
    try {
        auto state=unique_state();
        queue_bridge::V value=state?state->cache.snapshot(state->refreshing.load()):queue_bridge::V(queue_bridge::O{
            {"protocol",1.0},{"origin","orca-native-queue"},{"cloud_session_reused",true},
            {"attached",false},{"devices",queue_bridge::A{}},{"can_submit",false},
            {"bridge_version","0.6.0"},{"reason","等待 Orca 创建唯一联网实例"}});
        if(state){queue_bridge::A records;std::lock_guard<std::mutex> lk(state->command_mu);
            for(const auto& item:state->commands)records.emplace_back(item.second);
            auto object=value.as_object();object["commands"]=records;object["upload_busy"]=state->commanding.load();value=object;}
        auto json=value.dump();if(json.size()>2*1024*1024)return -2;
        auto needed=static_cast<unsigned int>(json.size()+1);
        if(buffer&&capacity>=needed)std::memcpy(buffer,json.c_str(),needed);
        return static_cast<int>(needed);
    }catch(...){return -1;}
}
QB_EXPORT int obn_queue_refresh_v1() {
    try {
        auto state=unique_state();if(!state||!state->alive)return -1;
        std::lock_guard<std::mutex> lk(state->worker_mu);
        auto now=queue_bridge::Clock::now();
        if(!state->alive)return -1;
        if(state->refreshing || now-state->refreshed<std::chrono::seconds(5))return 1;
        if(state->worker.joinable())state->worker.join();
        state->refreshed=now;state->refreshing=true;
        state->worker=std::thread([state]{
            try {
                using BoolFn=bool(__cdecl*)(void*);
                bool login=backend_function<BoolFn>("bambu_network_is_user_login")(state->agent);
                state->cache.login(login);
                bool cloud=backend_function<BoolFn>("bambu_network_is_server_connected")(state->agent);
                state->cache.cloud(cloud);
                if(!login)state->cache.refresh_error("Bambu Cloud 未登录");
                else {
                    using ListFn=int(__cdecl*)(void*,unsigned int*,std::string*);
                    unsigned int code=0;std::string body;
                    auto rc=backend_function<ListFn>("bambu_network_get_user_print_info")(state->agent,&code,&body);
                    if(rc==0&&code==200){state->cache.catalog(body);state->cache.refresh_error("");}
                    else state->cache.refresh_error("读取云端设备列表失败");
                    using SelectedFn=std::string(__cdecl*)(void*);
                    auto id=backend_function<SelectedFn>("bambu_network_get_user_selected_machine")(state->agent);
                    state->cache.select(id);
                    std::vector<std::string> watched;
                    {std::lock_guard<std::mutex> guard(state->command_mu);watched=state->watched_devices;}
                    if(watched.empty()) {
                        auto catalog=state->cache.snapshot(false);
                        for(const auto& row:catalog.find("devices").as_array())if(row.find("id").as_string()==id&&!queue_bridge::canonical_model(row.find("model").as_string()).empty())watched.push_back(id);
                    }
                    if(!watched.empty()) {
                        using SubscribeFn=int(__cdecl*)(void*,std::vector<std::string>);
                        backend_function<SubscribeFn>("bambu_network_add_subscribe")(state->agent,watched);
                    }
                    for(const auto& watched_id:watched)if(state->alive&&!watched_id.empty()) {
                        using SendFn=int(__cdecl*)(void*,std::string,std::string,int,int);
                        auto send=backend_function<SendFn>("bambu_network_send_message");
                        send(state->agent,watched_id,R"({"pushing":{"sequence_id":"0","command":"pushall","version":1,"push_target":1}})",0,0);
                        if(state->alive)send(state->agent,watched_id,R"({"info":{"sequence_id":"0","command":"get_version"}})",0,0);
                    }
                }
            }catch(...){state->cache.refresh_error("原生设备刷新失败");}
            state->refreshing=false;
        });
        return 0;
    }catch(...){return -1;}
}

// File-transfer definitions mirror upstream's C ABI. Handles remain opaque;
// the bridge never dereferences them or implements file transfer itself.
struct FT_TunnelHandle;
struct FT_JobHandle;
struct ft_job_result {int ec;int resp_ec;const char* json;const void* bin;uint32_t bin_size;};
struct ft_job_msg {int kind;const char* json;};
enum ft_err {FT_OK=0,FT_EINVAL=-1,FT_ESTATE=-2,FT_EIO=-3,FT_ETIMEOUT=-4,FT_ECANCELLED=-5,FT_EXCEPTION=-6,FT_EUNKNOWN=-128};
using ft_tunnel_connect_cb=void(*)(void*,int,int,const char*);
using ft_tunnel_status_cb=void(*)(void*,int,int,int,const char*);
using ft_job_result_cb=void(*)(void*,ft_job_result);
using ft_job_msg_cb=void(*)(void*,ft_job_msg);

#include "forwarders.inc"

#include "queue_commands.inc"
