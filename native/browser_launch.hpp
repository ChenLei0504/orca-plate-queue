// SPDX-License-Identifier: AGPL-3.0-or-later
// Fixed-purpose system-browser launch. No caller-provided URL or command line.
#pragma once
#include <shellapi.h>
#pragma comment(lib, "shell32.lib")

namespace queue_browser {
std::string encode(const std::string& text) {
    static const char* hex = "0123456789ABCDEF";
    std::string out;
    for (unsigned char c : text) {
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
            (c >= '0' && c <= '9') || c == '-' || c == '_' || c == '.' || c == '~') out += c;
        else { out += '%'; out += hex[c >> 4]; out += hex[c & 15]; }
    }
    return out;
}

std::string signin_url(const obn::json::Value& payload) {
    if (!payload.is_object()) return {};
    const auto region = payload.find("region").as_string();
    const auto nonce = payload.find("nonce").as_string();
    const auto& port_value = payload.find("port");
    if ((region != "CN" && region != "US") || nonce.size() != 43 ||
        nonce.find_first_not_of("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_") != std::string::npos ||
        !port_value.is_number()) return {};
    const auto port = port_value.as_int(0);
    if (port < 1 || port > 65535 || port_value.dump() != std::to_string(port)) return {};
    const std::string base = region == "CN" ? "https://bambulab.cn/sign-in" : "https://bambulab.com/sign-in";
    const std::string local = "http://127.0.0.1:" + std::to_string(port) + "/callback/" + nonce;
    const std::string callback = base + "/callback?source=portal&locale=" + (region == "CN" ? "zh-cn" : "en") +
        "&redirect_url=" + encode(local) + "&openBy=suite&from=studio&slicerLoginType=ticket";
    return base + "?from=studio&source=portal&to=" + encode(callback);
}

int open(const std::string& url) {
    if (url.empty()) return -2;
    // All bytes are generated ASCII: no arguments, files, shell commands or URL schemes from UI.
    const std::wstring wide(url.begin(), url.end());
    const auto result = ShellExecuteW(nullptr, L"open", wide.c_str(), nullptr, nullptr, SW_SHOWNORMAL);
    return reinterpret_cast<INT_PTR>(result) > 32 ? 0 : -11;
}
}
