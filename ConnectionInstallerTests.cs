// Offline fixtures only. No real Orca path or SDK is used by this executable.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.Serialization.Json;
using System.Drawing;
using System.Windows.Forms;

sealed class FixtureFiles : IComponentFiles {
    public bool busy;
    public int placements, deletions, failPlace, failDelete;
    readonly ComponentFiles actual = new ComponentFiles();
    public bool OrcaRunning() { return busy; }
    public void Place(string s, string t, string h) { if (++placements == failPlace) throw new IOException("fixture copy failure"); actual.Place(s,t,h); }
    public void Delete(string p) { if (++deletions == failDelete) throw new IOException("fixture delete failure"); actual.Delete(p); }
}
static class ConnectionInstallerTests {
    static void Layout(Control control) {
        var handle=control.Handle;
        foreach(Control child in control.Controls)Layout(child);
        control.PerformLayout();
    }
    static void Assert(bool ok, string text) { if (!ok) throw new Exception(text); }
    static void Fails(Action action) { bool failed = false; try { action(); } catch { failed = true; } Assert(failed,"Expected rejection"); }
    static void Json<T>(string path, T value) {
        using (var s = File.Create(path)) new DataContractJsonSerializer(typeof(T),new DataContractJsonSerializerSettings { UseSimpleDictionaryFormat=true }).WriteObject(s,value);
    }
    static void PE(string path, byte marker) {
        byte[] b = new byte[128]; b[0]=77;b[1]=90;b[60]=64;b[64]=80;b[65]=69;b[68]=100;b[69]=134;b[100]=marker;File.WriteAllBytes(path,b);
    }
    [STAThread] public static void Main(string[] args) {
        try { Run(args); }
        catch(Exception error) { Console.WriteLine("FAIL "+error.GetType().Name+": "+error.Message);Console.WriteLine(error.StackTrace);Environment.ExitCode=1; }
    }
    static void Run(string[] args) {
        Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);
        string root=Path.GetFullPath(args[0]);Directory.CreateDirectory(root);
        string bundle=Path.Combine(root,"bundle"),bin=Path.Combine(bundle,"bin");Directory.CreateDirectory(bin);
        string bridge="bambu_networking_02.03.00.dll",backend="orca_queue_upstream_020300_b14f880.dll";
        PE(Path.Combine(bin,bridge),1);PE(Path.Combine(bin,backend),2);PE(Path.Combine(bin,"camera.dll"),3);
        var manifest=new ComponentManifest { schema=1,version="fixture",files=new Dictionary<string,ComponentEntry>(),series=new Dictionary<string,ComponentSeries>() };
        foreach(var pair in new [] {new [] {bridge,"bridge"},new [] {backend,"backend"},new [] {"camera.dll","sidecar"}})
            manifest.files[pair[0]]=new ComponentEntry {sha256=ConnectionManager.Hash(Path.Combine(bin,pair[0])),role=pair[1],preserve_existing=pair[1]=="sidecar"};
        manifest.series["02.03.00"]=new ComponentSeries {bridge=bridge,backend=backend,compatible_bridge_hashes=new string[0]};
        Json(Path.Combine(bundle,"components.json"),manifest);
        var io=new FixtureFiles();string data=Path.Combine(root,"fresh");var manager=new ConnectionManager(bundle,data,io);
        Assert(manager.Check().changes.Count==3&&!Directory.Exists(data),"Check modified target");
        Assert(!manager.HasRestorableBackup(),"Fresh install has restore enabled");
        io.busy=true;Fails(()=>manager.Install());Assert(!Directory.Exists(data),"Busy guard wrote target");io.busy=false;
        manager.Install();Assert(manager.Check().changes.Count==0,"Install failed");
        Assert(manager.HasRestorableBackup(),"Installed backup unavailable");
        int backups=Directory.GetDirectories(Path.Combine(data,"queue-connection-backups")).Length;
        manager.Install();Assert(Directory.GetDirectories(Path.Combine(data,"queue-connection-backups")).Length==backups,"No-op changed backup");
        manager.Restore();Assert(!File.Exists(Path.Combine(data,"plugins",bridge)),"Restore left new files");Fails(()=>manager.Restore());
        Assert(!manager.HasRestorableBackup(),"Restored backup still enabled");
        data=Path.Combine(root,"existing");Directory.CreateDirectory(Path.Combine(data,"plugins"));
        File.Copy(Path.Combine(bin,backend),Path.Combine(data,"plugins",bridge));File.WriteAllText(Path.Combine(data,"plugins","camera.dll"),"real-camera");
        File.WriteAllText(Path.Combine(data,"queue-sentinel.txt"),"unchanged");string old=ConnectionManager.Hash(Path.Combine(data,"plugins",bridge));
        manager=new ConnectionManager(bundle,data,new FixtureFiles());manager.Install();
        Assert(File.ReadAllText(Path.Combine(data,"plugins","camera.dll"))=="real-camera","Replaced existing camera");manager.Restore();
        Assert(ConnectionManager.Hash(Path.Combine(data,"plugins",bridge))==old,"Original SDK not restored");
        Assert(File.ReadAllText(Path.Combine(data,"queue-sentinel.txt"))=="unchanged","Queue touched");
        File.WriteAllText(Path.Combine(data,"plugins",bridge),"unknown");Fails(()=>manager.Install());
        data=Path.Combine(root,"updated");manager=new ConnectionManager(bundle,data,new FixtureFiles());manager.Install();
        File.WriteAllText(Path.Combine(data,"plugins",bridge),"external-update");Fails(()=>manager.Restore());
        Assert(File.ReadAllText(Path.Combine(data,"plugins",bridge))=="external-update","External update overwritten");
        data=Path.Combine(root,"install-failure");io=new FixtureFiles{failPlace=2};manager=new ConnectionManager(bundle,data,io);Fails(()=>manager.Install());
        Assert(Directory.GetFiles(Path.Combine(data,"plugins")).Length==0,"Install rollback failed");
        data=Path.Combine(root,"restore-failure");io=new FixtureFiles();manager=new ConnectionManager(bundle,data,io);manager.Install();
        io.failDelete=2;Fails(()=>manager.Restore());Assert(manager.Check().changes.Count==0,"Restore rollback failed");io.failDelete=0;manager.Restore();
        Fails(()=>ConnectionManager.Child(root,"../escape.dll"));
        PE(Path.Combine(bin,bridge),99);data=Path.Combine(root,"tamper");manager=new ConnectionManager(bundle,data,new FixtureFiles());Fails(()=>manager.Install());Assert(!Directory.Exists(data),"Tamper wrote target");
        if(args.Length==1)ConnectionCompatibilityTests.Run(root,ConnectionCompatibilityTests.FixtureBundle(root));
        if(args.Length>1) { new ConnectionManager(args[1],Path.Combine(root,"real-bundle-check-only"),new FixtureFiles()).Verify();ConnectionCompatibilityTests.Run(root,args[1]); }
        if(args.Length>3)ConnectionCompatibilityTests.RealCores(root,args[1],args[2],args[3]);
        using(var form=new ConnectionInstallerForm()) using(var image=new Bitmap(form.Width,form.Height)) {
            Layout(form);form.DrawToBitmap(image,new Rectangle(0,0,form.Width,form.Height));image.Save(Path.Combine(root,"installer-preview.png"));
        }
        Console.WriteLine("PASS standalone installer: check-only, busy guard, install, no-op, backup, restore, original SDK, camera preservation, unknown SDK rejection, external changes, tampering and transaction rollback");
        Console.WriteLine("No real Orca data, printer commands or native libraries used.");
    }
}
