# 网页登录实现与验收边界 / Browser sign-in

本地预览版本：0.8.0a1，构建 20261103.6。尚未公开发布。

## 登录方式

1. 在“打印队列 → 连接说明”选择中国大陆或全球区，点击“准备网页登录”。
2. 点击“打开拓竹官方登录页”。内嵌窗口不能打开时，复制页面提供的链接到浏览器。
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
