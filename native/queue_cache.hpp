// SPDX-License-Identifier: AGPL-3.0-or-later
#pragma once
#include "obn/json_lite.hpp"
#include <chrono>
#include <map>
#include <mutex>
#include <string>
#include <deque>

namespace queue_bridge {
using V = obn::json::Value;
using O = obn::json::Object;
using A = obn::json::Array;
using Clock = std::chrono::steady_clock;
struct TaskEvent {unsigned long long sequence;Clock::time_point received;bool reported;O status;std::string signature;};

struct Device {
    std::string id, name, model, source, monitor_epoch;
    bool cloud_online = false;
    bool seen_state = false;
    Clock::time_point updated{};
    V nozzle;
    O status;
    std::map<std::string, O> trays;
    O external;
    bool ams_known = false;
    V ams_bits, tray_bits, hw_switch, tray_now;
    unsigned long long messages = 0;
    unsigned long long state_event = 0;
    double wire_time = 0;
    Clock::time_point state_updated{};
    unsigned long long task_sequence=0;
    std::deque<TaskEvent> task_events;
};

class Cache {
    mutable std::mutex mu_;
    std::map<std::string, Device> devices_;
    std::string selected_;
    bool cloud_ = false;
    bool logged_in_ = false;
    std::string refresh_error_;
    std::string epoch_;
public:
    Cache();
    void reset();
    void cloud(bool connected);
    void login(bool logged_in);
    void select(const std::string& id);
    void catalog(const std::string& json);
    void ingest(const std::string& id, const std::string& json, const std::string& source);
    void refresh_error(const std::string& error);
    V snapshot(bool refreshing) const;
    std::string selected_a1() const;
};
}
