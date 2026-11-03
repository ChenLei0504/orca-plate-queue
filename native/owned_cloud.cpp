// SPDX-License-Identifier: AGPL-3.0-or-later
// Owns an isolated agent. Never installed over Orca networking libraries.
// The process host exposes bounded private-pipe requests, not a public network service.
#define QB_BACKEND_FILENAME L"orca_queue_owned_backend.dll"
#include "queue_bridge.cpp"
#include <sddl.h>
#include <aclapi.h>

namespace {
std::mutex owned_mu;
void* owned_agent = nullptr;
HANDLE owned_storage_lock = INVALID_HANDLE_VALUE;
bool owned_ticket_attempted = false;

bool private_directory(const std::wstring& path) {
    HANDLE token = nullptr;
    if (!OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &token)) return false;
    DWORD size = 0;
    GetTokenInformation(token, TokenUser, nullptr, 0, &size);
    std::vector<char> buffer(size);
    bool ok = GetTokenInformation(token, TokenUser, buffer.data(), size, &size) != 0;
    CloseHandle(token);
    if (!ok) return false;
    LPWSTR sid = nullptr;
    if (!ConvertSidToStringSidW(reinterpret_cast<TOKEN_USER*>(buffer.data())->User.Sid, &sid)) return false;
    std::wstring sddl = L"D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;";
    sddl += sid; sddl += L")"; LocalFree(sid);
    PSECURITY_DESCRIPTOR descriptor = nullptr;
    if (!ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl.c_str(), SDDL_REVISION_1, &descriptor, nullptr)) return false;
    PACL acl = nullptr; BOOL present = FALSE, defaulted = FALSE;
    ok = GetSecurityDescriptorDacl(descriptor, &present, &acl, &defaulted) != 0 && present;
    if (ok) ok = SetNamedSecurityInfoW(const_cast<wchar_t*>(path.c_str()), SE_FILE_OBJECT,
        DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION, nullptr, nullptr, acl, nullptr) == ERROR_SUCCESS;
    LocalFree(descriptor);
    return ok;
}

int write_owned_json(queue_bridge::V value, char* output, unsigned int capacity) {
    auto text = value.dump();
    if (text.size() > 2 * 1024 * 1024) return -2;
    auto needed = static_cast<unsigned int>(text.size() + 1);
    if (output && capacity >= needed) std::memcpy(output, text.c_str(), needed);
    return static_cast<int>(needed);
}
}

QB_EXPORT unsigned int oq_owned_protocol_v1() { return 1; }

QB_EXPORT int oq_owned_open_v1(const char* raw, unsigned int length) {
    std::lock_guard<std::mutex> lock(owned_mu);
    if (owned_agent) return -3;
    if (!raw || !length || length > 65536) return -2;
    try {
        auto parsed = obn::json::parse(std::string(raw, length));
        if (!parsed || !parsed->is_object()) return -2;
        auto path = parsed->find("storage").as_string();
        auto region = parsed->find("region").as_string();
        if (path.size() < 3 || path.size() > 32760 || path.find('\0') != std::string::npos ||
            (region != "CN" && region != "US")) return -2;
        int n = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path.data(), static_cast<int>(path.size()), nullptr, 0);
        if (n <= 0) return -2;
        std::wstring wide(n, L' ');
        MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path.data(), static_cast<int>(path.size()), wide.data(), n);
        const bool drive = wide.size() >= 3 && wide[1] == L':' && (wide[2] == L'\\' || wide[2] == L'/');
        const bool extended = wide.rfind(L"\\\\?\\", 0) == 0;
        if (!drive && !extended) return -2;
        auto attributes = GetFileAttributesW(wide.c_str());
        if (attributes == INVALID_FILE_ATTRIBUTES || !(attributes & FILE_ATTRIBUTE_DIRECTORY) || (attributes & FILE_ATTRIBUTE_REPARSE_POINT)) return -2;
#ifdef OQ_PROCESS_HOST
        // Windows 10 1903+ uses UTF-8 via our EXE manifest. Fail clearly on older
        // hosts instead of passing mangled paths to the SDK's narrow file APIs.
        if (GetACP() != CP_UTF8) return -7;
        if (!private_directory(wide)) return -9;
        // The pinned SDK probes APPDATA/OrcaSlicer for obn.env before agent
        // configuration. Redirect ONLY this child process to its private root.
        // This must happen before LoadLibrary/create_agent, not afterwards.
        if (_putenv_s("APPDATA", path.c_str()) || _putenv_s("OBN_CONFIG_DIR", path.c_str()) ||
            _putenv_s("OBN_LOG_TO_FILE", "0") || _putenv_s("OBN_HTTP_TRACE", "0")) return -9;
#else
        if (!std::all_of(path.begin(), path.end(), [](unsigned char c) { return c >= 32 && c < 127; })) return -7;
#endif
        auto lock_path = wide + L"\\session.lock";
        auto storage_lock = CreateFileW(lock_path.c_str(), GENERIC_READ | GENERIC_WRITE, 0, nullptr, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
        if (storage_lock == INVALID_HANDLE_VALUE) return -10;
        auto a = bambu_network_create_agent(path);
        if (!a) { CloseHandle(storage_lock); return -1; }
        auto fail = [&] { bambu_network_destroy_agent(a); CloseHandle(storage_lock); return -1; };
        if (bambu_network_set_config_dir(a, path) != 0 ||
            bambu_network_set_country_code(a, region) != 0 ||
            bambu_network_set_on_message_fn(a, [](std::string, std::string) {}) != 0 ||
            bambu_network_set_on_server_connected_fn(a, [](int, int) {}) != 0 ||
            bambu_network_set_on_user_login_fn(a, [](int, bool) {}) != 0 ||
            bambu_network_start(a) != 0) return fail();
        owned_agent = a;
        owned_storage_lock = storage_lock;
        owned_ticket_attempted = false;
        // No login, printer subscription, or MQTT command from opening the component.
        return 0;
    } catch (...) { return -1; }
}

QB_EXPORT int oq_owned_ticket_v1(const char* ticket, unsigned int length) {
    std::lock_guard<std::mutex> lock(owned_mu);
    if (!owned_agent) return -1;
    if (!ticket || !length || length > 8192 || std::memchr(ticket, 0, length)) return -2;
    // Authentication is explicitly invoked by the browser callback. Never expose token JSON.
    // Re-authenticate in a fresh agent, so an old account's task cache cannot survive a switch.
    if (owned_ticket_attempted || bambu_network_is_user_login(owned_agent)) return -3;
    owned_ticket_attempted = true;
    try {
        unsigned int code = 0;
        std::string body;
        auto rc = bambu_network_get_my_token(owned_agent, std::string(ticket, length), &code, &body);
        if (rc != 0 || code != 200) {
            if (!body.empty()) SecureZeroMemory(body.data(), body.size());
            return -4;
        }
        auto parsed = obn::json::parse(body);
        if (!parsed || parsed->find("accessToken").as_string().empty()) {
            if (!body.empty()) SecureZeroMemory(body.data(), body.size());
            return -4;
        }
        rc = bambu_network_change_user(owned_agent, body);
        SecureZeroMemory(body.data(), body.size());
        return rc == 0 && bambu_network_is_user_login(owned_agent) ? 0 : -4;
    } catch (...) { return -1; }
}

QB_EXPORT int oq_owned_auth_v1(const char* raw, unsigned int length) {
    std::lock_guard<std::mutex> lock(owned_mu);
    if (!owned_agent || bambu_network_is_user_login(owned_agent)) return -3;
    if (!raw || !length || length > 49152) return -2;
    try {
        std::string body(raw, length);
        auto value = obn::json::parse(body);
        if (!value || !value->is_object() || value->find("accessToken").as_string().empty()) return -2;
        int rc = bambu_network_change_user(owned_agent, body);
        SecureZeroMemory(body.data(), body.size());
        return rc == 0 && bambu_network_is_user_login(owned_agent) ? 0 : -4;
    } catch (...) { return -4; }
}

QB_EXPORT int oq_owned_logout_v1() {
    std::lock_guard<std::mutex> lock(owned_mu);
    if (!owned_agent) return -1;
    // Clear only this component's local session; never revoke a Handy token.
    return bambu_network_user_logout(owned_agent, false);
}

QB_EXPORT int oq_owned_connect_v1() {
    std::lock_guard<std::mutex> lock(owned_mu);
    if (!owned_agent || !bambu_network_is_user_login(owned_agent)) return -1;
    return bambu_network_connect_server(owned_agent);
}

QB_EXPORT int oq_owned_snapshot_v1(char* output, unsigned int capacity) {
    std::lock_guard<std::mutex> lock(owned_mu);
    try {
        auto state = owned_agent ? state_for(owned_agent) : nullptr;
        auto value = state ? state->cache.snapshot(state->refreshing.load()).as_object() : queue_bridge::O{};
        value["protocol"] = 1.0;
        value["origin"] = "orca-owned-cloud";
        value["cloud_session_reused"] = false;
        value["attached"] = state != nullptr;
        const bool logged = owned_agent && bambu_network_is_user_login(owned_agent);
        value["logged_in"] = logged;
#ifdef OQ_PROCESS_HOST
        value["can_submit"] = logged;
        value["material_mapping_ready"] = true;
        value["prototype"] = false;
#else
        value["can_submit"] = false;
        value["material_mapping_ready"] = false;
        value["prototype"] = true;
#endif
        if (state) {
            queue_bridge::A records;
            std::lock_guard<std::mutex> lk(state->command_mu);
            for (const auto& item : state->commands) records.emplace_back(item.second);
            value["commands"] = records;
            value["upload_busy"] = state->commanding.load();
        }
        if (!state) value["devices"] = queue_bridge::A{};
        return write_owned_json(value, output, capacity);
    } catch (...) { return -1; }
}

QB_EXPORT int oq_owned_refresh_v1() {
    std::lock_guard<std::mutex> lock(owned_mu);
    if (!owned_agent) return -1;
    return obn_queue_refresh_v1();
}

QB_EXPORT int oq_owned_close_v1() {
    std::lock_guard<std::mutex> lock(owned_mu);
    if (!owned_agent) return 0;
    auto a = owned_agent;
    owned_agent = nullptr;
    // Destroy only our session. Do not call cloud logout (could revoke a token remotely).
    auto rc = bambu_network_destroy_agent(a);
    if (owned_storage_lock != INVALID_HANDLE_VALUE) CloseHandle(owned_storage_lock);
    owned_storage_lock = INVALID_HANDLE_VALUE;
    return rc;
}
