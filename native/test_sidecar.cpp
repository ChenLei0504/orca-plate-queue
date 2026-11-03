// SPDX-License-Identifier: AGPL-3.0-or-later
#include "queue_provider_api.h"
#include <atomic>
#include <chrono>
#include <cstring>
#include <future>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
void check(bool ok,const char* message) {if(!ok)throw std::runtime_error(message);}
struct FakeHost {
    std::string received;
    unsigned commands=0;
    bool invalid=false,missing_nul=false,throws=false,block=false;
    std::promise<void> entered,release;
    std::shared_future<void> released=release.get_future().share();
};
int32_t OQ_CALL snapshot(void* context,char* out,uint32_t capacity) {
    auto& host=*static_cast<FakeHost*>(context);
    if(host.throws)throw std::runtime_error("fake error");
    if(host.invalid)return OQ_SNAPSHOT_MAX+1;
    if(host.block){host.entered.set_value();host.released.wait();}
    const char* text="{\"protocol\":1,\"origin\":\"orca-native-queue\",\"attached\":true,\"cloud_session_reused\":true,\"devices\":[]}";
    auto size=static_cast<uint32_t>(std::strlen(text)+1);
    if(out&&capacity>=size){std::memcpy(out,text,size);if(host.missing_nul)out[size-1]='x';}
    return size;
}
int32_t OQ_CALL refresh(void*) {return 1;}
int32_t OQ_CALL command(void* context,const char* bytes,uint32_t size) {
    auto& host=*static_cast<FakeHost*>(context);host.received.assign(bytes,size);++host.commands;return 0;
}
OrcaQueueProviderV1 contract(FakeHost& host) {
    OrcaQueueProviderV1 p{};p.struct_size=sizeof(p);p.abi_version=1;p.queue_contract_version=1;
    p.material_mapping_revision=2;p.context=&host;p.snapshot=snapshot;p.refresh=refresh;p.command=command;return p;
}
int main() {
 try {
    check(obn_queue_abi_version_v1()==1,"consumer ABI");
    check(obn_queue_material_revision_v1()==0&&obn_queue_refresh_v1()==-1,"disconnected capabilities");
    auto n=obn_queue_snapshot_v1(nullptr,0);std::vector<char> out(n);
    check(obn_queue_snapshot_v1(out.data(),n)==n&&std::string(out.data()).find("\"attached\":false")!=std::string::npos,"must not fake attachment");
    check(obn_queue_command_v1("{}",2)==-1,"disconnected command");
    FakeHost host;auto p=contract(host);uint64_t token=99;
    auto bad=p;bad.abi_version=2;check(orca_queue_register_provider_v1(&bad,&token)==-2&&token==0,"ABI mismatch");
    bad=p;bad.struct_size=8;check(orca_queue_register_provider_v1(&bad,&token)==-2,"short structure");
    bad=p;bad.material_mapping_revision=1;check(orca_queue_register_provider_v1(&bad,&token)==-2,"material contract");
    bad=p;bad.queue_contract_version=2;check(orca_queue_register_provider_v1(&bad,&token)==-2,"queue contract");
    bad=p;bad.command=nullptr;check(orca_queue_register_provider_v1(&bad,&token)==-2,"missing function");
    bad=p;bad.reserved[0]=1;check(orca_queue_register_provider_v1(&bad,&token)==-2,"reserved contract");
    check(orca_queue_register_provider_v1(&p,&token)==0&&token,"register");
    uint64_t other=0;check(orca_queue_register_provider_v1(&p,&other)==-10&&!other,"reject second provider");
    check(obn_queue_material_revision_v1()==2&&obn_queue_refresh_v1()==1,"bound capabilities");
    check(orca_queue_unregister_provider_v1(token+1)==-11,"reject stale detach");
    // Mapping/options remain byte-identical, including sparse filaments/external.
    for(const auto* json:{
        R"({"action":"submit","use_ams":true,"ams_mapping":[-1,3],"ams_mapping_info":[{"ams":-1,"filamentType":""},{"ams":3,"filamentType":"PETG","targetColor":"FFFFFF"}],"options":{"bed_leveling":true,"flow_calibration":false,"timelapse":false}})",
        R"({"action":"submit","use_ams":false,"ams_mapping":[-1],"ams_mapping_info":[{"ams":-1,"filamentType":"PLA"}]})"}) {
        check(obn_queue_command_v1(json,static_cast<uint32_t>(std::strlen(json)))==0,"command forwarding");
        check(host.received==json,"material mapping/options changed");
    }
    check(obn_queue_command_v1(nullptr,2)==-2&&obn_queue_command_v1("{}",0)==-2&&obn_queue_command_v1("{}",OQ_COMMAND_MAX+1)==-2&&host.commands==2,"invalid input forwarded");
    n=obn_queue_snapshot_v1(nullptr,0);out.resize(n);
    char tiny='!';check(obn_queue_snapshot_v1(&tiny,1)==n&&tiny=='!',"size probe");
    check(obn_queue_snapshot_v1(out.data(),n)==n&&out.back()==0,"snapshot");
    host.invalid=true;check(obn_queue_snapshot_v1(nullptr,0)==-2,"unbounded output");host.invalid=false;
    host.missing_nul=true;check(obn_queue_snapshot_v1(out.data(),n)==-2,"unterminated output");host.missing_nul=false;
    host.throws=true;check(obn_queue_snapshot_v1(nullptr,0)==-12,"exception containment");host.throws=false;
    // Detachment cannot release host context until a callback has returned.
    host.block=true;
    auto pending=std::async(std::launch::async,[]{return obn_queue_snapshot_v1(nullptr,0);});
    host.entered.get_future().wait();
    std::promise<void> started;
    auto detach=std::async(std::launch::async,[&]{started.set_value();return orca_queue_unregister_provider_v1(token);});
    started.get_future().wait();
    bool waited=detach.wait_for(std::chrono::milliseconds(30))==std::future_status::timeout;
    host.release.set_value();check(pending.get()==n&&detach.get()==0&&waited,"detach did not drain callback");
    check(obn_queue_command_v1("{}",2)==-1&&host.commands==2,"command after detach");
    host.block=false;check(orca_queue_register_provider_v1(&p,&other)==0&&other!=token,"generation");
    check(orca_queue_unregister_provider_v1(token)==-11,"stale token detached new host");
    check(orca_queue_unregister_provider_v1(other)==0,"final detach");
    std::cout<<"PASS independent DLL: contracts, single provider, exact mapping forwarding, limits, detach and callback lifetime\n";
    return 0;
 }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
