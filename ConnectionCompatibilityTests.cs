// Offline compatibility scenarios. Candidate DLL bytes are never loaded.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Runtime.Serialization.Json;

static class ConnectionCompatibilityTests {
    static void Assert(bool ok,string text) { if(!ok)throw new Exception(text); }
    static void Fails(Action action) { bool failed=false;try{action();}catch{failed=true;}Assert(failed,"Expected compatibility rejection"); }
    static void U16(byte[] b,int at,ushort v) { Array.Copy(BitConverter.GetBytes(v),0,b,at,2); }
    static void U32(byte[] b,int at,uint v) { Array.Copy(BitConverter.GetBytes(v),0,b,at,4); }
    static void Core(string path,ComponentSeries spec,byte revision,string extra=null,string abi=null) {
        var names=spec.exports.ToList();if(extra!=null)names.Add(extra);names.Sort(StringComparer.Ordinal);
        byte[] b=new byte[32768];U16(b,0,0x5a4d);U32(b,60,0x80);U32(b,0x80,0x4550);U16(b,0x84,0x8664);U16(b,0x86,1);U16(b,0x94,240);U16(b,0x96,0x2000);
        int opt=0x98;U16(b,opt,0x20b);U32(b,opt+108,16);U32(b,opt+112,0x1000);U32(b,opt+116,0x6000);
        int section=opt+240;U32(b,section+8,0x6000);U32(b,section+12,0x1000);U32(b,section+16,0x6000);U32(b,section+20,0x200);
        U32(b,0x200+20,(uint)names.Count);U32(b,0x200+24,(uint)names.Count);U32(b,0x200+28,0x1100);U32(b,0x200+32,0x1500);U32(b,0x200+36,0x1900);
        int pos=0xf00;
        for(int i=0;i<names.Count;i++) {
            U32(b,0x300+i*4,0x5000);U32(b,0x700+i*4,(uint)(pos-0x200+0x1000));U16(b,0xb00+i*2,(ushort)i);
            byte[] name=Encoding.ASCII.GetBytes(names[i]+"\0");Array.Copy(name,0,b,pos,name.Length);pos+=name.Length;
        }
        byte[] text=Encoding.ASCII.GetBytes("open-bamboo-networking\0"+(abi??spec.abi)+".99\0");Array.Copy(text,0,b,0x6000,text.Length);b[0x6100]=revision;
        Directory.CreateDirectory(Path.GetDirectoryName(path));File.WriteAllBytes(path,b);
    }
    static ComponentManifest Manifest(string bundle) { return new ConnectionManager(bundle,Path.Combine(bundle,"unused"),new FixtureFiles()).Verify(); }
    static void Seed(string data,ComponentManifest m,byte revision) {
        foreach(var spec in m.series.Values)Core(Path.Combine(data,"plugins",spec.bridge),spec,revision);
    }
    public static string FixtureBundle(string root) {
        string bundle=Path.Combine(root,"adaptive-fixture");Directory.CreateDirectory(Path.Combine(bundle,"bin"));
        var m=new ComponentManifest{schema=2,version="offline-fixture",files=new Dictionary<string,ComponentEntry>(),series=new Dictionary<string,ComponentSeries>()};
        foreach(string key in new[]{"02.03.00","02.08.01","02.08.04","default"}) {
            string abi=key=="default"?"02.08.04":key;
            var spec=new ComponentSeries{abi=abi,bridge=key=="default"?"bambu_networking.dll":"bambu_networking_"+key+".dll",backend="orca_queue_backend_"+key.Replace(".","")+".dll",
                exports=new[]{"bambu_network_get_version","bambu_network_create_agent","bambu_network_start_print","obn_ensure_conf_fixes"},compatible_bridge_hashes=new string[0]};
            string path=Path.Combine(bundle,"bin",spec.bridge);Core(path,spec,0,"obn_queue_abi_version_v1");
            m.series[key]=spec;m.files[spec.bridge]=new ComponentEntry{role="bridge",sha256=ConnectionManager.Hash(path)};
        }
        using(var stream=File.Create(Path.Combine(bundle,"components.json")))new DataContractJsonSerializer(typeof(ComponentManifest),new DataContractJsonSerializerSettings{UseSimpleDictionaryFormat=true}).WriteObject(stream,m);
        return bundle;
    }
    public static void RealCores(string root,string bundle,string upstream,string legacy) {
        var m=Manifest(bundle);if(m.schema!=2)throw new Exception("Expected adaptive manifest");
        string data=Path.Combine(root,"real-core-static-only");Directory.CreateDirectory(Path.Combine(data,"plugins"));
        foreach(var spec in m.series.Values) {
            string name=spec.abi=="02.08.04"?"bambu_networking.dll":"bambu_networking_"+spec.abi+".dll";
            File.Copy(Path.Combine(upstream,"bin--win_x64--"+name),Path.Combine(data,"plugins",spec.bridge));
        }
        var hashes=m.series.Values.ToDictionary(s=>s.bridge,s=>ConnectionManager.Hash(Path.Combine(data,"plugins",s.bridge)));
        var manager=new ConnectionManager(bundle,data,new FixtureFiles());manager.InstallReviewed(manager.Check());
        foreach(var spec in m.series.Values)Assert(ConnectionManager.Hash(Path.Combine(data,"plugins",spec.backend))==hashes[spec.bridge],"Actual upstream core changed");
        manager.Restore();
        foreach(var spec in m.series.Values)Assert(ConnectionManager.Hash(Path.Combine(data,"plugins",spec.bridge))==hashes[spec.bridge],"Actual core restore changed bytes");
        data=Path.Combine(root,"legacy-migration-static-only");Directory.CreateDirectory(Path.Combine(data,"plugins"));
        foreach(var spec in m.series.Values) {
            string folder=Path.Combine(legacy,spec.abi);
            File.Copy(Path.Combine(folder,"bambu_networking_"+spec.abi+".dll"),Path.Combine(data,"plugins",spec.bridge));
            string core=Path.Combine(data,"plugins",spec.legacy_backend);
            if(!File.Exists(core))File.Copy(Path.Combine(folder,spec.legacy_backend),core);
        }
        hashes=m.series.Values.ToDictionary(s=>s.bridge,s=>ConnectionManager.Hash(Path.Combine(data,"plugins",s.bridge)));
        manager=new ConnectionManager(bundle,data,new FixtureFiles());manager.Install();Assert(manager.Check().changes.Count==0,"Legacy migration failed");manager.Restore();
        foreach(var spec in m.series.Values)Assert(ConnectionManager.Hash(Path.Combine(data,"plugins",spec.bridge))==hashes[spec.bridge],"Legacy restore failed");
        Console.WriteLine("PASS current upstream binaries and legacy migration: static inspection, exact-byte core preservation and restore; no DLL execution");
    }
    public static void Run(string root,string bundle) {
        var m=Manifest(bundle);if(m.schema!=2)return;
        string data=Path.Combine(root,"compat-basic");Seed(data,m,1);
        File.WriteAllText(Path.Combine(data,"plugins","BambuSource.dll"),"camera untouched");
        File.WriteAllText(Path.Combine(data,"OrcaSlicer.conf"),"account settings untouched");
        var original=m.series.Values.ToDictionary(s=>s.bridge,s=>ConnectionManager.Hash(Path.Combine(data,"plugins",s.bridge)));
        var io=new FixtureFiles();var manager=new ConnectionManager(bundle,data,io);
        var plan=manager.Check();Assert(plan.changes.Count==8,"Expected independent backend for each entry");
        Assert(!Directory.Exists(Path.Combine(data,"queue-connection-backups")),"Check wrote backups");
        io.busy=true;Fails(()=>manager.InstallReviewed(plan));io.busy=false;
        manager.InstallReviewed(plan);
        foreach(var s in m.series.Values)Assert(ConnectionManager.Hash(Path.Combine(data,"plugins",s.backend))==original[s.bridge],"User core not preserved verbatim");
        Assert(manager.Check().changes.Count==0,"Installed adapter not recognized");
        int count=Directory.GetDirectories(Path.Combine(data,"queue-connection-backups")).Length;manager.Install();
        Assert(Directory.GetDirectories(Path.Combine(data,"queue-connection-backups")).Length==count,"No-op made backup");
        manager.Restore();
        foreach(var s in m.series.Values)Assert(ConnectionManager.Hash(Path.Combine(data,"plugins",s.bridge))==original[s.bridge]&&!File.Exists(Path.Combine(data,"plugins",s.backend)),"Restore lost original core");
        Assert(File.ReadAllText(Path.Combine(data,"plugins","BambuSource.dll"))=="camera untouched","Camera changed");
        Assert(File.ReadAllText(Path.Combine(data,"OrcaSlicer.conf"))=="account settings untouched","Account changed");
        manager.Install();Seed(data,m,2);Fails(()=>manager.Restore());
        plan=manager.Check();manager.InstallReviewed(plan);
        foreach(var s in m.series.Values)Assert(ConnectionManager.Hash(Path.Combine(data,"plugins",s.backend))!=original[s.bridge],"Update kept old core");
        Assert(manager.Check().changes.Count==0,"Readaptation failed");
        manager.Restore();
        foreach(var s in m.series.Values)Assert(NativeLibraryInfo.Read(Path.Combine(data,"plugins",s.bridge)).openBamboo,"Update restore did not return upstream");
        manager.Install();
        // Only one entry updates. Ownership must retain the other unchanged backends.
        var first=m.series.Values.First();Core(Path.Combine(data,"plugins",first.bridge),first,3);manager.Install();
        var second=m.series.Values.Last();Core(Path.Combine(data,"plugins",second.bridge),second,4);manager.Install();
        Assert(manager.Check().changes.Count==0,"Partial update lost backend ownership");
        data=Path.Combine(root,"compat-stale");Seed(data,m,1);manager=new ConnectionManager(bundle,data,new FixtureFiles());plan=manager.Check();Seed(data,m,2);Fails(()=>manager.InstallReviewed(plan));
        Assert(!Directory.Exists(Path.Combine(data,"queue-connection-backups")),"Stale review wrote target");
        data=Path.Combine(root,"compat-rollback");Seed(data,m,1);io=new FixtureFiles{failPlace=6};manager=new ConnectionManager(bundle,data,io);Fails(()=>manager.Install());
        foreach(var s in m.series.Values)Assert(ConnectionManager.Hash(Path.Combine(data,"plugins",s.bridge))==original[s.bridge]&&!File.Exists(Path.Combine(data,"plugins",s.backend)),"Adapt rollback failed");
        data=Path.Combine(root,"compat-restore-failure");Seed(data,m,1);io=new FixtureFiles();manager=new ConnectionManager(bundle,data,io);manager.Install();io.failDelete=2;Fails(()=>manager.Restore());
        Assert(manager.Check().changes.Count==0,"Restore rollback lost adapted core");io.failDelete=0;manager.Restore();
        data=Path.Combine(root,"compat-new-export");Seed(data,m,1);Core(Path.Combine(data,"plugins",first.bridge),first,1,"bambu_network_unknown_new_api");manager=new ConnectionManager(bundle,data,new FixtureFiles());Fails(()=>manager.Check());
        data=Path.Combine(root,"compat-new-abi");Seed(data,m,1);Core(Path.Combine(data,"plugins",first.bridge),first,1,null,"02.09.00");manager=new ConnectionManager(bundle,data,new FixtureFiles());Fails(()=>manager.Check());
        data=Path.Combine(root,"compat-foreign-backend");Seed(data,m,1);File.WriteAllText(Path.Combine(data,"plugins",first.backend),"not owned");manager=new ConnectionManager(bundle,data,new FixtureFiles());Fails(()=>manager.Check());
        data=Path.Combine(root,"compat-corrupt");Seed(data,m,1);File.WriteAllBytes(Path.Combine(data,"plugins",first.bridge),new byte[500]);manager=new ConnectionManager(bundle,data,new FixtureFiles());Fails(()=>manager.Check());
        data=Path.Combine(root,"compat-empty");manager=new ConnectionManager(bundle,data,new FixtureFiles());Fails(()=>manager.Check());Assert(!Directory.Exists(data),"Missing upstream check wrote target");
        data=Path.Combine(root,"compat-adapter-upgrade");Seed(data,m,1);manager=new ConnectionManager(bundle,data,new FixtureFiles());manager.Install();
        string updatedBundle=Path.Combine(root,"updated-adapter");Directory.CreateDirectory(Path.Combine(updatedBundle,"bin"));
        foreach(var file in m.files)File.Copy(Path.Combine(bundle,"bin",file.Key),Path.Combine(updatedBundle,"bin",file.Key));
        string updatedEntry=Path.Combine(updatedBundle,"bin",first.bridge);
        using(var stream=new FileStream(updatedEntry,FileMode.Append))stream.WriteByte(77);
        string oldWrapper=m.files[first.bridge].sha256;
        m.files[first.bridge].sha256=ConnectionManager.Hash(updatedEntry);
        using(var stream=File.Create(Path.Combine(updatedBundle,"components.json")))new DataContractJsonSerializer(typeof(ComponentManifest),new DataContractJsonSerializerSettings{UseSimpleDictionaryFormat=true}).WriteObject(stream,m);
        manager=new ConnectionManager(updatedBundle,data,new FixtureFiles());
        Assert(manager.Check().changes.Count==1,"Adapter upgrade changed upstream core");manager.Install();Assert(manager.Check().changes.Count==0,"Adapter upgrade failed");manager.Restore();
        Assert(ConnectionManager.Hash(Path.Combine(data,"plugins",first.bridge))==oldWrapper,"Adapter upgrade restore failed");
        Assert(manager.Check().changes.Count==1,"Restored adapter lost ownership for re-upgrade");
        manager.Install();Assert(manager.Check().changes.Count==0,"Re-upgrade after restore failed");
        Console.WriteLine("PASS adaptive installer: all 4 entries, core preservation, updates, partial updates, backups, restore, stale plans, busy guard, rollback, ABI/exports/malformed/foreign-file rejection");
    }
}