// SPDX-License-Identifier: AGPL-3.0-or-later
#pragma once
#include <string>
namespace queue_bridge {
inline std::string canonical_model(const std::string& value) {
    if(value=="N2S"||value=="A1"||value=="Bambu Lab A1")return "N2S";
    if(value=="C12"||value=="P1S"||value=="Bambu Lab P1S")return "C12";
    return {};
}
}
