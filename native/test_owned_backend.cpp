// Test only, no sockets or real account state.
#define bambu_network_is_user_login fixture_original_is_user_login
#define bambu_network_user_logout fixture_original_logout
#include "test_upstream.cpp"
#undef bambu_network_user_logout
#undef bambu_network_is_user_login
static bool logged = false;
API int bambu_network_user_logout(void*, bool remote) { assert(!remote); logged = false; return 0; }
API bool bambu_network_is_user_login(void*) { return logged; }
API int bambu_network_set_config_dir(void*, std::string path) { return path.empty() ? -1 : 0; }
API int bambu_network_set_country_code(void*, std::string region) { return region == "CN" || region == "US" ? 0 : -1; }
API int bambu_network_start(void*) { return 0; }
API int bambu_network_connect_server(void*) { return logged ? 0 : -1; }
API int bambu_network_get_my_token(void*, std::string ticket, unsigned int* status, std::string* body) {
    *status = ticket == "fixture-ticket" ? 200 : 401;
    *body = R"({"accessToken":"TEST-SECRET-DO-NOT-EXPOSE","refreshToken":"TEST-REFRESH"})";
    return *status == 200 ? 0 : -1;
}
API int bambu_network_change_user(void*, std::string value) {
    logged = value.find("TEST-SECRET-DO-NOT-EXPOSE") != std::string::npos;
    return logged ? 0 : -1;
}
