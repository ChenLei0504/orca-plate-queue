// SPDX-License-Identifier: AGPL-3.0-or-later
// Proposed host-to-queue API. Not an API currently supplied by Orca/Open Bamboo.
#pragma once
#include <stdint.h>
#ifdef _WIN32
#define OQ_CALL __cdecl
#ifdef OQ_SIDECAR_BUILD
#define OQ_API __declspec(dllexport)
#else
#define OQ_API __declspec(dllimport)
#endif
#else
#define OQ_CALL
#define OQ_API __attribute__((visibility("default")))
#endif
#ifdef __cplusplus
extern "C" {
#endif
#define OQ_PROVIDER_ABI_V1 1u
#define OQ_QUEUE_CONTRACT_V1 1u
#define OQ_SNAPSHOT_MAX (2u * 1024u * 1024u + 1u)
#define OQ_COMMAND_MAX 65536u
// C ABI, native pointer alignment, no C++ containers/allocators across the DLL.
// Callbacks copy input before returning and must not reenter this API.
// snapshot returns required bytes INCLUDING NUL; never partially writes.
// refresh/command enqueue work, never block on network, upload or host UI.
typedef struct OrcaQueueProviderV1 {
    uint32_t struct_size;
    uint32_t abi_version;
    uint32_t queue_contract_version;
    uint32_t material_mapping_revision; // exactly 2; see provider-contract.md
    void* context; // owned by host, opaque to sidecar
    int32_t (OQ_CALL *snapshot)(void*, char*, uint32_t);
    int32_t (OQ_CALL *refresh)(void*);
    int32_t (OQ_CALL *command)(void*, const char*, uint32_t);
    uint64_t reserved[4]; // must be zero
} OrcaQueueProviderV1;
// Registration: 0 success, -2 invalid contract, -10 already attached.
// unregister: 0 success, -11 invalid/stale token. No callback is in flight
// after successful unregister. Host must drain its own asynchronous work.
OQ_API int32_t OQ_CALL orca_queue_register_provider_v1(const OrcaQueueProviderV1*, uint64_t* token);
OQ_API int32_t OQ_CALL orca_queue_unregister_provider_v1(uint64_t token);
// Existing consumer ABI, so queue scheduling and material mapping are unchanged.
OQ_API uint32_t OQ_CALL obn_queue_abi_version_v1(void);
OQ_API uint32_t OQ_CALL obn_queue_material_revision_v1(void);
OQ_API int32_t OQ_CALL obn_queue_snapshot_v1(char*, uint32_t);
OQ_API int32_t OQ_CALL obn_queue_refresh_v1(void);
OQ_API int32_t OQ_CALL obn_queue_command_v1(const char*, uint32_t);
#ifdef __cplusplus
}
#endif
