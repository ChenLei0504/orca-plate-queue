# 网页登录实现与验收边界 / Browser sign-in

本地预览版本：0.8.0a1，构建 20261103.7。尚未公开发布。

## 登录方式

1. 在“打印队列 → 连接说明”选择中国大陆或全球区，点击“准备网页登录”。
2. 点击“在系统浏览器中登录”。程序明确使用 Windows 默认浏览器打开官网，Orca 队列页面保持不变。若系统浏览器未打开，复制页面提供的链接到 Chrome 或 Edge。
3. 用户只在 `bambulab.cn` 或 `bambulab.com` 官方网页输入账号和验证码。
4. 官网通过短时票据返回本机回调；队列交给自己包内固定版本的 Open Bamboo 核心兑换会话。
5. 返回 Orca，等待设备出现后核对 A1 / P1S、AMS 和 Handy 是否同时正常在线。

此流程不共享 Orca 的既有登录。当前宿主的 `app_info()` 可以报告是否登录 Bambu，但没有公开的会话交接接口。队列不读取宿主账号文件，也不修改或注入已安装 Open Bamboo。

## 实现约束

- `browser_login.py` 只监听 `127.0.0.1` 的随机端口；每次使用 256 位随机路径。显式申请本机网络权限。
- 每次接收器最多存一张票据。有效期五分钟；完成、取消、重新连接或卸载插件时关闭。
- 回调检查 Host、路径、大小和有效期；片段票据在本机页面转为同源 POST，另行检查 Origin。禁止缓存和引用来源泄露；不记录请求 URL。
- 登录票据不进入队列数据、页面状态或错误正文。原生进程通过私有管道接收票据，每个 agent 只兑换一次。失败不自动重试。
- 会话仍由私有联网核心保存在插件目录，使用当前 Windows 用户和 SYSTEM 的 ACL，尚未加密。
- 有活动／未核对任务时仍禁止切换账号；新流程没有新增打印控制入口。
- `cloud_login.py` 暂留源码和旧测试以记录问题，不进入独立 wheel，不再由页面或连接 provider 使用。

## 依据

- [Orca 的网页登录处理](https://github.com/OrcaSlicer/OrcaSlicer/blob/af2ffb8c/src/slic3r/GUI/WebUserLoginDialog.cpp)：浏览器登录及 ticket 处理。宿主自身能力不等于公开 Python 插件能力。
- [Orca 的插件宿主接口](https://github.com/OrcaSlicer/OrcaSlicer/blob/af2ffb8c/src/slic3r/GUI/PluginHostApp.cpp)：用于核对公开的信息接口。
- [Open Bamboo 核心](https://github.com/ClusterM/open-bamboo-networking)：本项目固定 b14f880；`abi_user.cpp` 提供票据兑换，`Agent::apply_login_info` 接收原始令牌响应并处理用户信息。
- [bambu-gateway 的浏览器登录 URL](https://github.com/leolobato/bambu-gateway/blob/main/app/cloud/auth.py)：参考其双层官方 sign-in / callback 参数。本项目改为随机本机回调地址，不使用其固定端口和手动粘贴票据接口。

## 尚待真实验证

离线测试可以证明回调隔离、生命周期、私有管道交接与错误处理，不能证明官方网页在两个地区都接受当前随机回调 URL，也不能证明账号授权、票据兑换、设备联网和 Handy 并发已经成功。

先由用户完成一次网页登录；若页面拒绝或没有返回，应记录错误阶段，继续核对官方网页行为，不用匿名请求成功代替登录验收。不要把含票据的完整回调地址发到公开 Issue。

## English

Open Print Queue → Connection guide, choose a region, and prepare browser sign-in. Open the official Bambu link, enter credentials only there, and return to Orca. A five-minute loopback receiver hands a single ticket to the plugin’s private, pinned networking core. No separate server installation is needed.

Orca’s current public plugin API does not hand over its signed-in session. This feature uses the same kind of official browser/ticket flow, not Orca credential discovery. Offline tests cover callbacks and the private process using a simulated backend. Acceptance of the random callback URL by both regional websites, real account login, device connectivity and simultaneous Handy operation remain unverified.

### 20261103.7：系统浏览器入口 / System-browser launch

已确认的宿主行为：Orca 2.5.0-rc 的 `PluginPage::on_new_window` 对新窗口链接调用 `browser()->LoadURL(url)`，因此 `target="_blank"` 会覆盖插件页面。普通页面测试并不能模拟这一宿主行为。用户看到的无地址栏登录页面与此问题相符；官网完成认证并不代表队列已接收票据。

新入口是按钮，向私有组件发送专用 `open_login_browser` 动作。未初始化 SDK 的临时私有组件用 Windows `ShellExecuteW` 打开系统默认浏览器，随后退出，避免浏览器继承联网核心重定向后的 APPDATA；只根据当前地区、本机随机端口和随机路径生成拓竹 HTTPS 登录地址，不接受任意 URL、文件路径或命令行。只在用户点击时打开，不会在轮询、启动或重连时自动打开。失败保留复制链接备用方式。

原生测试构建禁用真实浏览器启动，核对国区／全球区目的地址和无效参数拒绝；页面测试核对按钮不会导航、不会传入 URL 或认证资料。原生构建与权限声明已同步。真实官网回调、会话保存与重启恢复仍待用户验收，未以离线测试代替。

[Orca 宿主源码](https://github.com/OrcaSlicer/OrcaSlicer/blob/af2ffb8c/src/slic3r/plugin/host/PluginPages.cpp#L132)

Orca’s plugin page redirects new-window links into its own WebView. The preview now uses a dedicated button and a fixed-purpose native launcher to open the system default browser without navigating away from the queue. Only generated Bambu HTTPS URLs are accepted. Launch failures preserve the manual copy fallback. Browser sign-in and session restoration still require real-account validation.
