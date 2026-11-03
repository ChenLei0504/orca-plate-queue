// SPDX-License-Identifier: AGPL-3.0-or-later
#define OQ_SIDECAR_BUILD
#include "queue_provider_api.h"
#include <cstring>
#include <limits>
#include <mutex>
namespace {
std::mutex gate;
OrcaQueueProviderV1 provider{};
uint64_t generation=0, active=0;
constexpr char disconnected[]="{\"protocol\":1,\"origin\":\"orca-native-queue\",\"cloud_session_reused\":false,\"attached\":false,\"can_submit\":false,\"devices\":[]}";
}
int32_t OQ_CALL orca_queue_register_provider_v1(const OrcaQueueProviderV1* p,uint64_t* token) {
    if(!p||!token)return -2;
    *token=0;
    if(p->struct_size<sizeof(OrcaQueueProviderV1)||p->abi_version!=OQ_PROVIDER_ABI_V1||
       p->queue_contract_version!=OQ_QUEUE_CONTRACT_V1||p->material_mapping_revision!=2||
       !p->snapshot||!p->refresh||!p->command)return -2;
    for(auto value:p->reserved)if(value)return -2;
    std::lock_guard<std::mutex> lock(gate);
    if(active)return -10;
    if(generation==std::numeric_limits<uint64_t>::max())return -2;
    provider=*p;active=++generation;*token=active;return 0;
}
int32_t OQ_CALL orca_queue_unregister_provider_v1(uint64_t token) {
    std::lock_guard<std::mutex> lock(gate);
    if(!active||token!=active)return -11;
    active=0;provider={};return 0;
}
uint32_t OQ_CALL obn_queue_abi_version_v1(void) {return 1;}
uint32_t OQ_CALL obn_queue_material_revision_v1(void) {
    std::lock_guard<std::mutex> lock(gate);return active?provider.material_mapping_revision:0;
}
int32_t OQ_CALL obn_queue_snapshot_v1(char* out,uint32_t capacity) {
    if((!out&&capacity)||capacity>OQ_SNAPSHOT_MAX)return -2;
    std::lock_guard<std::mutex> lock(gate);
    if(!active) {
        if(out&&capacity>=sizeof(disconnected))std::memcpy(out,disconnected,sizeof(disconnected));
        return sizeof(disconnected);
    }
    // A host implementation must not throw across the C ABI. Contain C++
    // exceptions defensively; invalid pointers/access violations are not recoverable.
    try {
        auto size=provider.snapshot(provider.context,out,capacity);
        if(size<=0||static_cast<uint32_t>(size)>OQ_SNAPSHOT_MAX)return -2;
        if(out&&static_cast<uint32_t>(size)<=capacity&&out[size-1]!='\0')return -2;
        return size;
    }catch(...){return -12;}
}
int32_t OQ_CALL obn_queue_refresh_v1(void) {
    std::lock_guard<std::mutex> lock(gate);
    if(!active)return -1;
    try {return provider.refresh(provider.context);}catch(...){return -12;}
}
int32_t OQ_CALL obn_queue_command_v1(const char* bytes,uint32_t length) {
    if(!bytes||!length||length>OQ_COMMAND_MAX)return -2;
    std::lock_guard<std::mutex> lock(gate);
    if(!active)return -1;
    // The host owns JSON validation, identity/freshness checks and idempotency.
    // No transformation of print options or AMS/external-spool mapping here.
    try {return provider.command(provider.context,bytes,length);}catch(...){return -12;}
}
