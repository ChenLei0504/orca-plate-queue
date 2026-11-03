// SPDX-License-Identifier: AGPL-3.0-or-later
// Static PE inspection only: never LoadLibrary or execute a candidate backend.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;

public sealed class NativeLibraryInfo {
    public HashSet<string> exports = new HashSet<string>(StringComparer.Ordinal);
    public HashSet<string> versions = new HashSet<string>(StringComparer.Ordinal);
    public bool openBamboo;
    sealed class PE {
        readonly byte[] bytes;
        readonly List<uint[]> sections = new List<uint[]>();
        public PE(byte[] b) { bytes=b; }
        public void Need(long at,long size) { if(at<0||size<0||at>bytes.Length-size)throw new IOException("联网文件 PE 结构损坏。"); }
        public ushort U16(long at) { Need(at,2);return BitConverter.ToUInt16(bytes,(int)at); }
        public uint U32(long at) { Need(at,4);return BitConverter.ToUInt32(bytes,(int)at); }
        public long Pos(uint rva,int length) {
            foreach(var s in sections) if(rva>=s[0]&&(long)rva-s[0]+length<=s[1]) {
                long p=(long)s[2]+rva-s[0];Need(p,length);return p;
            }
            throw new IOException("联网文件导出表地址无效。");
        }
        public string Name(uint rva) {
            var text=new StringBuilder();
            for(int i=0;i<256;i++) { byte c=bytes[(int)Pos(checked(rva+(uint)i),1)];if(c==0)return text.ToString();if(c<32||c>126)break;text.Append((char)c); }
            throw new IOException("联网文件导出名称无效。");
        }
        public HashSet<string> Read() {
            if(U16(0)!=0x5a4d)throw new IOException("联网文件不是 Windows DLL。");
            long pe=U32(60);
            if(U32(pe)!=0x4550||U16(pe+4)!=0x8664||(U16(pe+22)&0x2000)==0)throw new IOException("联网文件必须为 Windows x64 DLL。");
            int count=U16(pe+6),optional=U16(pe+20);long opt=pe+24;
            if(count<1||count>96||optional<120||U16(opt)!=0x20b||U32(opt+108)<1)throw new IOException("联网文件 PE 格式不支持。");
            Need(opt,optional+count*40);
            for(int i=0;i<count;i++) { long s=opt+optional+i*40;sections.Add(new[]{U32(s+12),U32(s+16),U32(s+20)}); }
            long table=Pos(U32(opt+112),40);
            uint functions=U32(table+20),names=U32(table+24);
            if(functions==0||functions>8192||names==0||names>functions)throw new IOException("联网文件导出数量无效。");
            long np=Pos(U32(table+32),checked((int)names*4)),op=Pos(U32(table+36),checked((int)names*2)),fp=Pos(U32(table+28),checked((int)functions*4));
            var result=new HashSet<string>(StringComparer.Ordinal);
            for(uint i=0;i<names;i++) {
                ushort ordinal=U16(op+i*2);
                if(ordinal>=functions||U32(fp+ordinal*4)==0)throw new IOException("联网文件导出函数无效。");
                string name=Name(U32(np+i*4));
                if(!Regex.IsMatch(name,@"\A[A-Za-z_][A-Za-z_0-9]*\z")||!result.Add(name))throw new IOException("联网文件导出名称不支持。");
            }
            return result;
        }
    }
    public static NativeLibraryInfo Read(string path) {
        var length=new FileInfo(path).Length;
        if(length<128||length>64*1024*1024)throw new IOException("联网文件大小不支持。");
        byte[] b=File.ReadAllBytes(path);
        var result=new NativeLibraryInfo{exports=new PE(b).Read()};
        // The upstream ABI version is a NUL-terminated constant returned by
        // bambu_network_get_version. Reading it does not execute the library.
        string text=Encoding.ASCII.GetString(b);
        foreach(Match m in Regex.Matches(text,@"(?<![0-9.])(\d{2}\.\d{2}\.\d{2})\.\d+\x00"))result.versions.Add(m.Groups[1].Value);
        result.openBamboo=text.Contains("open-bamboo-networking")&&result.exports.Contains("obn_ensure_conf_fixes");
        return result;
    }
}

public sealed partial class ConnectionManager {
    static void CompatibleCore(string path,ComponentSeries spec) {
        var info=NativeLibraryInfo.Read(path);
        if(info.exports.Any(n=>n.StartsWith("obn_queue_",StringComparison.Ordinal)))throw new IOException("检测到队列桥接，不能将桥接再次作为联网核心。");
        if(!info.openBamboo||spec.abi==null||!info.versions.SetEquals(new[]{spec.abi}))throw new IOException("联网核心来源或接口系列不匹配："+Path.GetFileName(path));
        if(spec.exports==null||!info.exports.SetEquals(spec.exports))throw new IOException("联网接口函数发生变化，需要新版适配器："+Path.GetFileName(path));
    }
    ComponentPlan CompatiblePlan(ComponentManifest manifest) {
        var plan=new ComponentPlan{manifest=manifest,target=Path.GetFullPath(Path.Combine(data,"plugins"))};
        Plain(plan.target);int found=0;
        var desired=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach(var pair in manifest.series.OrderBy(p=>p.Key)) {
            var spec=pair.Value;
            if(spec==null||!manifest.files.ContainsKey(spec.bridge)||manifest.files[spec.bridge].role!="bridge"||!desired.Add(spec.backend))throw new IOException("适配器清单无效。");
            string entry=Child(plan.target,spec.bridge),backend=Child(plan.target,spec.backend);
            string before=Hash(entry);if(before=="")continue;found++;
            string after=manifest.files[spec.bridge].sha256;
            if(before==after) { CompatibleCore(backend,spec);plan.notes.Add(spec.bridge+"：已适配，保留当前联网核心");continue; }
            string source=entry;
            var info=NativeLibraryInfo.Read(entry);
            if(info.exports.Any(n=>n.StartsWith("obn_queue_",StringComparison.Ordinal))) {
                if(OwnsEntry(entry)&&OwnsBackend(backend,manifest))source=backend;
                else {
                    if(!(spec.compatible_bridge_hashes??new string[0]).Contains(before)||String.IsNullOrEmpty(spec.legacy_backend))throw new IOException("发现其他版本桥接，请先使用原安装器恢复后再适配："+spec.bridge);
                    source=Child(plan.target,spec.legacy_backend);
                }
            }
            CompatibleCore(source,spec);
            string sourceHash=Hash(source),backendBefore=Hash(backend);
            if(backendBefore!=""&&backendBefore!=sourceHash&&!OwnsBackend(backend,manifest))throw new IOException("同名私有核心不属于已记录的安装，未覆盖："+spec.backend);
            if(backendBefore!=sourceHash) {
                plan.changes.Add(new ComponentRow{name=spec.backend,before=backendBefore,after=sourceHash});
                plan.sources[spec.backend]=source;
            }
            plan.changes.Add(new ComponentRow{name=spec.bridge,before=before,after=after});
            plan.sources[spec.bridge]=Child(Path.Combine(bundle,"bin"),spec.bridge);
            plan.notes.Add(spec.bridge+"：接口 "+spec.abi+" 匹配，原样保留现有核心（"+sourceHash.Substring(0,12)+"）");
        }
        if(found==0)throw new IOException("未找到支持的 Open Bamboo 联网文件。请先安装 Open Bamboo，或选择 Orca 实际使用的数据目录。");
        // All backends must be staged/installed before any entry-point wrapper.
        plan.changes=plan.changes.OrderBy(r=>manifest.files.ContainsKey(r.name)?1:0).ThenBy(r=>r.name).ToList();
        return plan;
    }
    bool OwnsEntry(string path) {
        try {
            string root=Path.Combine(data,"queue-connection-backups");Plain(root);
            var latest=Read<LatestReceipt>(Path.Combine(root,"latest.json"));
            if(latest.backup==null||!Regex.IsMatch(latest.backup,@"\A[A-Za-z0-9-]+\z"))return false;
            var receipt=Read<ComponentReceipt>(Path.Combine(root,latest.backup,"receipt.json"));
            if(receipt.schema!=2||(receipt.phase!="installed"&&receipt.phase!="restored")||receipt.target!=Path.GetFullPath(Path.Combine(data,"plugins")))return false;
            string name=Path.GetFileName(path),hash=Hash(path);
            if(receipt.phase=="restored"&&receipt.files!=null) {
                var changed=receipt.files.FirstOrDefault(r=>r.name==name);
                if(changed!=null)return changed.before==hash&&hash!="";
            }
            return receipt.entries!=null&&receipt.entries.Any(r=>r.name==name&&r.after==hash);
        } catch {return false;}
    }
    bool OwnsBackend(string path,ComponentManifest manifest) {
        try {
            string root=Path.Combine(data,"queue-connection-backups");Plain(root);
            var latest=Read<LatestReceipt>(Path.Combine(root,"latest.json"));
            if(latest.backup==null||!Regex.IsMatch(latest.backup,@"\A[A-Za-z0-9-]+\z"))return false;
            var receipt=Read<ComponentReceipt>(Path.Combine(root,latest.backup,"receipt.json"));
            if(receipt.schema!=2||(receipt.phase!="installed"&&receipt.phase!="restored")||receipt.target!=Path.GetFullPath(Path.Combine(data,"plugins")))return false;
            // A later repair may leave an unchanged backend out of its delta.
            // Installed ownership is persisted separately from the restore delta.
            string name=Path.GetFileName(path),hash=Hash(path);
            if(receipt.phase=="restored"&&receipt.files!=null) {
                var changed=receipt.files.FirstOrDefault(r=>r.name==name);
                if(changed!=null)return changed.before==hash&&hash!="";
            }
            return receipt.backends!=null&&receipt.backends.Any(r=>r.name==name&&r.after==hash);
        } catch {return false;}
    }
    static string ReplacementSource(string bundle,string backup,ComponentRow row) {
        string staged=Child(Path.Combine(backup,"incoming"),row.name);
        if(Hash(staged)==row.after)return staged;
        string original=Child(Path.Combine(bundle,"bin"),row.name);
        if(Hash(original)!=row.after)throw new IOException("安装源校验失败："+row.name);
        return original;
    }
    static void ValidateRestoreRow(ComponentManifest manifest,ComponentReceipt receipt,ComponentRow row,string backup) {
        if(row==null||!Regex.IsMatch(row.before??"",@"\A(?:[a-f0-9]{64})?\z")||!Regex.IsMatch(row.after??"",@"\A[a-f0-9]{64}\z"))throw new IOException("备份记录无效。");
        ComponentEntry file;
        if(manifest.files.TryGetValue(row.name,out file)) {if(row.after!=file.sha256)throw new IOException("备份不属于本安装器版本。");return;}
        var specs=manifest.series.Values.Where(s=>s.backend==row.name).ToArray();
        if(manifest.schema!=2||receipt.schema!=2||specs.Length!=1)throw new IOException("备份包含未知组件。");
        string staged=Child(Path.Combine(backup,"incoming"),row.name);
        if(Hash(staged)!=row.after)throw new IOException("私有联网核心备份校验失败。");
        CompatibleCore(staged,specs[0]);
    }
}