// SPDX-License-Identifier: AGPL-3.0-or-later
// Private child process: no listening socket, no host DLL replacement.
#define QB_EXPORT extern "C"
#define OQ_PROCESS_HOST 1
#include "owned_cloud.cpp"
#include <iostream>
#include <io.h>
#include <fcntl.h>

int main(int argc, char** argv) {
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
    SetDefaultDllDirectories(LOAD_LIBRARY_SEARCH_APPLICATION_DIR | LOAD_LIBRARY_SEARCH_SYSTEM32);
    if (argc != 2) return 2;
    char* end = nullptr;
    auto parent_id = std::strtoul(argv[1], &end, 10);
    if (!parent_id || !end || *end) return 2;
    auto parent = OpenProcess(SYNCHRONIZE, FALSE, parent_id);
    if (!parent) return 3;
    std::thread([parent] { WaitForSingleObject(parent, INFINITE); ExitProcess(4); }).detach();
    _setmode(_fileno(stdin), _O_BINARY);
    _setmode(_fileno(stdout), _O_BINARY);
    std::string line;
    while (std::cin.good()) {
        line.clear();
        char c;
        while (std::cin.get(c) && c != '\n') {
            if (line.size() >= 65536) return 5;
            line.push_back(c);
        }
        if (line.empty() && !std::cin.good()) break;
        queue_bridge::O reply{{"id", ""}, {"ok", false}, {"code", -2.0}};
        bool finish = false;
        try {
            auto parsed = obn::json::parse(line);
            if (!parsed || !parsed->is_object()) throw std::runtime_error("invalid");
            auto id = parsed->find("id").as_string();
            if (id.empty() || id.size() > 80) throw std::runtime_error("invalid");
            reply["id"] = id;
            const auto action = parsed->find("action").as_string();
            auto payload = parsed->find("payload").dump();
            int code = -2;
            if (action == "open") code = oq_owned_open_v1(payload.data(), static_cast<unsigned int>(payload.size()));
            else if (action == "authenticate") code = oq_owned_auth_v1(payload.data(), static_cast<unsigned int>(payload.size()));
            else if (action == "connect") code = oq_owned_connect_v1();
            else if (action == "refresh") code = oq_owned_refresh_v1();
            else if (action == "command") code = obn_queue_command_v1(payload.data(), static_cast<unsigned int>(payload.size()));
            else if (action == "logout") code = oq_owned_logout_v1();
            else if (action == "close") { code = oq_owned_close_v1(); finish = true; }
            else if (action == "snapshot") {
                std::vector<char> buffer(2 * 1024 * 1024);
                auto n = oq_owned_snapshot_v1(buffer.data(), static_cast<unsigned int>(buffer.size()));
                if (n > 0 && n <= static_cast<int>(buffer.size())) {
                    auto value = obn::json::parse(buffer.data());
                    if (value) { reply["result"] = *value; code = 0; }
                } else code = -1;
            }
            if (!payload.empty()) SecureZeroMemory(payload.data(), payload.size());
            reply["code"] = static_cast<double>(code);
            reply["ok"] = code >= 0;
        } catch (...) { /* Never serialize exception text or auth payloads. */ }
        if (!line.empty()) SecureZeroMemory(line.data(), line.size());
        std::cout << queue_bridge::V(reply).dump() << '\n' << std::flush;
        if (finish) return 0;
    }
    oq_owned_close_v1();
    return 0;
}
