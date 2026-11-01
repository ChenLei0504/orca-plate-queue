"""Exercise every packaged wrapper with a fake SDK; never load real backends."""
from pathlib import Path
import json
import shutil
import subprocess
from build_bridge import ROOT, SOURCE, compiler_environment


def main():
    env=compiler_environment();cl=str(Path(env['PATH'].split(';')[0])/'cl.exe')
    manifest=json.loads((ROOT/'public-build/bridges.json').read_text())
    for series,spec in manifest.items():
        out=ROOT/'public-test'/series;out.mkdir(parents=True,exist_ok=True)
        common=[cl,'/nologo','/std:c++17','/EHsc','/MD','/O2','/utf-8','/W4','/wd4190',
                '/DABI_VERSION=0x'+series.replace('.',''),'/D_ITERATOR_DEBUG_LEVEL=0','/DNOMINMAX',
                '/I'+str(SOURCE/'include'),'/I'+str(ROOT)]
        for name in ('test_host.cpp','test_upstream.cpp'):
            source=(ROOT/name).read_text(encoding='utf8').replace('02.03.00',series).replace('orca_queue_upstream_020300_b14f880.dll',spec['backend'])
            (out/name).write_text(source,encoding='utf8')
        shutil.copyfile(ROOT/'public-build'/series/spec['bridge'],out/spec['bridge'])
        def run(args):subprocess.run(args,cwd=out,env=env,check=True)
        if series=='02.03.00':
            run(common+[str(ROOT/'test_cache.cpp'),str(ROOT/'queue_cache.cpp'),str(SOURCE/'src/json_lite.cpp'),'/Fe:'+str(out/'test_cache.exe')])
            run([str(out/'test_cache.exe')])
            print('PASS bounded callback transition history and epoch checks',flush=True)
            # Compile the pinned production backend's actual cloud mapping serializer.
            # This executable has no Agent, account, HTTP or printer implementation.
            cloud=(SOURCE/'src/cloud_print.cpp').read_text(encoding='utf8')
            mapping_code=cloud[cloud.index('std::string trim('):cloud.index('std::string to_bool(')]
            wire_source='#include <string>\n#include <cassert>\n#include "obn/bambu_networking.hpp"\n#include "obn/json_lite.hpp"\n'+mapping_code+r'''
int main(){
    BBL::PrintParams p{};
    p.ams_mapping="[-1,-1,-1,-1,-1,-1,-1,-1,3,-1]";
    obn::json::Array rich;
    for(int i=0;i<10;++i)rich.emplace_back(obn::json::Object{{"ams_id",i==8?0.0:255.0},{"slot_id",i==8?3.0:255.0}});
    p.ams_mapping2=obn::json::Value(rich).dump();
    auto body=obn::json::parse(ams_mapping2_for_cloud(p));assert(body);
    assert(body->find("[8].amsId").as_int()==0&&body->find("[8].slotId").as_int()==3);
    for(int i=0;i<10;++i)if(i!=8)assert(body->as_array()[i].find("amsId").as_int()==255&&body->as_array()[i].find("slotId").as_int()==255);
    rich[8]=obn::json::Object{{"ams_id",255.0},{"slot_id",0.0}};
    p.ams_mapping2=obn::json::Value(rich).dump();
    body=obn::json::parse(ams_mapping2_for_cloud(p));assert(body);
    assert(body->find("[8].amsId").as_int()==255&&body->find("[8].slotId").as_int()==0);
    assert(body->find("[0].slotId").as_int()==255);
}
'''
            (out/'test_cloud_mapping.cpp').write_text(wire_source,encoding='utf8')
            run(common+[str(out/'test_cloud_mapping.cpp'),str(SOURCE/'src/json_lite.cpp'),'/Fe:'+str(out/'test_cloud_mapping.exe')])
            run([str(out/'test_cloud_mapping.exe')])
            print('PASS production cloud serializer preserves unused versus external markers',flush=True)
        run(common+['/LD',str(out/'test_upstream.cpp'),str(SOURCE/'src/json_lite.cpp'),'/link','/OUT:'+str(out/spec['backend'])])
        run(common+[str(out/'test_host.cpp'),str(SOURCE/'src/json_lite.cpp'),'/Fe:'+str(out/'test_host.exe')])
        run([str(out/'test_host.exe')])
        print('PASS isolated SDK ABI '+series,flush=True)
    print('All packaged native wrappers passed; no real SDK agent or printer used.')


if __name__=='__main__':main()
