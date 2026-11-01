// SPDX-License-Identifier: AGPL-3.0-or-later
#include "queue_cache.hpp"
#include "queue_models.hpp"
#include <algorithm>
#include <cctype>
#include <cmath>
#include <limits>
#include <set>
#include <atomic>

namespace queue_bridge {
namespace {
std::string text(const V& v) {
    if(v.is_string()) return v.as_string().substr(0,256);
    if(v.is_number()) return std::to_string(v.as_int());
    return {};
}
V number(const V& v, double low, double high) {
    double n = std::numeric_limits<double>::quiet_NaN();
    if(v.is_number()) n=v.as_number();
    if(v.is_string()) {
        try { size_t used=0; n=std::stod(v.as_string(),&used); if(used!=v.as_string().size()) return {}; }
        catch(...) { return {}; }
    }
    return std::isfinite(n)&&n>=low&&n<=high ? V(n):V();
}
long long bits(const V& v) {
    if(v.is_number()) return v.as_int(-1);
    if(v.is_string() && !v.as_string().empty()) {
        try { size_t used=0; auto n=std::stoll(v.as_string(),&used,16); return used==v.as_string().size()?n:-1; }
        catch(...) {}
    }
    return -1;
}
void material(O& saved,const V& tray) {
    for(const auto* key: {"tray_type","tray_color","tray_info_idx"}) {
        auto v=tray.find(key);
        if(v.is_string() && v.as_string().size()<=128) saved[key]=v;
    }
}
std::string color(const O& tray) {
    auto it=tray.find("tray_color"); if(it==tray.end())return {};
    auto s=it->second.as_string();
    if(s.size()==6||s.size()==8) {
        if(std::all_of(s.begin(),s.end(),[](unsigned char c){return std::isxdigit(c)!=0;})) return "#"+s;
    }
    return {};
}
std::string string_at(const O& o,const std::string& key) {auto i=o.find(key);return i==o.end()?std::string():i->second.as_string();}
std::string epoch() {
    static std::atomic<unsigned long long> sequence{0};
    return std::to_string(std::chrono::system_clock::now().time_since_epoch().count())+"_"+std::to_string(++sequence);
}
}

Cache::Cache():epoch_(epoch()){}
void Cache::reset() {std::lock_guard<std::mutex> lk(mu_);epoch_=epoch();devices_.clear();selected_.clear();cloud_=false;logged_in_=false;refresh_error_.clear();}
void Cache::cloud(bool connected) {
    std::lock_guard<std::mutex> lk(mu_);cloud_=connected;
    if(!connected) for(auto& item:devices_) {
        auto& d=item.second;d.seen_state=false;d.trays.clear();d.external.clear();d.nozzle=V();d.ams_known=false;
        d.status.clear();d.ams_bits=V();d.tray_bits=V();d.hw_switch=V();d.tray_now=V();
        d.wire_time=0;
    }
}
void Cache::login(bool logged_in) {
    if(!logged_in){reset();return;}
    std::lock_guard<std::mutex> lk(mu_);logged_in_=true;
}
void Cache::select(const std::string& id) {std::lock_guard<std::mutex> lk(mu_);selected_=id;}
void Cache::refresh_error(const std::string& error){std::lock_guard<std::mutex> lk(mu_);refresh_error_=error;}

void Cache::catalog(const std::string& raw) {
    if(raw.size()>2*1024*1024)return;
    auto parsed=obn::json::parse(raw);if(!parsed)return;
    auto list=parsed->find("devices");if(!list.is_array()||list.as_array().size()>100)return;
    std::lock_guard<std::mutex> lk(mu_);
    std::set<std::string> keep;
    for(const auto& value:list.as_array()) {
        auto id=text(value.find("dev_id"));if(id.empty()||id.size()>128)continue;
        auto& device=devices_[id];device.id=id;keep.insert(id);
        if(device.monitor_epoch.empty())device.monitor_epoch=epoch();
        device.name=text(value.find("dev_name"));if(device.name.empty())device.name=id;
        device.model=text(value.find("dev_model_name"));
        auto normalized=canonical_model(device.model);
        if(normalized.empty())normalized=canonical_model(text(value.find("dev_product_name")));
        if(!normalized.empty())device.model=normalized;
        auto online=value.find("dev_online");device.cloud_online=online.is_bool()&&online.as_bool();
        // Metadata can report nozzle size; retain its actual value, never assume 0.4.
        auto nozzle=number(value.find("nozzle_diameter"),.1,2);
        if(!nozzle.is_null())device.nozzle=nozzle;
    }
    for(auto it=devices_.begin();it!=devices_.end();) {
        if(!keep.count(it->first))it=devices_.erase(it);else ++it;
    }
}

void Cache::ingest(const std::string& id,const std::string& raw,const std::string& source) {
    if(id.empty()||id.size()>128||raw.size()>2*1024*1024)return;
    auto parsed=obn::json::parse(raw);if(!parsed)return;
    auto print=parsed->find("print");if(!print.is_object())return;
    std::lock_guard<std::mutex> lk(mu_);
    auto& d=devices_[id];d.id=id;if(d.name.empty())d.name=id;
    if(d.monitor_epoch.empty())d.monitor_epoch=epoch();
    auto timestamp=number(parsed->find("t_utc"),0,1e16);
    if(timestamp.is_null())timestamp=number(print.find("t_utc"),0,1e16);
    if(!timestamp.is_null()&&timestamp.as_number()>0) {
        if(timestamp.as_number()<d.wire_time)return;
        d.wire_time=timestamp.as_number();
    } else if(source=="cloud"&&d.source=="lan"&&d.seen_state&&Clock::now()-d.updated<std::chrono::seconds(8)
              &&print.find("command").as_string()!="skip_objects")return;
    auto name=print.find("subtask_name");
    if(name.is_string()&&!name.as_string().empty()&&name.as_string()!=string_at(d.status,"subtask_name")) {
        // Identity fields from the previous job must never attach to a new title.
        for(const auto* key:{"subtask_id","task_id","project_id","gcode_start_time","gcode_file","s_obj","skip_ack_sequence","skip_ack_result"})d.status.erase(key);
    }
    bool recognized=false;
    for(const auto* key: {"nozzle_temper","bed_temper","nozzle_target_temper","bed_target_temper","mc_percent","print_error","layer_num","total_layer_num"}) {
        auto n=number(print.find(key),0,static_cast<double>(0xffffffffu));
        if(!n.is_null()){d.status[key]=n;recognized=true;}
    }
    auto state=print.find("gcode_state");
    if(state.is_string() && state.as_string().size()<32){d.status["gcode_state"]=state;recognized=true;++d.state_event;d.state_updated=Clock::now();}
    for(const auto* key:{"subtask_id","task_id","project_id","gcode_start_time","subtask_name","gcode_file"}) {
        auto value=print.find(key);
        if(value.is_string()||value.is_number())d.status[key]=V(text(value));
    }
    auto skipped=print.find("s_obj");
    if(skipped.is_array()&&skipped.as_array().size()<=1024) {
        A valid;for(const auto& v:skipped.as_array())if(v.is_number()&&v.as_int()>=0&&v.as_int()<1000000000)valid.push_back(v);
        d.status["s_obj"]=valid;
    }
    auto hms=print.find("hms");
    if(hms.is_array())d.status["hms_count"]=static_cast<double>(hms.as_array().size());
    if(print.find("command").as_string()=="skip_objects") {
        d.status["skip_ack_sequence"]=text(print.find("sequence_id"));
        d.status["skip_ack_result"]=text(print.find("result"));
    }
    auto nozzle=number(print.find("nozzle_diameter"),.1,2);
    if(!nozzle.is_null()){d.nozzle=nozzle;recognized=true;}
    auto hw=number(print.find("hw_switch_state"),0,1);
    if(!hw.is_null()){d.hw_switch=hw;recognized=true;}
    auto ams=print.find("ams");
    if(ams.is_object()) {
        auto now=number(ams.find("tray_now"),0,255);if(!now.is_null()){d.tray_now=now;recognized=true;}
        auto exists=ams.find("ams_exist_bits");if(bits(exists)>=0){d.ams_bits=exists;d.ams_known=true;recognized=true;}
        auto trays=ams.find("tray_exist_bits");if(bits(trays)>=0)d.tray_bits=trays;
        auto units=ams.find("ams");
        if(units.is_array()&&units.as_array().size()<=16)for(const auto& unit:units.as_array()) {
            auto uid=text(unit.find("id"));auto u=number(unit.find("id"),0,15);if(u.is_null())continue;
            auto traylist=unit.find("tray");if(!traylist.is_array()||traylist.as_array().size()>4)continue;
            for(const auto& tray:traylist.as_array()) {
                auto tid=text(tray.find("id"));auto t=number(tray.find("id"),0,3);if(t.is_null())continue;
                auto key="ams/"+uid+"/tray/"+tid;
                auto& target=d.trays[key];target["unit"]=u;target["tray"]=t;material(target,tray);recognized=true;
            }
        }
    }
    auto external=print.find("vt_tray");
    if(external.is_object()){material(d.external,external);recognized=true;}
    if(recognized){d.updated=Clock::now();d.seen_state=true;d.source=source;++d.messages;}
    // Keep transitions, not a stream of temperature or progress samples. Snapshot polling
    // can miss an entire short print; these records retain the actual callback ordering.
    O event;
    for(const auto* key:{"gcode_state","subtask_name","subtask_id","task_id","gcode_start_time","mc_percent","print_error","hms_count"}) {
        auto it=d.status.find(key);if(it!=d.status.end())event[key]=it->second;
    }
    O fingerprint=event;fingerprint.erase("mc_percent");fingerprint.erase("print_error");fingerprint.erase("hms_count");
    auto signature=V(fingerprint).dump();
    const bool reported=state.is_string()&&state.as_string().size()<32;
    bool changed=d.task_events.empty()||d.task_events.back().signature!=signature;
    bool upgrade=reported&&!d.task_events.empty()&&!d.task_events.back().reported;
    if((changed||upgrade)&&event.count("gcode_state")) {
        d.task_events.push_back(TaskEvent{++d.task_sequence,Clock::now(),reported,event,signature});
        while(d.task_events.size()>32)d.task_events.pop_front();
    }
}

std::string Cache::selected_a1() const {
    std::lock_guard<std::mutex> lk(mu_);
    auto it=devices_.find(selected_);
    return it!=devices_.end() && it->second.model=="N2S"?selected_:std::string();
}

V Cache::snapshot(bool refreshing) const {
    std::lock_guard<std::mutex> lk(mu_);A devices;
    for(const auto& pair:devices_) {
        const auto& d=pair.second;
        auto age=d.seen_state?std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now()-d.updated).count():1000000000LL;
        A slots;
        auto ams_mask=bits(d.ams_bits),tray_mask=bits(d.tray_bits);
        for(const auto& item:d.trays) {
            const auto& tray=item.second;int unit=static_cast<int>(tray.at("unit").as_int()),index=static_cast<int>(tray.at("tray").as_int());
            if(ams_mask>=0 && !(ams_mask&(1LL<<unit)))continue;
            V present;
            if(tray_mask>=0)present=V((tray_mask&(1LL<<(unit*4+index)))!=0);
            slots.emplace_back(O{{"id",item.first},{"label","AMS "+std::to_string(unit+1)+" / "+std::to_string(index+1)},
                {"kind","ams"},{"present",present},{"type",string_at(tray,"tray_type")},{"color",color(tray)}});
        }
        if(!d.external.empty()) {
            V present;
            // An attached but empty AMS does not prevent external feeding.
            // 254 is the firmware's external-tray identity; 255 is unknown/unloaded.
            if(!d.hw_switch.is_null()) {
                if(d.hw_switch.as_int()==0)present=V(false);
                else if((!d.tray_now.is_null()&&d.tray_now.as_int()==254)||(d.ams_known&&ams_mask==0))present=V(true);
            }
            slots.emplace_back(O{{"id","external"},{"label","外挂耗材"},{"kind","external"},
                {"present",present},{"type",string_at(d.external,"tray_type")},{"color",color(d.external)}});
        }
        A options;
        if(!canonical_model(d.model).empty()) {options.emplace_back("bed_leveling");options.emplace_back("timelapse");if(d.model!="C11"&&d.model!="C12")options.emplace_back("flow_calibration");}
        A events;
        for(const auto& e:d.task_events)events.emplace_back(O{{"event",static_cast<double>(e.sequence)},
            {"age_ms",static_cast<double>(std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now()-e.received).count())},
            {"state_reported",e.reported},{"telemetry",V(e.status)}});
        devices.emplace_back(O{{"id",d.id},{"name",d.name},{"model",d.model},{"online",d.cloud_online},
            {"cloud_connected",cloud_&&logged_in_},{"nozzle",d.nozzle},{"age_ms",static_cast<double>(age)},
            {"supported_options",options},{"slots",slots},{"telemetry",V(d.status)},{"telemetry_source",d.source},
            {"state_messages",static_cast<double>(d.messages)},{"ams_known",d.ams_known},
            {"state_event",static_cast<double>(d.state_event)},
            {"monitor_epoch",d.monitor_epoch},{"task_sequence",static_cast<double>(d.task_sequence)},{"task_events",events},
            {"state_age_ms",d.state_event?static_cast<double>(std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now()-d.state_updated).count()):1e9},
            {"filament_at_toolhead",d.hw_switch},{"current_tray",d.tray_now}});
    }
    return O{{"protocol",1.0},{"origin","orca-native-queue"},{"cloud_session_reused",true},
        {"devices",devices},{"refreshing",refreshing},{"refresh_error",refresh_error_},
        {"selected_device_id",selected_},{"logged_in",logged_in_},{"cloud_connected",cloud_},
        {"attached",true},{"can_submit",true},{"bridge_version","0.7.0"}};
}
}
