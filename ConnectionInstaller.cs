// SPDX-License-Identifier: AGPL-3.0-or-later
// Standalone file installer. No network, printer SDK, subprocess or script execution.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Windows.Forms;

[DataContract] public sealed class ComponentEntry {
    [DataMember] public string sha256;
    [DataMember] public string role;
    [DataMember] public bool preserve_existing;
}
[DataContract] public sealed class ComponentSeries {
    [DataMember] public string bridge;
    [DataMember] public string backend;
    [DataMember] public string[] compatible_bridge_hashes;
    [DataMember] public string abi;
    [DataMember] public string[] exports;
    [DataMember] public string legacy_backend;
}
[DataContract] public sealed class ComponentManifest {
    [DataMember] public int schema;
    [DataMember] public string version;
    [DataMember] public Dictionary<string, ComponentEntry> files;
    [DataMember] public Dictionary<string, ComponentSeries> series;
}
[DataContract] public sealed class ComponentRow {
    [DataMember] public string name;
    [DataMember] public string before;
    [DataMember] public string after;
}
[DataContract] public sealed class ComponentReceipt {
    [DataMember] public int schema = 1;
    [DataMember] public string target;
    [DataMember] public string phase;
    [DataMember] public List<ComponentRow> files;
    [DataMember] public List<ComponentRow> backends;
    [DataMember] public List<ComponentRow> entries;
}
[DataContract] public sealed class LatestReceipt { [DataMember] public string backup; }
public sealed class ComponentPlan {
    public Dictionary<string,string> sources = new Dictionary<string,string>();
    public List<string> notes = new List<string>();
    public ComponentManifest manifest;
    public string target;
    public List<ComponentRow> changes = new List<ComponentRow>();
}
public interface IComponentFiles {
    bool OrcaRunning();
    void Place(string source, string target, string expected);
    void Delete(string path);
}
public sealed class ComponentFiles : IComponentFiles {
    public bool OrcaRunning() {
        var processes = Process.GetProcessesByName("orca-slicer");
        try { return processes.Length > 0; }
        finally { foreach (var p in processes) p.Dispose(); }
    }
    public void Place(string source, string target, string expected) {
        string pending = Path.Combine(Path.GetDirectoryName(target), ".queue-" + Guid.NewGuid().ToString("N") + ".tmp");
        try {
            File.Copy(source, pending, false);
            if (ConnectionManager.Hash(pending) != expected) throw new IOException("组件复制校验失败。");
            if (File.Exists(target)) File.Replace(pending, target, null); else File.Move(pending, target);
            if (ConnectionManager.Hash(target) != expected) throw new IOException("组件安装后校验失败。");
        } finally { if (File.Exists(pending)) File.Delete(pending); }
    }
    public void Delete(string path) { File.Delete(path); }
}
public sealed partial class ConnectionManager {
    readonly string bundle, data;
    readonly IComponentFiles files;
    public ConnectionManager(string bundle, string data, IComponentFiles files) {
        this.bundle = Path.GetFullPath(bundle); this.data = Path.GetFullPath(data); this.files = files;
    }
    public static string Hash(string path) {
        if (!File.Exists(path)) return "";
        using (var h = SHA256.Create()) using (var s = File.OpenRead(path))
            return BitConverter.ToString(h.ComputeHash(s)).Replace("-", "").ToLowerInvariant();
    }
    static T Read<T>(string path) {
        var settings = new DataContractJsonSerializerSettings { UseSimpleDictionaryFormat = true };
        using (var stream = File.OpenRead(path)) {
            if (stream.Length > 2000000) throw new IOException("清单过大。");
            return (T)new DataContractJsonSerializer(typeof(T), settings).ReadObject(stream);
        }
    }
    static void Write<T>(string path, T value) {
        var settings = new DataContractJsonSerializerSettings { UseSimpleDictionaryFormat = true };
        string pending = Path.Combine(Path.GetDirectoryName(path), ".queue-" + Guid.NewGuid().ToString("N") + ".tmp");
        try {
            using (var stream = new FileStream(pending, FileMode.CreateNew, FileAccess.Write)) {
                new DataContractJsonSerializer(typeof(T), settings).WriteObject(stream, value); stream.Flush(true);
            }
            if (File.Exists(path)) File.Replace(pending, path, null); else File.Move(pending, path);
        } finally { if (File.Exists(pending)) File.Delete(pending); }
    }
    static void Plain(string path) {
        for (var cursor = new DirectoryInfo(Path.GetFullPath(path)); cursor != null; cursor = cursor.Parent)
            if (cursor.Exists && (cursor.Attributes & FileAttributes.ReparsePoint) != 0)
                throw new IOException("路径包含链接或重定向，已停止操作。");
        if (File.Exists(path) && (File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0)
            throw new IOException("文件是链接，已停止操作。");
    }
    public static string Child(string root, string name) {
        if (name == null || !Regex.IsMatch(name, @"\A[A-Za-z0-9_.-]+\.dll\z")) throw new IOException("组件文件名无效。");
        string full = Path.GetFullPath(Path.Combine(root, name));
        if (!String.Equals(Path.GetDirectoryName(full), Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar), StringComparison.OrdinalIgnoreCase))
            throw new IOException("组件路径超出目标目录。");
        Plain(full); return full;
    }
    void Closed() { if (files.OrcaRunning()) throw new IOException("请保存工程并完整退出 OrcaSlicer，再安装或恢复连接组件。"); }
    public bool HasRestorableBackup() {
        try {
            string root=Path.Combine(data,"queue-connection-backups");Plain(root);
            var latest=Read<LatestReceipt>(Path.Combine(root,"latest.json"));
            if(latest.backup==null||!Regex.IsMatch(latest.backup,@"\A[A-Za-z0-9-]+\z"))return false;
            var receipt=Read<ComponentReceipt>(Path.Combine(root,latest.backup,"receipt.json"));
            return receipt.phase=="installed"&&receipt.target==Path.GetFullPath(Path.Combine(data,"plugins"));
        } catch { return false; }
    }
    public ComponentManifest Verify() {
        var manifest = Read<ComponentManifest>(Path.Combine(bundle, "components.json"));
        if ((manifest.schema != 1 && manifest.schema != 2) || manifest.files == null || manifest.files.Count == 0 || manifest.files.Count > 32 || manifest.series == null)
            throw new IOException("组件清单格式不支持。");
        foreach (var item in manifest.files) {
            string path = Child(Path.Combine(bundle, "bin"), item.Key);
            if (item.Value == null || item.Value.sha256 == null || !Regex.IsMatch(item.Value.sha256, @"\A[a-f0-9]{64}\z") || Hash(path) != item.Value.sha256)
                throw new IOException("组件包校验失败：" + item.Key);
            byte[] bytes = File.ReadAllBytes(path);
            if (bytes.Length < 64 || bytes[0] != 77 || bytes[1] != 90) throw new IOException("无效 Windows 组件。");
            uint offset = BitConverter.ToUInt32(bytes, 60);
            if (offset > bytes.Length - 6 || BitConverter.ToUInt32(bytes, (int)offset) != 17744 || BitConverter.ToUInt16(bytes, (int)offset + 4) != 34404)
                throw new IOException("组件必须为 Windows x64 PE 文件。");
        }
        return manifest;
    }
    public ComponentPlan Check() {
        var manifest = Verify();
        if (manifest.schema == 2) return CompatiblePlan(manifest);
        var plan = new ComponentPlan { manifest = manifest, target = Path.GetFullPath(Path.Combine(data, "plugins")) };
        Plain(plan.target);
        foreach (var item in manifest.files.OrderBy(x => x.Value.role == "bridge").ThenBy(x => x.Key)) {
            string before = Hash(Child(plan.target, item.Key)), after = item.Value.sha256;
            if (before == after || (before != "" && item.Value.preserve_existing)) continue;
            if (before != "" && item.Value.role == "backend") throw new IOException("已有同名后端与本包不符，未覆盖：" + item.Key);
            if (before != "" && item.Value.role == "bridge") {
                var specs = manifest.series.Where(x => x.Value.bridge == item.Key || (item.Key == "bambu_networking.dll" && x.Key == "02.08.04")).ToArray();
                if (specs.Length != 1) throw new IOException("无法识别已有联网组件接口。");
                var spec = specs[0].Value;
                string upstream = manifest.files[spec.backend].sha256;
                var known = new [] { after, upstream }.Concat(spec.compatible_bridge_hashes ?? new string[0]);
                if (!known.Contains(before)) throw new IOException("已有组件不是已核对版本，未覆盖：" + item.Key);
                if (before != upstream && Hash(Child(plan.target, spec.backend)) != upstream) throw new IOException("已有桥接后端不匹配，未覆盖。");
            }
            plan.changes.Add(new ComponentRow { name = item.Key, before = before, after = after });
        }
        return plan;
    }
    void RestoreRow(string target, string backup, ComponentRow row) {
        string path = Child(target, row.name), current = Hash(path);
        if (current == row.before) return;
        if (current != row.after) throw new IOException("组件被其他程序修改，未覆盖：" + row.name);
        if (row.before != "") {
            string saved = Child(backup, row.name);
            if (Hash(saved) != row.before) throw new IOException("备份校验失败。");
            files.Place(saved, path, row.before);
        } else files.Delete(path);
    }
    public string Install() {
        Closed(); return Apply(Check());
    }
    public string InstallReviewed(ComponentPlan reviewed) {
        Closed();var current=Check();
        Func<ComponentPlan,string[]> signature=p=>p.changes.Select(r=>r.name+"|"+r.before+"|"+r.after).ToArray();
        if(reviewed==null||reviewed.target!=current.target||!signature(reviewed).SequenceEqual(signature(current)))
            throw new IOException("组件在确认后发生变化，请重新检查。");
        return Apply(current);
    }
    string Apply(ComponentPlan plan) {
        if (plan.changes.Count == 0) return "连接组件已匹配，无需重复安装。";
        string backupRoot = Path.Combine(data, "queue-connection-backups"); Plain(backupRoot);
        string backup = Path.Combine(backupRoot, Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(backup); Directory.CreateDirectory(plan.target);
        foreach (var row in plan.changes) if (row.before != "") {
            File.Copy(Child(plan.target, row.name), Child(backup, row.name), false);
            if (Hash(Child(backup, row.name)) != row.before) throw new IOException("备份文件校验失败。");
        }
        // Freeze every source before replacing entry points: a backend source may
        // be the user's current entry-point DLL. Never load it during install.
        string incoming=Path.Combine(backup,"incoming");Directory.CreateDirectory(incoming);
        foreach(var row in plan.changes) {
            string source; if(!plan.sources.TryGetValue(row.name,out source))source=Child(Path.Combine(bundle,"bin"),row.name);
            File.Copy(source,Child(incoming,row.name),false);
            if(Hash(Child(incoming,row.name))!=row.after)throw new IOException("联网核心在检查后发生变化，已停止安装。");
        }
        var receipt = new ComponentReceipt { schema=plan.manifest.schema, target = plan.target, phase = "prepared", files = plan.changes, backends=new List<ComponentRow>(), entries=new List<ComponentRow>() };
        string receiptPath = Path.Combine(backup, "receipt.json"); Write(receiptPath, receipt);
        var changed = new List<ComponentRow>();
        try {
            foreach (var row in plan.changes) {
                Closed(); string path = Child(plan.target, row.name);
                if (Hash(path) != row.before) throw new IOException("组件被其他安装器修改，安装中止。");
                changed.Add(row); files.Place(ReplacementSource(bundle,backup,row), path, row.after);
            }
            if(plan.manifest.schema==2) foreach(var spec in plan.manifest.series.Values) {
                string h=Hash(Child(plan.target,spec.backend));
                string entryHash=Hash(Child(plan.target,spec.bridge));
                if(entryHash==plan.manifest.files[spec.bridge].sha256) {
                    if(h!="")receipt.backends.Add(new ComponentRow{name=spec.backend,after=h,before=""});
                    receipt.entries.Add(new ComponentRow{name=spec.bridge,after=entryHash,before=""});
                }
            }
            receipt.phase = "installed"; Write(receiptPath, receipt);
            Write(Path.Combine(backupRoot, "latest.json"), new LatestReceipt { backup = Path.GetFileName(backup) });
        } catch (Exception original) {
            var failures = new List<string>();
            changed.Reverse();
            foreach (var row in changed) try { RestoreRow(plan.target, backup, row); } catch (Exception e) { failures.Add(e.Message); }
            receipt.phase = failures.Count == 0 ? "rolled_back" : "repair_required"; Write(receiptPath, receipt);
            if (failures.Count != 0) throw new IOException("安装失败，部分文件需要恢复，请保留备份：" + backup, original);
            throw;
        }
        return "连接组件已安装。请重新打开 Orca。" + (plan.manifest.schema==2 ? "已保留现有 Open Bamboo 核心，不会降级联网版本。" : "在首页登录 Bambu Cloud。") + "\r\n备份：" + backup;
    }
    public string Restore() {
        Closed(); var manifest = Verify();
        string backupRoot = Path.Combine(data, "queue-connection-backups"); Plain(backupRoot);
        var latest = Read<LatestReceipt>(Path.Combine(backupRoot, "latest.json"));
        if (latest.backup == null || !Regex.IsMatch(latest.backup, @"\A[A-Za-z0-9-]+\z")) throw new IOException("备份路径无效。");
        string backup = Path.Combine(backupRoot, latest.backup); Plain(backup);
        string receiptPath = Path.Combine(backup, "receipt.json");
        var receipt = Read<ComponentReceipt>(receiptPath);
        string target = Path.GetFullPath(Path.Combine(data, "plugins"));
        if ((receipt.schema != 1 && receipt.schema != 2) || receipt.target != target || receipt.phase != "installed" || receipt.files == null || receipt.files.Count > manifest.files.Count+manifest.series.Count || receipt.files.Select(r=>r.name).Distinct(StringComparer.OrdinalIgnoreCase).Count()!=receipt.files.Count)
            throw new IOException("备份不属于当前目录，或该安装已恢复。");
        foreach (var row in receipt.files) {
            ValidateRestoreRow(manifest,receipt,row,backup);
            string current = Hash(Child(target, row.name));
            if (current != row.before && current != row.after) throw new IOException("组件已被其他安装器更新，恢复中止。");
            if (row.before != "" && Hash(Child(backup, row.name)) != row.before) throw new IOException("备份校验失败。");
        }
        var touched = new List<Tuple<ComponentRow, string>>();
        try {
            foreach (var row in receipt.files.AsEnumerable().Reverse()) {
                Closed(); touched.Add(Tuple.Create(row, Hash(Child(target, row.name)))); RestoreRow(target, backup, row);
            }
        } catch (Exception original) {
            var failures = new List<string>();
            foreach (var item in touched) try {
                var row = item.Item1; string path = Child(target, row.name), current = Hash(path);
                if (current == item.Item2) continue;
                if (current != row.before) throw new IOException("恢复期间组件发生变化。");
                if (item.Item2 == row.after) files.Place(ReplacementSource(bundle,backup,row), path, row.after);
            } catch (Exception e) { failures.Add(e.Message); }
            if (failures.Count != 0) { receipt.phase = "repair_required"; Write(receiptPath, receipt); throw new IOException("恢复未完成，请保留备份：" + backup, original); }
            throw;
        }
        receipt.phase = "restored"; Write(receiptPath, receipt);
        return "已恢复安装前的联网文件。请重新打开 Orca。队列和账号未改动。";
    }
}
public sealed class ConnectionInstallerForm : Form {
    readonly TextBox target = new TextBox(), status = new TextBox();
    readonly Button check = new Button(), install = new Button(), restore = new Button();
    public ConnectionInstallerForm() {
        Text = "Orca 队列连接适配器 · 0.7.4"; Width = 760; Height = 480; MinimumSize = new System.Drawing.Size(680, 400);
        Font = new System.Drawing.Font("Microsoft YaHei UI", 10); StartPosition = FormStartPosition.CenterScreen;
        var label = new Label { Text = "先保存工程并退出 Orca。适配前会备份联网入口；兼容模式保留现有 Open Bamboo 核心。", Dock = DockStyle.Top, Height = 64, Padding = new Padding(14) };
        target.Text = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "OrcaSlicer"); target.Dock = DockStyle.Top;
        var choose = new Button { Text = "选择 Orca 数据目录（便携版）", AutoSize = true };
        choose.Click += delegate { using (var picker = new FolderBrowserDialog()) { picker.Description = "选择 OrcaSlicer 数据目录，不是程序安装目录"; if (picker.ShowDialog(this) == DialogResult.OK) target.Text = picker.SelectedPath; } };
        status.Multiline = true; status.ReadOnly = true; status.ScrollBars = ScrollBars.Vertical; status.Dock = DockStyle.Fill;
        status.Text = "建议先点“检查”。请完整解压并保留同目录 bin、components.json 和源码包。\r\n此工具不下载文件、不运行其他程序，也不连接打印机。";
        var actions = new FlowLayoutPanel { Dock = DockStyle.Bottom, Height = 56, Padding = new Padding(10), FlowDirection = FlowDirection.LeftToRight };
        check.Text = "检查"; install.Text = "安装 / 重新适配"; restore.Text = "恢复原组件";
        foreach (var button in new [] { check, install, restore }) { button.AutoSize = true; actions.Controls.Add(button); }
        target.AutoSize = false; target.Height = 28; choose.Height = 30; choose.AutoSize = false;
        var paths = new Panel { Dock = DockStyle.Top, Height = 90, Padding = new Padding(10) }; paths.Controls.Add(target); choose.Dock = DockStyle.Bottom; paths.Controls.Add(choose);
        Controls.Add(status); Controls.Add(paths); Controls.Add(label); Controls.Add(actions);
        check.Click += delegate { Run("check"); }; install.Click += delegate { Run("install"); }; restore.Click += delegate { Run("restore"); };
        target.TextChanged += delegate { restore.Enabled=BackupAvailable(); };
        restore.Enabled=BackupAvailable();
    }
    bool BackupAvailable() { try { return new ConnectionManager(AppDomain.CurrentDomain.BaseDirectory,target.Text,new ComponentFiles()).HasRestorableBackup(); } catch { return false; } }
    void Run(string action) {
        check.Enabled = install.Enabled = restore.Enabled = false;
        try {
            var manager = new ConnectionManager(AppDomain.CurrentDomain.BaseDirectory, target.Text, new ComponentFiles());
            if(action=="restore") {
                if(MessageBox.Show(this,"恢复此目录安装前的联网文件：\r\n"+target.Text+"\r\n请确认已完整退出 Orca。","恢复原组件",MessageBoxButtons.OKCancel,MessageBoxIcon.Information)!=DialogResult.OK)return;
                status.Text=manager.Restore();
            } else {
                var plan=manager.Check();
                status.Text="目标："+plan.target+"\r\n"+String.Join("\r\n",plan.notes)+"\r\n"+
                    (plan.changes.Count==0?"连接组件已匹配，无需重复安装。":"拟更新文件：\r\n"+String.Join("\r\n",plan.changes.Select(r=>r.name)));
                if(action=="check"||plan.changes.Count==0)return;
                string explanation=plan.manifest.schema==2?"保留当前 Open Bamboo 核心，仅安装兼容的队列桥接。":"本包会安装固定版本联网核心。";
                if(MessageBox.Show(this,explanation+"\r\n"+status.Text+"\r\n请确认已结束打印、保存工程并完整退出 Orca。","确认备份并适配",MessageBoxButtons.OKCancel,MessageBoxIcon.Information)!=DialogResult.OK)return;
                status.Text=manager.InstallReviewed(plan);
            }
        } catch (Exception e) { status.Text = "操作未完成：" + e.Message; }
        finally { check.Enabled = install.Enabled = true; restore.Enabled=BackupAvailable(); }
    }
}
public static class ConnectionInstallerProgram {
    [STAThread] public static void Main() { Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false); Application.Run(new ConnectionInstallerForm()); }
}
