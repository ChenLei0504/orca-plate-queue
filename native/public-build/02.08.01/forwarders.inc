// Generated from pinned upstream signatures. Do not edit.
QB_EXPORT int bambu_network_add_subscribe(void* agent, std::vector<std::string> dev_list) {
 try { using Fn = int (__cdecl*)(void*, std::vector<std::string>);
 static auto upstream_fn = backend_function<Fn>("bambu_network_add_subscribe");
 return upstream_fn(agent, dev_list); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_bind(void* agent, std::string dev_ip, std::string dev_id, std::string dev_model, std::string sec_link, std::string timezone, bool improved, BBL::OnUpdateStatusFn update_fn) {
 try { using Fn = int (__cdecl*)(void*, std::string, std::string, std::string, std::string, std::string, bool, BBL::OnUpdateStatusFn);
 static auto upstream_fn = backend_function<Fn>("bambu_network_bind");
 return upstream_fn(agent, dev_ip, dev_id, dev_model, sec_link, timezone, improved, update_fn); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_bind_detect(void* agent, std::string dev_ip, std::string sec_link, BBL::detectResult& detect) {
 try { using Fn = int (__cdecl*)(void*, std::string, std::string, BBL::detectResult&);
 static auto upstream_fn = backend_function<Fn>("bambu_network_bind_detect");
 return upstream_fn(agent, dev_ip, sec_link, detect); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT std::string bambu_network_build_login_cmd(void* agent) {
 try { using Fn = std::string (__cdecl*)(void*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_build_login_cmd");
 return upstream_fn(agent); } catch (...) { return {}; }
}

QB_EXPORT std::string bambu_network_build_login_info(void* agent) {
 try { using Fn = std::string (__cdecl*)(void*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_build_login_info");
 return upstream_fn(agent); } catch (...) { return {}; }
}

QB_EXPORT std::string bambu_network_build_logout_cmd(void* agent) {
 try { using Fn = std::string (__cdecl*)(void*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_build_logout_cmd");
 return upstream_fn(agent); } catch (...) { return {}; }
}

QB_EXPORT int bambu_network_change_user(void* agent, std::string user_info) {
 try { using Fn = int (__cdecl*)(void*, std::string);
 static auto upstream_fn = backend_function<Fn>("bambu_network_change_user");
 return upstream_fn(agent, user_info); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT bool bambu_network_check_debug_consistent(bool is_debug) {
 try { using Fn = bool (__cdecl*)(bool);
 static auto upstream_fn = backend_function<Fn>("bambu_network_check_debug_consistent");
 return upstream_fn(is_debug); } catch (...) { return false; }
}

QB_EXPORT int bambu_network_check_user_report(void* agent, int* id, bool* printable) {
 try { using Fn = int (__cdecl*)(void*, int*, bool*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_check_user_report");
 return upstream_fn(agent, id, printable); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_check_user_task_report(void* agent, int* task_id, bool* printable) {
 try { using Fn = int (__cdecl*)(void*, int*, bool*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_check_user_task_report");
 return upstream_fn(agent, task_id, printable); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_connect_printer(void* agent, std::string dev_id, std::string dev_ip, std::string username, std::string password, bool use_ssl) {
 try { using Fn = int (__cdecl*)(void*, std::string, std::string, std::string, std::string, bool);
 static auto upstream_fn = backend_function<Fn>("bambu_network_connect_printer");
 return upstream_fn(agent, dev_id, dev_ip, username, password, use_ssl); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_connect_server(void* agent) {
 try { using Fn = int (__cdecl*)(void*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_connect_server");
 return upstream_fn(agent); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_create_filament_spool(void* agent, std::string request_body, std::string* http_body) {
 try { using Fn = int (__cdecl*)(void*, std::string, std::string*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_create_filament_spool");
 return upstream_fn(agent, request_body, http_body); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_del_rating_picture_oss(void* agent, std::string& config, std::string& pic_oss_path, std::string model_id, int profile_id, unsigned int& http_code, std::string& http_error) {
 try { using Fn = int (__cdecl*)(void*, std::string&, std::string&, std::string, int, unsigned int&, std::string&);
 static auto upstream_fn = backend_function<Fn>("bambu_network_del_rating_picture_oss");
 return upstream_fn(agent, config, pic_oss_path, model_id, profile_id, http_code, http_error); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_del_subscribe(void* agent, std::vector<std::string> dev_list) {
 try { using Fn = int (__cdecl*)(void*, std::vector<std::string>);
 static auto upstream_fn = backend_function<Fn>("bambu_network_del_subscribe");
 return upstream_fn(agent, dev_list); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_delete_filament_spools(void* agent, BBL::FilamentDeleteParams params, std::string* http_body) {
 try { using Fn = int (__cdecl*)(void*, BBL::FilamentDeleteParams, std::string*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_delete_filament_spools");
 return upstream_fn(agent, params, http_body); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_delete_setting(void* agent, std::string setting_id) {
 try { using Fn = int (__cdecl*)(void*, std::string);
 static auto upstream_fn = backend_function<Fn>("bambu_network_delete_setting");
 return upstream_fn(agent, setting_id); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_disconnect_printer(void* agent) {
 try { using Fn = int (__cdecl*)(void*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_disconnect_printer");
 return upstream_fn(agent); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT void bambu_network_enable_multi_machine(void* agent, bool enable) {
 try { using Fn = void (__cdecl*)(void*, bool);
 static auto upstream_fn = backend_function<Fn>("bambu_network_enable_multi_machine");
 upstream_fn(agent, enable); } catch (...) { return; }
}

QB_EXPORT std::string bambu_network_get_bambulab_host(void* agent) {
 try { using Fn = std::string (__cdecl*)(void*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_get_bambulab_host");
 return upstream_fn(agent); } catch (...) { return {}; }
}

QB_EXPORT int bambu_network_get_camera_url(void* agent, std::string dev_id, std::function<void(std::string)> callback) {
 try { using Fn = int (__cdecl*)(void*, std::string, std::function<void(std::string)>);
 static auto upstream_fn = backend_function<Fn>("bambu_network_get_camera_url");
 return upstream_fn(agent, dev_id, callback); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_get_camera_url_for_golive(void* agent, std::string dev_id, std::string sdev_id, std::function<void(std::string)> callback) {
 try { using Fn = int (__cdecl*)(void*, std::string, std::string, std::function<void(std::string)>);
 static auto upstream_fn = backend_function<Fn>("bambu_network_get_camera_url_for_golive");
 return upstream_fn(agent, dev_id, sdev_id, callback); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_get_design_staffpick(void* agent, int offset, int limit, std::function<void(std::string)> cb) {
 try { using Fn = int (__cdecl*)(void*, int, int, std::function<void(std::string)>);
 static auto upstream_fn = backend_function<Fn>("bambu_network_get_design_staffpick");
 return upstream_fn(agent, offset, limit, cb); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_get_filament_config(void* agent, std::string* http_body) {
 try { using Fn = int (__cdecl*)(void*, std::string*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_get_filament_config");
 return upstream_fn(agent, http_body); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_get_filament_spools(void* agent, BBL::FilamentQueryParams params, std::string* http_body) {
 try { using Fn = int (__cdecl*)(void*, BBL::FilamentQueryParams, std::string*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_get_filament_spools");
 return upstream_fn(agent, params, http_body); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_get_hms_snapshot(void* agent, std::string& dev_id, std::string& file_name, std::function<void(std::string, int)> callback) {
 try { using Fn = int (__cdecl*)(void*, std::string&, std::string&, std::function<void(std::string, int)>);
 static auto upstream_fn = backend_function<Fn>("bambu_network_get_hms_snapshot");
 return upstream_fn(agent, dev_id, file_name, callback); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_get_model_instance_id(void* agent, std::string model_id, std::string* instance_id, unsigned int& http_code, std::string& http_error) {
 try { using Fn = int (__cdecl*)(void*, std::string, std::string*, unsigned int&, std::string&);
 static auto upstream_fn = backend_function<Fn>("bambu_network_get_model_instance_id");
 return upstream_fn(agent, model_id, instance_id, http_code, http_error); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_get_model_mall_detail_url(void* agent, std::string* url, std::string id) {
 try { using Fn = int (__cdecl*)(void*, std::string*, std::string);
 static auto upstream_fn = backend_function<Fn>("bambu_network_get_model_mall_detail_url");
 return upstream_fn(agent, url, id); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_get_model_mall_home_url(void* agent, std::string* url) {
 try { using Fn = int (__cdecl*)(void*, std::string*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_get_model_mall_home_url");
 return upstream_fn(agent, url); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_get_model_mall_rating(void* agent, int job_id, std::string& rating_result, unsigned int& http_code, std::string& http_error) {
 try { using Fn = int (__cdecl*)(void*, int, std::string&, unsigned int&, std::string&);
 static auto upstream_fn = backend_function<Fn>("bambu_network_get_model_mall_rating");
 return upstream_fn(agent, job_id, rating_result, http_code, http_error); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_get_model_publish_url(void* agent, std::string* url) {
 try { using Fn = int (__cdecl*)(void*, std::string*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_get_model_publish_url");
 return upstream_fn(agent, url); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_get_model_rating_id(void* agent, std::string model_id, int profile_id, int* rating_id, unsigned int& http_code, std::string& http_error) {
 try { using Fn = int (__cdecl*)(void*, std::string, int, int*, unsigned int&, std::string&);
 static auto upstream_fn = backend_function<Fn>("bambu_network_get_model_rating_id");
 return upstream_fn(agent, model_id, profile_id, rating_id, http_code, http_error); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_get_mw_user_4ulist(void* agent, int seed, int limit, std::function<void(std::string)> cb) {
 try { using Fn = int (__cdecl*)(void*, int, int, std::function<void(std::string)>);
 static auto upstream_fn = backend_function<Fn>("bambu_network_get_mw_user_4ulist");
 return upstream_fn(agent, seed, limit, cb); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_get_mw_user_preference(void* agent, std::function<void(std::string)> cb) {
 try { using Fn = int (__cdecl*)(void*, std::function<void(std::string)>);
 static auto upstream_fn = backend_function<Fn>("bambu_network_get_mw_user_preference");
 return upstream_fn(agent, cb); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_get_my_message(void* agent, int type, int after, int limit, unsigned int* http_code, std::string* http_body) {
 try { using Fn = int (__cdecl*)(void*, int, int, int, unsigned int*, std::string*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_get_my_message");
 return upstream_fn(agent, type, after, limit, http_code, http_body); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_get_my_profile(void* agent, std::string token, unsigned int* http_code, std::string* http_body) {
 try { using Fn = int (__cdecl*)(void*, std::string, unsigned int*, std::string*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_get_my_profile");
 return upstream_fn(agent, token, http_code, http_body); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_get_my_token(void* agent, std::string ticket, unsigned int* http_code, std::string* http_body) {
 try { using Fn = int (__cdecl*)(void*, std::string, unsigned int*, std::string*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_get_my_token");
 return upstream_fn(agent, ticket, http_code, http_body); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_get_oss_config(void* agent, std::string& config, std::string country_code, unsigned int& http_code, std::string& http_error) {
 try { using Fn = int (__cdecl*)(void*, std::string&, std::string, unsigned int&, std::string&);
 static auto upstream_fn = backend_function<Fn>("bambu_network_get_oss_config");
 return upstream_fn(agent, config, country_code, http_code, http_error); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_get_printer_firmware(void* agent, std::string dev_id, unsigned* http_code, std::string* http_body) {
 try { using Fn = int (__cdecl*)(void*, std::string, unsigned*, std::string*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_get_printer_firmware");
 return upstream_fn(agent, dev_id, http_code, http_body); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_get_setting_list(void* agent, std::string bundle_version, BBL::ProgressFn pro_fn, BBL::WasCancelledFn cancel_fn) {
 try { using Fn = int (__cdecl*)(void*, std::string, BBL::ProgressFn, BBL::WasCancelledFn);
 static auto upstream_fn = backend_function<Fn>("bambu_network_get_setting_list");
 return upstream_fn(agent, bundle_version, pro_fn, cancel_fn); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_get_setting_list2(void* agent, std::string bundle_version, BBL::CheckFn chk_fn, BBL::ProgressFn pro_fn, BBL::WasCancelledFn cancel_fn) {
 try { using Fn = int (__cdecl*)(void*, std::string, BBL::CheckFn, BBL::ProgressFn, BBL::WasCancelledFn);
 static auto upstream_fn = backend_function<Fn>("bambu_network_get_setting_list2");
 return upstream_fn(agent, bundle_version, chk_fn, pro_fn, cancel_fn); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_get_slice_info(void* agent, std::string project_id, std::string profile_id, int plate_index, std::string* slice_json) {
 try { using Fn = int (__cdecl*)(void*, std::string, std::string, int, std::string*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_get_slice_info");
 return upstream_fn(agent, project_id, profile_id, plate_index, slice_json); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT std::string bambu_network_get_studio_info_url(void* agent) {
 try { using Fn = std::string (__cdecl*)(void*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_get_studio_info_url");
 return upstream_fn(agent); } catch (...) { return {}; }
}

QB_EXPORT int bambu_network_get_subtask(void* agent, BBLModelTask* task, std::function<void(BBLModelTask*)> cb) {
 try { using Fn = int (__cdecl*)(void*, BBLModelTask*, std::function<void(BBLModelTask*)>);
 static auto upstream_fn = backend_function<Fn>("bambu_network_get_subtask");
 return upstream_fn(agent, task, cb); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_get_subtask_info(void* agent, std::string subtask_id, std::string* task_json, unsigned int* http_code, std::string* http_body) {
 try { using Fn = int (__cdecl*)(void*, std::string, std::string*, unsigned int*, std::string*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_get_subtask_info");
 return upstream_fn(agent, subtask_id, task_json, http_code, http_body); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_get_task_plate_index(void* agent, std::string task_id, int* plate_index) {
 try { using Fn = int (__cdecl*)(void*, std::string, int*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_get_task_plate_index");
 return upstream_fn(agent, task_id, plate_index); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT std::string bambu_network_get_user_avatar(void* agent) {
 try { using Fn = std::string (__cdecl*)(void*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_get_user_avatar");
 return upstream_fn(agent); } catch (...) { return {}; }
}

QB_EXPORT std::string bambu_network_get_user_id(void* agent) {
 try { using Fn = std::string (__cdecl*)(void*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_get_user_id");
 return upstream_fn(agent); } catch (...) { return {}; }
}

QB_EXPORT int bambu_network_get_user_info(void* agent, int* identifier) {
 try { using Fn = int (__cdecl*)(void*, int*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_get_user_info");
 return upstream_fn(agent, identifier); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT std::string bambu_network_get_user_name(void* agent) {
 try { using Fn = std::string (__cdecl*)(void*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_get_user_name");
 return upstream_fn(agent); } catch (...) { return {}; }
}

QB_EXPORT std::string bambu_network_get_user_nickanme(void* agent) {
 try { using Fn = std::string (__cdecl*)(void*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_get_user_nickanme");
 return upstream_fn(agent); } catch (...) { return {}; }
}

QB_EXPORT int bambu_network_get_user_presets(void* agent, std::map<std::string, std::map<std::string, std::string>>* user_presets) {
 try { using Fn = int (__cdecl*)(void*, std::map<std::string, std::map<std::string, std::string>>*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_get_user_presets");
 return upstream_fn(agent, user_presets); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT std::string bambu_network_get_user_selected_machine(void* agent) {
 try { using Fn = std::string (__cdecl*)(void*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_get_user_selected_machine");
 return upstream_fn(agent); } catch (...) { return {}; }
}

QB_EXPORT int bambu_network_get_user_tasks(void* agent, BBL::TaskQueryParams params, std::string* http_body) {
 try { using Fn = int (__cdecl*)(void*, BBL::TaskQueryParams, std::string*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_get_user_tasks");
 return upstream_fn(agent, params, http_body); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT std::string bambu_network_get_version() {
 try { using Fn = std::string (__cdecl*)();
 static auto upstream_fn = backend_function<Fn>("bambu_network_get_version");
 return upstream_fn(); } catch (...) { return {}; }
}

QB_EXPORT int bambu_network_init_log(void* agent) {
 try { using Fn = int (__cdecl*)(void*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_init_log");
 return upstream_fn(agent); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT void bambu_network_install_device_cert(void* agent, std::string dev_id, bool lan_only) {
 try { using Fn = void (__cdecl*)(void*, std::string, bool);
 static auto upstream_fn = backend_function<Fn>("bambu_network_install_device_cert");
 upstream_fn(agent, dev_id, lan_only); } catch (...) { return; }
}

QB_EXPORT bool bambu_network_is_server_connected(void* agent) {
 try { using Fn = bool (__cdecl*)(void*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_is_server_connected");
 return upstream_fn(agent); } catch (...) { return false; }
}

QB_EXPORT bool bambu_network_is_user_login(void* agent) {
 try { using Fn = bool (__cdecl*)(void*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_is_user_login");
 return upstream_fn(agent); } catch (...) { return false; }
}

QB_EXPORT int bambu_network_modify_printer_name(void* agent, std::string dev_id, std::string dev_name) {
 try { using Fn = int (__cdecl*)(void*, std::string, std::string);
 static auto upstream_fn = backend_function<Fn>("bambu_network_modify_printer_name");
 return upstream_fn(agent, dev_id, dev_name); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_ping_bind(void* agent, std::string ping_code) {
 try { using Fn = int (__cdecl*)(void*, std::string);
 static auto upstream_fn = backend_function<Fn>("bambu_network_ping_bind");
 return upstream_fn(agent, ping_code); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_put_model_mall_rating(void* agent, int rating_id, int score, std::string content, std::vector<std::string> images, unsigned int& http_code, std::string& http_error) {
 try { using Fn = int (__cdecl*)(void*, int, int, std::string, std::vector<std::string>, unsigned int&, std::string&);
 static auto upstream_fn = backend_function<Fn>("bambu_network_put_model_mall_rating");
 return upstream_fn(agent, rating_id, score, content, images, http_code, http_error); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_put_rating_picture_oss(void* agent, std::string& config, std::string& pic_oss_path, std::string model_id, int profile_id, unsigned int& http_code, std::string& http_error) {
 try { using Fn = int (__cdecl*)(void*, std::string&, std::string&, std::string, int, unsigned int&, std::string&);
 static auto upstream_fn = backend_function<Fn>("bambu_network_put_rating_picture_oss");
 return upstream_fn(agent, config, pic_oss_path, model_id, profile_id, http_code, http_error); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_put_setting(void* agent, std::string setting_id, std::string name, std::map<std::string, std::string>* values_map, unsigned int* http_code) {
 try { using Fn = int (__cdecl*)(void*, std::string, std::string, std::map<std::string, std::string>*, unsigned int*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_put_setting");
 return upstream_fn(agent, setting_id, name, values_map, http_code); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_query_bind_status(void* agent, std::vector<std::string> query_list, unsigned int* http_code, std::string* http_body) {
 try { using Fn = int (__cdecl*)(void*, std::vector<std::string>, unsigned int*, std::string*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_query_bind_status");
 return upstream_fn(agent, query_list, http_code, http_body); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_refresh_connection(void* agent) {
 try { using Fn = int (__cdecl*)(void*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_refresh_connection");
 return upstream_fn(agent); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_report_consent(void* agent, std::string expand) {
 try { using Fn = int (__cdecl*)(void*, std::string);
 static auto upstream_fn = backend_function<Fn>("bambu_network_report_consent");
 return upstream_fn(agent, expand); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_request_bind_ticket(void* agent, std::string* ticket) {
 try { using Fn = int (__cdecl*)(void*, std::string*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_request_bind_ticket");
 return upstream_fn(agent, ticket); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT std::string bambu_network_request_setting_id(void* agent, std::string name, std::map<std::string, std::string>* values_map, unsigned int* http_code) {
 try { using Fn = std::string (__cdecl*)(void*, std::string, std::map<std::string, std::string>*, unsigned int*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_request_setting_id");
 return upstream_fn(agent, name, values_map, http_code); } catch (...) { return {}; }
}

QB_EXPORT int bambu_network_send_message(void* agent, std::string dev_id, std::string json_str, int qos, int flag) {
 try { using Fn = int (__cdecl*)(void*, std::string, std::string, int, int);
 static auto upstream_fn = backend_function<Fn>("bambu_network_send_message");
 return upstream_fn(agent, dev_id, json_str, qos, flag); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_send_message_to_printer(void* agent, std::string dev_id, std::string json_str, int qos, int flag) {
 try { using Fn = int (__cdecl*)(void*, std::string, std::string, int, int);
 static auto upstream_fn = backend_function<Fn>("bambu_network_send_message_to_printer");
 return upstream_fn(agent, dev_id, json_str, qos, flag); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_set_cert_file(void* agent, std::string folder, std::string filename) {
 try { using Fn = int (__cdecl*)(void*, std::string, std::string);
 static auto upstream_fn = backend_function<Fn>("bambu_network_set_cert_file");
 return upstream_fn(agent, folder, filename); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_set_config_dir(void* agent, std::string config_dir) {
 try { using Fn = int (__cdecl*)(void*, std::string);
 static auto upstream_fn = backend_function<Fn>("bambu_network_set_config_dir");
 return upstream_fn(agent, config_dir); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_set_country_code(void* agent, std::string country_code) {
 try { using Fn = int (__cdecl*)(void*, std::string);
 static auto upstream_fn = backend_function<Fn>("bambu_network_set_country_code");
 return upstream_fn(agent, country_code); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_set_extra_http_header(void* agent, std::map<std::string, std::string> extra_headers) {
 try { using Fn = int (__cdecl*)(void*, std::map<std::string, std::string>);
 static auto upstream_fn = backend_function<Fn>("bambu_network_set_extra_http_header");
 return upstream_fn(agent, extra_headers); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_set_get_country_code_fn(void* agent, BBL::GetCountryCodeFn fn) {
 try { using Fn = int (__cdecl*)(void*, BBL::GetCountryCodeFn);
 static auto upstream_fn = backend_function<Fn>("bambu_network_set_get_country_code_fn");
 return upstream_fn(agent, fn); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_set_on_http_error_fn(void* agent, BBL::OnHttpErrorFn fn) {
 try { using Fn = int (__cdecl*)(void*, BBL::OnHttpErrorFn);
 static auto upstream_fn = backend_function<Fn>("bambu_network_set_on_http_error_fn");
 return upstream_fn(agent, fn); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_set_on_local_connect_fn(void* agent, BBL::OnLocalConnectedFn fn) {
 try { using Fn = int (__cdecl*)(void*, BBL::OnLocalConnectedFn);
 static auto upstream_fn = backend_function<Fn>("bambu_network_set_on_local_connect_fn");
 return upstream_fn(agent, fn); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_set_on_printer_connected_fn(void* agent, BBL::OnPrinterConnectedFn fn) {
 try { using Fn = int (__cdecl*)(void*, BBL::OnPrinterConnectedFn);
 static auto upstream_fn = backend_function<Fn>("bambu_network_set_on_printer_connected_fn");
 return upstream_fn(agent, fn); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_set_on_ssdp_msg_fn(void* agent, BBL::OnMsgArrivedFn fn) {
 try { using Fn = int (__cdecl*)(void*, BBL::OnMsgArrivedFn);
 static auto upstream_fn = backend_function<Fn>("bambu_network_set_on_ssdp_msg_fn");
 return upstream_fn(agent, fn); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_set_on_subscribe_failure_fn(void* agent, BBL::GetSubscribeFailureFn fn) {
 try { using Fn = int (__cdecl*)(void*, BBL::GetSubscribeFailureFn);
 static auto upstream_fn = backend_function<Fn>("bambu_network_set_on_subscribe_failure_fn");
 return upstream_fn(agent, fn); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_set_on_user_message_fn(void* agent, BBL::OnMessageFn fn) {
 try { using Fn = int (__cdecl*)(void*, BBL::OnMessageFn);
 static auto upstream_fn = backend_function<Fn>("bambu_network_set_on_user_message_fn");
 return upstream_fn(agent, fn); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_set_queue_on_main_fn(void* agent, BBL::QueueOnMainFn fn) {
 try { using Fn = int (__cdecl*)(void*, BBL::QueueOnMainFn);
 static auto upstream_fn = backend_function<Fn>("bambu_network_set_queue_on_main_fn");
 return upstream_fn(agent, fn); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_set_server_callback(void* agent, BBL::OnServerErrFn fn) {
 try { using Fn = int (__cdecl*)(void*, BBL::OnServerErrFn);
 static auto upstream_fn = backend_function<Fn>("bambu_network_set_server_callback");
 return upstream_fn(agent, fn); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_start(void* agent) {
 try { using Fn = int (__cdecl*)(void*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_start");
 return upstream_fn(agent); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT bool bambu_network_start_discovery(void* agent, bool start, bool sending) {
 try { using Fn = bool (__cdecl*)(void*, bool, bool);
 static auto upstream_fn = backend_function<Fn>("bambu_network_start_discovery");
 return upstream_fn(agent, start, sending); } catch (...) { return false; }
}

QB_EXPORT int bambu_network_start_local_print(void* agent, BBL::PrintParams params, BBL::OnUpdateStatusFn update_fn, BBL::WasCancelledFn cancel_fn) {
 try { using Fn = int (__cdecl*)(void*, BBL::PrintParams, BBL::OnUpdateStatusFn, BBL::WasCancelledFn);
 static auto upstream_fn = backend_function<Fn>("bambu_network_start_local_print");
 return upstream_fn(agent, params, update_fn, cancel_fn); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_start_local_print_with_record(void* agent, BBL::PrintParams params, BBL::OnUpdateStatusFn update_fn, BBL::WasCancelledFn cancel_fn, BBL::OnWaitFn wait_fn) {
 try { using Fn = int (__cdecl*)(void*, BBL::PrintParams, BBL::OnUpdateStatusFn, BBL::WasCancelledFn, BBL::OnWaitFn);
 static auto upstream_fn = backend_function<Fn>("bambu_network_start_local_print_with_record");
 return upstream_fn(agent, params, update_fn, cancel_fn, wait_fn); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_start_print(void* agent, BBL::PrintParams params, BBL::OnUpdateStatusFn update_fn, BBL::WasCancelledFn cancel_fn, BBL::OnWaitFn wait_fn) {
 try { using Fn = int (__cdecl*)(void*, BBL::PrintParams, BBL::OnUpdateStatusFn, BBL::WasCancelledFn, BBL::OnWaitFn);
 static auto upstream_fn = backend_function<Fn>("bambu_network_start_print");
 return upstream_fn(agent, params, update_fn, cancel_fn, wait_fn); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_start_publish(void* agent, BBL::PublishParams params, BBL::OnUpdateStatusFn update_fn, BBL::WasCancelledFn cancel_fn, std::string* out) {
 try { using Fn = int (__cdecl*)(void*, BBL::PublishParams, BBL::OnUpdateStatusFn, BBL::WasCancelledFn, std::string*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_start_publish");
 return upstream_fn(agent, params, update_fn, cancel_fn, out); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_start_sdcard_print(void* agent, BBL::PrintParams params, BBL::OnUpdateStatusFn update_fn, BBL::WasCancelledFn cancel_fn) {
 try { using Fn = int (__cdecl*)(void*, BBL::PrintParams, BBL::OnUpdateStatusFn, BBL::WasCancelledFn);
 static auto upstream_fn = backend_function<Fn>("bambu_network_start_sdcard_print");
 return upstream_fn(agent, params, update_fn, cancel_fn); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_start_send_gcode_to_sdcard(void* agent, BBL::PrintParams params, BBL::OnUpdateStatusFn update_fn, BBL::WasCancelledFn cancel_fn, BBL::OnWaitFn wait_fn) {
 try { using Fn = int (__cdecl*)(void*, BBL::PrintParams, BBL::OnUpdateStatusFn, BBL::WasCancelledFn, BBL::OnWaitFn);
 static auto upstream_fn = backend_function<Fn>("bambu_network_start_send_gcode_to_sdcard");
 return upstream_fn(agent, params, update_fn, cancel_fn, wait_fn); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_start_subscribe(void* agent, std::string module) {
 try { using Fn = int (__cdecl*)(void*, std::string);
 static auto upstream_fn = backend_function<Fn>("bambu_network_start_subscribe");
 return upstream_fn(agent, module); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_stop_subscribe(void* agent, std::string module) {
 try { using Fn = int (__cdecl*)(void*, std::string);
 static auto upstream_fn = backend_function<Fn>("bambu_network_stop_subscribe");
 return upstream_fn(agent, module); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_sync_ams_filaments(void* agent, BBL::AmsSyncParams params, std::string* http_body) {
 try { using Fn = int (__cdecl*)(void*, BBL::AmsSyncParams, std::string*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_sync_ams_filaments");
 return upstream_fn(agent, params, http_body); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_track_enable(void* agent, bool enable) {
 try { using Fn = int (__cdecl*)(void*, bool);
 static auto upstream_fn = backend_function<Fn>("bambu_network_track_enable");
 return upstream_fn(agent, enable); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_track_event(void* agent, std::string evt_key, std::string content) {
 try { using Fn = int (__cdecl*)(void*, std::string, std::string);
 static auto upstream_fn = backend_function<Fn>("bambu_network_track_event");
 return upstream_fn(agent, evt_key, content); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_track_get_property(void* agent, std::string name, std::string& value, std::string type) {
 try { using Fn = int (__cdecl*)(void*, std::string, std::string&, std::string);
 static auto upstream_fn = backend_function<Fn>("bambu_network_track_get_property");
 return upstream_fn(agent, name, value, type); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_track_header(void* agent, std::string header) {
 try { using Fn = int (__cdecl*)(void*, std::string);
 static auto upstream_fn = backend_function<Fn>("bambu_network_track_header");
 return upstream_fn(agent, header); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_track_remove_files(void* agent) {
 try { using Fn = int (__cdecl*)(void*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_track_remove_files");
 return upstream_fn(agent); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_track_update_property(void* agent, std::string name, std::string value, std::string type) {
 try { using Fn = int (__cdecl*)(void*, std::string, std::string, std::string);
 static auto upstream_fn = backend_function<Fn>("bambu_network_track_update_property");
 return upstream_fn(agent, name, value, type); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_unbind(void* agent, std::string dev_id) {
 try { using Fn = int (__cdecl*)(void*, std::string);
 static auto upstream_fn = backend_function<Fn>("bambu_network_unbind");
 return upstream_fn(agent, dev_id); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_update_cert(void* agent) {
 try { using Fn = int (__cdecl*)(void*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_update_cert");
 return upstream_fn(agent); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int bambu_network_update_filament_spool(void* agent, std::string spool_id, std::string request_body, std::string* http_body) {
 try { using Fn = int (__cdecl*)(void*, std::string, std::string, std::string*);
 static auto upstream_fn = backend_function<Fn>("bambu_network_update_filament_spool");
 return upstream_fn(agent, spool_id, request_body, http_body); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int ft_abi_version() {
 try { using Fn = int (__cdecl*)();
 static auto upstream_fn = backend_function<Fn>("ft_abi_version");
 return upstream_fn(); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT void ft_free(void* p) {
 try { using Fn = void (__cdecl*)(void*);
 static auto upstream_fn = backend_function<Fn>("ft_free");
 upstream_fn(p); } catch (...) { return; }
}

QB_EXPORT ft_err ft_job_cancel(FT_JobHandle* h) {
 try { using Fn = ft_err (__cdecl*)(FT_JobHandle*);
 static auto upstream_fn = backend_function<Fn>("ft_job_cancel");
 return upstream_fn(h); } catch (...) { return static_cast<ft_err>(-1); }
}

QB_EXPORT ft_err ft_job_create(const char* params_json, FT_JobHandle** out) {
 try { using Fn = ft_err (__cdecl*)(const char*, FT_JobHandle**);
 static auto upstream_fn = backend_function<Fn>("ft_job_create");
 return upstream_fn(params_json, out); } catch (...) { return static_cast<ft_err>(-1); }
}

QB_EXPORT ft_err ft_job_get_msg(FT_JobHandle* h, uint32_t timeout_ms, ft_job_msg* out) {
 try { using Fn = ft_err (__cdecl*)(FT_JobHandle*, uint32_t, ft_job_msg*);
 static auto upstream_fn = backend_function<Fn>("ft_job_get_msg");
 return upstream_fn(h, timeout_ms, out); } catch (...) { return static_cast<ft_err>(-1); }
}

QB_EXPORT ft_err ft_job_get_result(FT_JobHandle* h, uint32_t timeout_ms, ft_job_result* out) {
 try { using Fn = ft_err (__cdecl*)(FT_JobHandle*, uint32_t, ft_job_result*);
 static auto upstream_fn = backend_function<Fn>("ft_job_get_result");
 return upstream_fn(h, timeout_ms, out); } catch (...) { return static_cast<ft_err>(-1); }
}

QB_EXPORT void ft_job_msg_destroy(ft_job_msg* m) {
 try { using Fn = void (__cdecl*)(ft_job_msg*);
 static auto upstream_fn = backend_function<Fn>("ft_job_msg_destroy");
 upstream_fn(m); } catch (...) { return; }
}

QB_EXPORT void ft_job_release(FT_JobHandle* h) {
 try { using Fn = void (__cdecl*)(FT_JobHandle*);
 static auto upstream_fn = backend_function<Fn>("ft_job_release");
 upstream_fn(h); } catch (...) { return; }
}

QB_EXPORT void ft_job_result_destroy(ft_job_result* r) {
 try { using Fn = void (__cdecl*)(ft_job_result*);
 static auto upstream_fn = backend_function<Fn>("ft_job_result_destroy");
 upstream_fn(r); } catch (...) { return; }
}

QB_EXPORT void ft_job_retain(FT_JobHandle* h) {
 try { using Fn = void (__cdecl*)(FT_JobHandle*);
 static auto upstream_fn = backend_function<Fn>("ft_job_retain");
 upstream_fn(h); } catch (...) { return; }
}

QB_EXPORT ft_err ft_job_set_msg_cb(FT_JobHandle* h, ft_job_msg_cb cb, void* user) {
 try { using Fn = ft_err (__cdecl*)(FT_JobHandle*, ft_job_msg_cb, void*);
 static auto upstream_fn = backend_function<Fn>("ft_job_set_msg_cb");
 return upstream_fn(h, cb, user); } catch (...) { return static_cast<ft_err>(-1); }
}

QB_EXPORT ft_err ft_job_set_result_cb(FT_JobHandle* h, ft_job_result_cb cb, void* user) {
 try { using Fn = ft_err (__cdecl*)(FT_JobHandle*, ft_job_result_cb, void*);
 static auto upstream_fn = backend_function<Fn>("ft_job_set_result_cb");
 return upstream_fn(h, cb, user); } catch (...) { return static_cast<ft_err>(-1); }
}

QB_EXPORT ft_err ft_job_try_get_msg(FT_JobHandle* h, ft_job_msg* out) {
 try { using Fn = ft_err (__cdecl*)(FT_JobHandle*, ft_job_msg*);
 static auto upstream_fn = backend_function<Fn>("ft_job_try_get_msg");
 return upstream_fn(h, out); } catch (...) { return static_cast<ft_err>(-1); }
}

QB_EXPORT ft_err ft_tunnel_create(const char* url, FT_TunnelHandle** out) {
 try { using Fn = ft_err (__cdecl*)(const char*, FT_TunnelHandle**);
 static auto upstream_fn = backend_function<Fn>("ft_tunnel_create");
 return upstream_fn(url, out); } catch (...) { return static_cast<ft_err>(-1); }
}

QB_EXPORT void ft_tunnel_release(FT_TunnelHandle* h) {
 try { using Fn = void (__cdecl*)(FT_TunnelHandle*);
 static auto upstream_fn = backend_function<Fn>("ft_tunnel_release");
 upstream_fn(h); } catch (...) { return; }
}

QB_EXPORT void ft_tunnel_retain(FT_TunnelHandle* h) {
 try { using Fn = void (__cdecl*)(FT_TunnelHandle*);
 static auto upstream_fn = backend_function<Fn>("ft_tunnel_retain");
 upstream_fn(h); } catch (...) { return; }
}

QB_EXPORT ft_err ft_tunnel_set_status_cb(FT_TunnelHandle* h, ft_tunnel_status_cb cb, void* user) {
 try { using Fn = ft_err (__cdecl*)(FT_TunnelHandle*, ft_tunnel_status_cb, void*);
 static auto upstream_fn = backend_function<Fn>("ft_tunnel_set_status_cb");
 return upstream_fn(h, cb, user); } catch (...) { return static_cast<ft_err>(-1); }
}

QB_EXPORT ft_err ft_tunnel_shutdown(FT_TunnelHandle* h) {
 try { using Fn = ft_err (__cdecl*)(FT_TunnelHandle*);
 static auto upstream_fn = backend_function<Fn>("ft_tunnel_shutdown");
 return upstream_fn(h); } catch (...) { return static_cast<ft_err>(-1); }
}

QB_EXPORT ft_err ft_tunnel_start_connect(FT_TunnelHandle* h, ft_tunnel_connect_cb cb, void* user) {
 try { using Fn = ft_err (__cdecl*)(FT_TunnelHandle*, ft_tunnel_connect_cb, void*);
 static auto upstream_fn = backend_function<Fn>("ft_tunnel_start_connect");
 return upstream_fn(h, cb, user); } catch (...) { return static_cast<ft_err>(-1); }
}

QB_EXPORT ft_err ft_tunnel_start_job(FT_TunnelHandle* th, FT_JobHandle* jh) {
 try { using Fn = ft_err (__cdecl*)(FT_TunnelHandle*, FT_JobHandle*);
 static auto upstream_fn = backend_function<Fn>("ft_tunnel_start_job");
 return upstream_fn(th, jh); } catch (...) { return static_cast<ft_err>(-1); }
}

QB_EXPORT ft_err ft_tunnel_sync_connect(FT_TunnelHandle* h) {
 try { using Fn = ft_err (__cdecl*)(FT_TunnelHandle*);
 static auto upstream_fn = backend_function<Fn>("ft_tunnel_sync_connect");
 return upstream_fn(h); } catch (...) { return static_cast<ft_err>(-1); }
}

QB_EXPORT int obn_ensure_conf_block_cloud(const char* conf_path) {
 try { using Fn = int (__cdecl*)(const char*);
 static auto upstream_fn = backend_function<Fn>("obn_ensure_conf_block_cloud");
 return upstream_fn(conf_path); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT int obn_ensure_conf_fixes(const char* conf_path) {
 try { using Fn = int (__cdecl*)(const char*);
 static auto upstream_fn = backend_function<Fn>("obn_ensure_conf_fixes");
 return upstream_fn(conf_path); } catch (...) { return static_cast<int>(-1); }
}

QB_EXPORT const char* obn_get_lan_camera_url(const char* dev_id) {
 try { using Fn = const char* (__cdecl*)(const char*);
 static auto upstream_fn = backend_function<Fn>("obn_get_lan_camera_url");
 return upstream_fn(dev_id); } catch (...) { return {}; }
}

QB_EXPORT const char* obn_get_lan_serial(const char* ip) {
 try { using Fn = const char* (__cdecl*)(const char*);
 static auto upstream_fn = backend_function<Fn>("obn_get_lan_serial");
 return upstream_fn(ip); } catch (...) { return {}; }
}

QB_EXPORT const char* obn_get_tutk_camera_url(const char* dev_id) {
 try { using Fn = const char* (__cdecl*)(const char*);
 static auto upstream_fn = backend_function<Fn>("obn_get_tutk_camera_url");
 return upstream_fn(dev_id); } catch (...) { return {}; }
}
