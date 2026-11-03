# 独立云连接版 / Standalone cloud preview

当前产物：**0.8.0a1 · 20261103.4**，本地可安装测试包，尚未发布到市场。
旧的 0.7.8 分离安装版构建入口保持不变。

## 用户使用方式

1. 保存工程，暂停旧版的所有队列，核对未结束任务，然后停用旧版队列插件。
2. 在 Orca 插件管理中安装 `standalone-dist/0.8.0a1/Orca_Plate_Queue_win_x86_64.whl`。
3. 打开“打印队列 → 连接说明”，选择中国大陆或全球区，使用邮箱／中国大陆手机号接收验证码并登录。
4. 先核对 A1 / P1S 设备及 AMS 槽位，再导入单盘切片 3MF 配置耗材和份数。

不用运行旧连接组件安装器，也不要求安装 Open Bamboo、Docker、BamDude 或 Bambuddy。
软件仍复用了固定版本的 Open Bamboo **开源联网核心**，不是重新实现了整个拓竹协议。
不改变打印机的云模式，保留 Handy 是验收要求；目前尚未完成真实账号与 Handy 并发验收。

测试版沿用插件包名，安装可能替换旧队列包。不要同时激活两份队列。
旧任务保留在 `v3`；本测试版使用独立的 `v4-cloud` 数据目录，不自动接管旧任务。
回退时停用测试版并安装原 0.7.8 wheel，旧版联网组件保持原样。

仅包含 Windows x64 构建，要求 Windows 10 1903 或更新版本，以及 Orca 2.5.0 beta 的插件接口。
macOS / Linux 原生组件尚未构建，不能将这个 wheel 用在这些系统上。

## 已实现

- 同一个 wheel 包含页面、调度器、私有连接进程、联网核心和配套微软运行库。
- 私有进程通过标准输入／输出管道通信，不开本地监听端口、不安装系统服务。
- 插件关闭后终止组件；父进程退出时组件自行退出。已开始的打印不会因此被停止。
- 验证码登录支持地区、发送间隔、超时和脱敏错误。验证码仅临时传递，不写入队列或页面状态。
- 插件建立自己的账号会话，退出只清理本地会话，不调用远程账号注销。
- SDK 初次加载前将其配置查找位置限定到本插件目录，不读取 Orca/Open Bamboo 的账号配置。
- 启动前校验包内组件 SHA256；不自动加载用户安装的更新版联网库。
- 登录目录使用 Windows ACL，仅当前用户与 SYSTEM 可访问；**会话文件尚未加密**。
- 登录目录有独占锁，避免两个组件同时改写会话。
- 独立 provider 保留原有逐盘发送、AMS/外挂映射、任务身份核对、状态历史、零件跳过和队列恢复契约。
- 通信中断立即丢弃可用状态；没有回执的打印指令不自动重放。
- 有运行中／未核对任务时拦截账号切换；队列运行中不能手动重建连接。

## 构建与结构

`build_standalone_release.py` 明确选用 `owned_cloud` 模式并设置测试版版本号；普通构建仍选用旧桥接。

| 文件 | 职责 |
| --- | --- |
| `cloud_login.py` | 有界 HTTPS 验证码请求，不跟随重定向，不记录认证正文 |
| `owned_connection.py` | 组件文件校验、隐藏子进程、管道超时、异步登录和状态缓存 |
| `native/owned_host.cpp` | 有界 JSON 管道协议、父进程退出监控 |
| `native/owned_cloud.cpp` | 独立 agent、目录权限、会话锁、自己的登录／状态接口 |
| `printer_connection.py` | 明确选择一种 provider，校验并脱敏设备状态 |
| `plugin_runtime.py` | 页面生命周期、登录动作、运行任务保护 |

构建需要 MSVC v142、Windows SDK 10.0.19041、固定的 b14f880 SDK 源码和 ABI 02.08.04 核心。
`ORCA_QUEUE_VCRT_DIR` 必须指向同一发行版本的 Microsoft x64 14.40+ 运行库；旧的 14.29 运行库会导致该核心在启动时崩溃。

```powershell
python native/build_owned_host.py --fixture
python -m unittest test_owned_connection -v
python native/build_owned_host.py
python build_standalone_release.py
python -m unittest test_standalone_release -v
```

源码 ZIP 包含本项目源码、构建脚本、测试与固定版本上游源码归档。运行 wheel 中保留许可和真实权限声明。
新包确实包含原生库、子进程及网络操作；不能沿用旧版“无 DLL、无进程启动”的声明或风险评级。

## 验证记录（2026-11-03）

- Python 3.12（Orca 自带）与 Python 3.13：各 **332 项**测试通过。
- 中英文页面工作流：**97 项**通过。
- 私有进程模拟 SDK：AMS/外挂字段、稀疏耗材映射、重复指令回执、脱敏、中文长路径、目录独占、关闭和断连通过；组件安装目录和账号目录同时超过 260 字符且包含中文也已验证。
- 包内真实 SDK：空白账号目录启动、未登录快照、正常退出通过；未读取宿主配置回退位置。
- 可安装 wheel 的文件哈希、平台声明、权限声明、模块导入和模拟宿主启停通过。

这些是离线／未登录测试，不代表以下实机验证已经完成：

1. 国区和全球区收取验证码、登录、过期重登、退出及重启恢复。
2. 插件、Orca 和 Handy 同时在线，断线重连不互相影响。
3. 同一 3MF 原生打印对照 AMS 1–4、外挂、多耗材、跨盘备用槽与校准选项。
4. 两盘 A1 完成→换盘→下一盘，以及 P1S 人工清板继续。
5. 跳过部分／最后一个零件；结束本盘继续、停止整个队列、Handy 外部停止后的恢复。
6. 发送过程中断网、组件崩溃、重载与重启：不重复打印，不凭陈旧 100% 判定完成。

上述结果通过前，测试包不作为无人值守正式版发布。

## English

**0.8.0a1 / 20261103.4** is a locally built installable preview, not a validated public release.
One wheel includes the UI, scheduler, a private child process, pinned Open Bamboo networking code and compatible Microsoft runtimes. Users do not need a separate server, installer or Open Bamboo plugin.

Install through Orca’s plugin manager after pausing/reconciling and disabling the old queue. Sign in with an email/SMS code in the plugin. Keep the printer in cloud mode. Existing networking files are untouched; old `v3` queues are separate from `v4-cloud`.

Windows x64 only, Windows 10 1903+. Session files have a private current-user/SYSTEM ACL and are **not encrypted**. No credentials are discovered from other plugins. Process communication uses private pipes, not a local HTTP service. Lost command responses are not replayed automatically.

Python 3.12 and 3.13 each passed 332 offline tests; 97 UI flows passed. A blank-session smoke test of the real core passed. Real cloud login, simultaneous Handy use, AMS printing and automatic plate swaps still require supervised acceptance testing. macOS/Linux builds are not included.

### 20261103.2 安装修复 / Installation fix

修复 Orca 2.5.0-rc 拒绝平台通用 Python 标签的问题；安装包明确声明已测试的 CPython 3.12 / 3.13 和 Windows x64。此前失败发生在安装前检查，未进入登录或设备连接。

The wheel now declares explicit CPython 3.12 / 3.13 Windows x64 tags accepted by Orca’s installer. The previous package failed pre-install inspection, before account or printer access.

### 20261103.3 重启授权修复 / Restart permissions

Orca 已保存的权限无需手工清除。短路径登录目录现在使用普通路径访问，避免被误判为插件目录外写入；私有组件的启动命令保持固定，父进程编号通过私有环境变量传入，退出保护不变。权限声明与实际启动命令一致。首次安装或授权范围变化仍由 Orca 提示用户确认。

Short session paths now retain the host-allowed spelling. The exact private-component command line stays stable across restarts; the parent process ID travels via a private environment variable, consumed before networking loads. Initial or changed permissions still require user consent. No permission database is edited by the plugin.

### 20261103.4 短信校验与授权恢复 / SMS validation and permission recovery

中国区短信验证码请求先从 `https://bambulab.cn/api/csrf` 获取独立的临时校验 Cookie，再向同一网站的短信端点提交对应 Cookie 和请求头。不读取浏览器或 Orca 登录信息，不绕过网页安全挑战，错误响应仅用于分类，不记录账号、验证码、Cookie 或响应正文。无账号空请求实测从缺少 Cookie 的 HTTP 403 变为参数缺失的 HTTP 400；真实短信发送及登录仍待用户验证。

首次授权后后台操作可能已被 Orca 中止：同意后点“连接说明 → 重新连接”，无需反复重启或重装。读、写管道是两项不同授权，弹窗都可能显示 `open`；权限随插件保存，重新安装会由 Orca 重新审核。授权恢复现在显示明确操作提示；未登录的重新连接成功后显示“请登录 Bambu Cloud”。

CN SMS requests now acquire a fresh anonymous CSRF cookie from the website and submit its matching header only to that website. Cookies remain in memory and are never sent to API login. Anonymous empty-request verification changed from missing-cookie HTTP 403 to expected invalid-parameter HTTP 400; real SMS delivery and login remain unverified. After accepting an interrupted background operation, use Reconnect; no restart is needed. Read/write pipe grants are separate and reinstallation triggers Orca's permission review again.
