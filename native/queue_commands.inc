// SPDX-License-Identifier: AGPL-3.0-or-later
// C-only commands. SDK upload is asynchronous; MQTT receipt is not print completion.
namespace {
using queue_bridge::V;using queue_bridge::O;using queue_bridge::A;
std::string required_string(const V& v,const char* key,size_t limit=256) {
    auto s=v.find(key);if(!s.is_string()||s.as_string().empty()||s.as_string().size()>limit)throw std::runtime_error("invalid field");
    return s.as_string();
}
bool safe_token(const std::string& s) {
    return s.size()>=8&&s.size()<=80&&std::all_of(s.begin(),s.end(),[](unsigned char c){return std::isalnum(c)||c=='_';});
}
V queue_device(const std::shared_ptr<AgentState>& state,const std::string& id) {
    auto snapshot=state->cache.snapshot(false);
    auto devices=snapshot.find("devices");
    for(const auto& d:devices.as_array())if(d.find("id").as_string()==id) {
        if(queue_bridge::canonical_model(d.find("model").as_string()).empty()||!d.find("online").as_bool()||!d.find("cloud_connected").as_bool()||d.find("age_ms").as_number(1e9)>15000)break;
        return d;
    }
    throw std::runtime_error("device unavailable");
}
void owned_task(const V& device,const V& request) {
    auto telemetry=device.find("telemetry");
    auto tag=required_string(request,"tag");
    if(!safe_token(tag)||telemetry.find("subtask_name").as_string()!=tag)throw std::runtime_error("task mismatch");
    bool strong=false;
    for(const auto* key:{"subtask_id","task_id","gcode_start_time"}) {
        auto expected=request.find("identity").find(key).as_string();
        if(!expected.empty()&&expected!="0") {
            if(telemetry.find(key).as_string()!=expected)throw std::runtime_error("task changed");
            strong=true;
        }
    }
    if(!strong)throw std::runtime_error("missing task identity");
}
struct LockedAsset {
    HANDLE file=INVALID_HANDLE_VALUE;
    ~LockedAsset(){if(file!=INVALID_HANDLE_VALUE)CloseHandle(file);}
    void open(const std::string& path,const std::string& digest) {
        if(digest.size()!=64)throw std::runtime_error("invalid hash");
        int n=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,path.data(),static_cast<int>(path.size()),nullptr,0);
        if(n<=0)throw std::runtime_error("invalid path");
        std::wstring wide(n,L' ');MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,path.data(),static_cast<int>(path.size()),wide.data(),n);
        file=CreateFileW(wide.c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
        LARGE_INTEGER size{};if(file==INVALID_HANDLE_VALUE||!GetFileSizeEx(file,&size)||size.QuadPart<=0||size.QuadPart>300000000)throw std::runtime_error("asset unavailable");
        HCRYPTPROV provider=0;HCRYPTHASH hash=0;
        if(!CryptAcquireContextW(&provider,nullptr,nullptr,PROV_RSA_AES,CRYPT_VERIFYCONTEXT))throw std::runtime_error("hash unavailable");
        bool ok=CryptCreateHash(provider,CALG_SHA_256,0,0,&hash)!=0;
        char buffer[65536];DWORD got=0;
        while(ok){if(!ReadFile(file,buffer,sizeof(buffer),&got,nullptr)){ok=false;break;}if(!got)break;ok=CryptHashData(hash,reinterpret_cast<BYTE*>(buffer),got,0)!=0;}
        BYTE bytes[32];DWORD count=32;if(ok)ok=CryptGetHashParam(hash,HP_HASHVAL,bytes,&count,0)!=0;
        if(hash)CryptDestroyHash(hash);CryptReleaseContext(provider,0);
        std::string actual;const char* hex="0123456789abcdef";
        if(ok)for(auto b:bytes){actual+=hex[b>>4];actual+=hex[b&15];}
        if(!ok||actual!=digest)throw std::runtime_error("asset changed");
    }
};
void result_record(const std::shared_ptr<AgentState>& state,const std::string& id,int rc) {
    std::lock_guard<std::mutex> lk(state->command_mu);
    auto& record=state->commands[id];record["status"]=rc==0?"sent":"failed";record["code"]=static_cast<double>(rc);
}
}

QB_EXPORT int obn_queue_command_v1(const char* bytes,unsigned int length) {
    try {
        if(!bytes||!length||length>65536)return -2;
        auto parsed=obn::json::parse(std::string(bytes,length));if(!parsed||!parsed->is_object())return -2;
        auto request=*parsed;auto id=required_string(request,"request_id",80),action=required_string(request,"action",24);
        if(!safe_token(id))return -2;
        auto state=unique_state();if(!state||!state->alive)return -1;
        auto payload=request.dump();
        std::unique_lock<std::mutex> lk(state->command_mu);
        if(!state->alive)return -1;
        if(action=="watch"||action=="watch_many") {
            std::vector<std::string> watched;
            if(action=="watch")watched.push_back(required_string(request,"device_id",128));
            else {
                auto ids=request.find("device_ids");if(!ids.is_array()||ids.as_array().size()>32)return -2;
                for(const auto& value:ids.as_array()) {
                    if(!value.is_string()||value.as_string().empty()||value.as_string().size()>128||std::find(watched.begin(),watched.end(),value.as_string())!=watched.end())return -2;
                    watched.push_back(value.as_string());
                }
            }
            auto catalog=state->cache.snapshot(false);auto devices=catalog.find("devices");
            for(const auto& watched_id:watched) {
                bool found=false;
                for(const auto& d:devices.as_array())if(d.find("id").as_string()==watched_id&&!queue_bridge::canonical_model(d.find("model").as_string()).empty())found=true;
                if(!found)return -8;
            }
            state->watched_devices=watched;return 0;
        }
        auto existing=state->payloads.find(id);
        if(existing!=state->payloads.end())return existing->second==payload?1:-3;
        if(action=="cancel_submit") {
            auto target=required_string(request,"target",80);
            if(state->commanding&&state->upload_id==target){state->cancel=true;return 0;}
            return -4;
        }
        if(state->commands.size()>=4096)return -5; // Never evict idempotency receipts during this session.
        auto device_id=required_string(request,"device_id",128);
        auto device=queue_device(state,device_id);
        auto current=device.find("telemetry").find("gcode_state").as_string();
        if(action=="submit") {
            if(state->commanding)return -4;
            if(current!="IDLE"&&current!="FINISH"&&current!="FAILED")return -6;
            if(device.find("state_age_ms").as_number(1e9)>15000)return -6;
            auto path=required_string(request,"path",32760),digest=required_string(request,"sha256",64),tag=required_string(request,"tag",80);
            if(!safe_token(tag)||tag.rfind("oq_",0)!=0)return -2;
            auto index=request.find("plate").as_int();if(index<1||index>10000)return -2;
            auto mapping=request.find("ams_mapping");
            if(!mapping.is_array()||mapping.as_array().empty()||mapping.as_array().size()>128)return -2;
            for(const auto& v:mapping.as_array())if(!v.is_number()||v.as_number()!=v.as_int()||v.as_int()<-1||v.as_int()>63)return -2;
            auto options=request.find("options");
            for(const auto* k:{"bed_leveling","flow_calibration","timelapse"}) {
                if(!options.find(k).is_bool())return -2;
                if(options.find(k).as_bool()) {
                    bool supported=false;
                    for(const auto& option:device.find("supported_options").as_array())if(option.as_string()==k)supported=true;
                    if(!supported)return -2;
                }
            }
            auto use_ams=request.find("use_ams");if(!use_ams.is_bool())return -2;
            auto detail=request.find("ams_mapping_info");
            if(!detail.is_array()||detail.as_array().size()!=mapping.as_array().size())return -2;
            bool mapped=false;
            for(size_t i=0;i<detail.as_array().size();++i) {
                auto row=detail.as_array()[i];auto slot=mapping.as_array()[i].as_int();
                if(!row.is_object()||!row.find("ams").is_number()||row.find("ams").as_number()!=slot)return -2;
                for(const auto* k:{"filamentId","filamentType","targetColor"})
                    if(!row.find(k).is_string()||row.find(k).as_string().size()>256)return -2;
                if(slot>=0){mapped=true;if(row.find("filamentType").as_string().empty())return -2;}
                if(row.find("nozzleId").is_number()&&row.find("nozzleId").as_number()!=0&&row.find("nozzleId").as_number()!=1)return -2;
                if(!use_ams.as_bool()&&slot>=0)return -2;
            }
            if(use_ams.as_bool()&&!mapped)return -2;
            // SDK reopens filename itself: use the Windows ACP representation expected
            // by this pinned build, after an exact round-trip check (never lossy).
            int wn=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,path.data(),static_cast<int>(path.size()),nullptr,0);
            if(wn<=0)return -2;std::wstring wide(wn,L' ');MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,path.data(),static_cast<int>(path.size()),wide.data(),wn);
            BOOL replaced=FALSE;auto encoding=GetACP();auto flags=encoding==CP_UTF8?WC_ERR_INVALID_CHARS:WC_NO_BEST_FIT_CHARS;
            auto substituted=encoding==CP_UTF8?nullptr:&replaced;
            int an=WideCharToMultiByte(encoding,flags,wide.data(),wn,nullptr,0,nullptr,substituted);
            if(an<=0||replaced)return -7;std::string sdk_path(an,' ');WideCharToMultiByte(encoding,flags,wide.data(),wn,sdk_path.data(),an,nullptr,substituted);
            if(replaced)return -7;
            if(state->command_worker.joinable())state->command_worker.join();
            state->payloads[id]=payload;state->commands[id]=O{{"request_id",id},{"device_id",device_id},{"action",action},{"tag",tag},{"status","working"},{"stage",0.0}};
            state->commanding=true;state->cancel=false;state->upload_id=id;
            state->command_worker=std::thread([state,id,request,device_id,path,digest,tag,index,mapping,detail,options,use_ams,sdk_path]{
                int rc=-100;
                try {
                    LockedAsset asset;asset.open(path,digest);
                    auto latest=queue_device(state,device_id);auto s=latest.find("telemetry").find("gcode_state").as_string();
                    if(s!="IDLE"&&s!="FINISH"&&s!="FAILED")throw std::runtime_error("printer became busy");
                    if(!state->alive||state->cancel)throw std::runtime_error("cancelled");
                    BBL::PrintParams p{};p.dev_id=device_id;p.task_name=tag;p.project_name=tag;
                    p.filename=sdk_path;p.config_filename=sdk_path;p.plate_index=static_cast<int>(index);
                    p.ftp_file=tag+".3mf";p.dst_file=p.ftp_file;p.print_type="from_normal";p.connection_type="cloud";
                    p.ams_mapping=mapping.dump();A rich;
                    for(size_t i=0;i<mapping.as_array().size();++i) {
                        auto slot=mapping.as_array()[i].as_int();
                        // Native SelectMachine leaves unused project filaments at 255/255.
                        // 255/0 explicitly means external spool. A sparse plate must not
                        // turn its unused prefix into external-spool selections.
                        bool used=!detail.as_array()[i].find("filamentType").as_string().empty();
                        rich.emplace_back(O{{"ams_id",slot<0?255.0:static_cast<double>(slot/4)},
                            {"slot_id",slot<0?(used?0.0:255.0):static_cast<double>(slot%4)}});
                    }
                    p.ams_mapping2=V(rich).dump();p.task_use_ams=use_ams.as_bool();
                    p.ams_mapping_info=detail.dump();
                    p.task_bed_leveling=options.find("bed_leveling").as_bool();p.task_flow_cali=options.find("flow_calibration").as_bool();p.task_record_timelapse=options.find("timelapse").as_bool();p.task_bed_type="auto";
                    auto bed=request.find("bed_type").as_string();
                    if(bed=="Textured PEI Plate")p.task_bed_type="textured_plate";
                    else if(bed=="Smooth PEI Plate"||bed=="High Temp Plate")p.task_bed_type="hot_plate";
                    else if(bed=="Cool Plate")p.task_bed_type="cool_plate";
                    else if(bed=="Engineering Plate")p.task_bed_type="eng_plate";
                    using StartFn=int(__cdecl*)(void*,BBL::PrintParams,BBL::OnUpdateStatusFn,BBL::WasCancelledFn,BBL::OnWaitFn);
                    rc=backend_function<StartFn>("bambu_network_start_print")(state->agent,p,
                        [state,id](int stage,int code,std::string){std::lock_guard<std::mutex> guard(state->command_mu);state->commands[id]["stage"]=static_cast<double>(stage);state->commands[id]["progress"]=static_cast<double>(code);},
                        [state]{return !state->alive||state->cancel.load();},[](int,std::string){return true;});
                }catch(...){rc=-100;}
                result_record(state,id,rc);state->commanding=false;
            });
            return 0;
        }
        if(action!="stop"&&action!="pause"&&action!="resume"&&action!="skip")return -2;
        owned_task(device,request);
        if(current!="RUNNING"&&current!="PAUSE"&&current!="PREPARE"&&current!="SLICING")return -6;
        O print{{"sequence_id",id},{"command",action=="skip"?"skip_objects":action},{"param",""}};
        if(action=="skip") {
            auto objects=request.find("objects");if(!objects.is_array()||objects.as_array().empty()||objects.as_array().size()>1024)return -2;
            for(const auto& v:objects.as_array())if(!v.is_number()||v.as_number()!=v.as_int()||v.as_int()<0||v.as_int()>999999999)return -2;
            print["obj_list"]=objects;
        }
        state->payloads[id]=payload;state->commands[id]=O{{"request_id",id},{"device_id",device_id},{"action",action},{"status","working"}};
        // send_message is the SDK's non-blocking MQTT enqueue, not an upload.
        // Keep the registry lock through this short enqueue to serialize controls.
        using SendFn=int(__cdecl*)(void*,std::string,std::string,int,int);
        owned_task(queue_device(state,device_id),request);
        auto rc=backend_function<SendFn>("bambu_network_send_message")(state->agent,device_id,V(O{{"print",print}}).dump(),1,0);
        state->commands[id]["status"]=rc==0?"sent":"failed";state->commands[id]["code"]=static_cast<double>(rc);
        return 0;
    }catch(...){return -8;}
}
