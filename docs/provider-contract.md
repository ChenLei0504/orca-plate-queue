# 独立队列连接接口（开发草案） / Independent queue provider API

**状态：我们一侧的独立 DLL 原型和 Python 接入已实现，虚拟宿主测试通过。Orca / Open Bamboo 尚未实现此接口，不能直接用于真实打印。**

这是一份拟议接口，不是对上游现有功能的描述。没有向上游发送 Issue / PR，也没有把原型安装到用户 Orca 中。现有兼容适配器继续作为过渡方案；云端下载和版本号不变。

## 目标与边界

- 独立文件 `orca_plate_queue.dll`，由支持此接口的宿主明确加载；不覆盖或改名 `bambu_networking*.dll`。
- 复用宿主当前连接。队列不读取登录凭据，不另建云端会话，不接管原有状态回调。
- 独立 DLL 不使用 Open Bamboo 的 C++ 类、结构体布局或导出函数；通过 C 函数表和 UTF-8 JSON 与宿主通信。
- 多打印机由一个 provider 管理，通过设备 ID 区分；不是每台打印机注册一个 provider。
- 打印参数和 AMS / 外挂映射字节原样转交 provider。由宿主适配层按原生打印流程转换和校验，不能因为映射不支持而静默改为外挂。
- 当前队列协议仍要求复用云端连接。独立 DLL 本身可编译到其他系统，不代表整个队列插件已兼容 macOS / Linux，也不代表已新增局域网直连。

## 架构

```text
队列 UI / 调度 / 换盘流程
        ↓ 现有快照与命令协议
native_connection.py
        ↓ 只绑定宿主已经加载的模块
orca_plate_queue.dll（独立文件）
        ↓ 宿主主动注册的 C 函数表
Orca 或 Open Bamboo 的宿主适配层（待上游实现）
        ↓ 已有会话、状态分发、原生打印入口
打印机
```

当前旧路径仍然可用：队列 → 转发桥接 → 已保留的 Open Bamboo 核心。两个路径不能同时作为活动入口：发现两者都已接入时，队列拒绝选择，以免重复发送。未接入的独立 DLL 不妨碍旧桥接工作。

## 接口文件与加载

- [C 头文件](../native/queue_provider_api.h)：拟议 provider ABI。
- [独立 DLL 实现](../native/queue_sidecar.cpp)：注册、转发、解绑，不包含联网实现。
- [虚拟宿主测试](../native/test_sidecar.cpp)：不访问真实 SDK、账号或打印机。
- [Python 接入](../native_connection.py)：识别已加载的 `orca_plate_queue.dll`，继续支持旧桥接。

宿主应从自己的已授权安装位置加载模块，不能搜索任意当前目录。加载及注册不能在 Windows `DllMain` 中执行。Python 队列只查找已加载模块，不扫描插件目录、下载 DLL 或主动加载文件。独立 DLL 名称固定不等于加载权限已解决，宿主还需完成包管理与权限接入。

## ABI v1

`OrcaQueueProviderV1` 使用 C 调用约定、固定宽度整数和本机指针对齐。Windows 为 `__cdecl`。禁止自定义结构体 packing，禁止跨 DLL 传递 `std::string`、`std::function` 或让另一侧释放内存。

| 字段 | 要求 |
| --- | --- |
| `struct_size` | 至少为当前结构体大小；未来追加字段另行约定 |
| `abi_version` | 1 |
| `queue_contract_version` | 1，表示完整实现下述 JSON 语义 |
| `material_mapping_revision` | 2；当前不接受其他值，不能仅凭“版本更大”推断兼容 |
| `context` | 宿主拥有的对象指针，可为空；独立 DLL 不解引用 |
| `snapshot` / `refresh` / `command` | 都必须提供 |
| `reserved[4]` | 全部为 0 |

注册：`orca_queue_register_provider_v1(&provider, &token)`。成功返回 0，并给出非零的进程内注册标记。重复注册返回 -10；无效参数/版本返回 -2。不接受第二个活动 provider。

解绑：`orca_queue_unregister_provider_v1(token)`。成功返回 0，过期/不匹配标记返回 -11。成功后，没有 provider 回调仍在执行。旧 token 不能解除后来建立的注册。

消费者继续使用 `obn_queue_abi_version_v1`、`obn_queue_material_revision_v1`、`obn_queue_snapshot_v1`、`obn_queue_refresh_v1` 和 `obn_queue_command_v1`。保留名称用于兼容现有队列，不意味着 DLL 依赖 Open Bamboo。

未注册时，快照明确返回 `attached:false`、`can_submit:false`、空设备列表；耗材映射能力返回 0，命令拒绝执行。不通过“DLL 已加载”推断连接成功。

## 线程、内存和生命周期

1. 独立 DLL 串行调用 provider 的函数。回调不得再次调用注册、解绑、快照或命令接口，也不能等待正在等待本次调用的 UI 线程。
2. `snapshot` 只读取内存缓存；`refresh` 和 `command` 只校验并入队，不等待网络、上传、打印完成或 UI 确认。
3. 输入缓冲区只在调用期间有效。异步任务必须在返回前复制命令和文件路径；不能保存裸指针。
4. 不允许异常跨 C ABI。原型额外捕获 C++ 异常并返回 -12，但不能恢复坏指针或访问冲突。
5. 宿主先禁止新任务，再解绑，再处理自己的异步任务退出与回调注销，最后释放 context。解绑只等待正在执行的同步接口，**不会取消已开始的打印或自动排空宿主上传线程**。
6. 独立 DLL 在 Python 消费者仍可能调用时不能卸载；首版建议一直保留到 Orca 进程退出。登录退出只改变状态，不需要卸载 DLL。
7. provider 重建后必须更换状态监控 epoch，队列核对任务身份后恢复；不能把上一次连接缓存伪装为新状态，也不能自动重放未确认命令。

## 快照与命令协议 v1

这是现有队列 JSON 协议的显式约定，不是透传任意原始 MQTT 数据。参考 [快照生成](../native/queue_cache.cpp)、[命令处理](../native/queue_commands.inc) 和 [Python 校验](../printer_connection.py)。上游可以复用这些实现中的逻辑，但不能把其中依赖转发 DLL 的会话取得方式照搬过去。

### snapshot

- 传入 `NULL,0` 查询所需字节数；返回长度包含末尾 NUL。
- 最大 `2 MiB + 1` 字节，UTF-8 JSON。容量不足时返回完整所需长度，不写入部分数据；两次调用之间长度可以改变。
- 顶层 `protocol:1`、`origin:"orca-native-queue"`；只有确实复用宿主云端会话才能返回 `cloud_session_reused:true`。
- `attached` 表示接入宿主，不表示登录或设备在线；登录/连接状态单独提供，`can_submit` 只能反映实际能力。
- 设备使用稳定 ID，提供名称、机型、在线状态、喷嘴、实际耗材槽、支持选项、遥测，以及采集时间对应的 `age_ms` / `state_age_ms`。
- 保留 `monitor_epoch`、状态事件序号、任务事件、任务身份和命令结果记录。不能用刷新页面时间代替设备状态接收时间。
- 不包含登录凭据、令牌、访问码或任意配置文件内容。

### refresh

返回 0 表示刷新已接受，1 表示已在进行。异步更新设备目录和状态缓存，不切换 Orca 当前选择的打印机，不改变 AMS 配置。

### command

输入为不含结束 NUL 的 UTF-8 JSON，长度 1–65536 字节。原型只验证长度并原样转交，provider 必须完成 JSON、业务和任务身份校验。

| 动作 | provider 责任 |
| --- | --- |
| `watch_many` | 按设备 ID 订阅队列关心的设备，保持原生页面订阅与选择 |
| `submit` | 校验设备空闲与状态时效、文件 SHA256、盘号、任务标记、打印选项及完整耗材映射；异步调用原生打印流程 |
| `cancel_submit` | 取消指定上传请求；不能解释为停止任意当前打印 |
| `pause` / `resume` / `stop` | 校验设备和本队列任务身份，不控制其他来源的任务 |
| `skip` | 校验任务身份及零件 ID，等待设备回执更新状态 |

- `request_id` 与内容共同实现幂等：相同请求只能执行一次；同 ID 不同内容必须拒绝。会话内已接受记录不得随意淘汰。
- 接受返回 0，重复且相同返回 1；-3 为 ID 冲突，-4 为发送忙或无法取消，-5 为记录容量耗尽，-6 为设备状态变化，-7 为路径编码问题，-8 为设备/任务身份不匹配。其他负值表示拒绝。
- 接受、上传结束、发送成功、打印完成是不同事件；不能用 SDK 返回成功或进度 100% 代替本任务完成事件。
- `use_ams`、`ams_mapping`、`ams_mapping_info` 和调平/流量校准/延时摄影选项必须一致处理。稀疏耗材列表中的未使用项不能变成外挂选择。
- provider 在宿主侧根据对应 SDK 构造打印参数，避免队列侧绑定 C++ 参数布局。暂不支持的映射/传输方式明确拒绝，不能静默降级。

## 上游需要提供的改动（尚未实现）

1. 宿主加载独立 DLL，并把已有会话包装为上述 provider；原始 agent 指针不暴露给 Python。
2. 在宿主状态分发处增加只读观察者，维护队列缓存；不能直接替换 Orca 原有单一消息回调。
3. 提供异步发送入口，复用原生参数转换、AMS 映射和进度回执；保留请求幂等与任务身份校验。
4. 加入登录退出、连接重建、关闭程序的生命周期处理。
5. 包含接口版本与能力检查，并在上游更新时运行约定测试。

可以由 Orca 实现，也可以由 Open Bamboo 原生库配合实现；仅修改 Open Bamboo 的安装页面不能取得现有会话。若上游不提供这个入口，本方案不能仅靠我们单方面发布 DLL 成为可用连接方案。

## 验证与迁移

本地构建：`python native/build_sidecar.py`。Windows 需 MSVC，可设置 `ORCA_QUEUE_MSVC_ROOT` 指向现有工具链；Linux 构建使用 C++17 编译器。输出位于 `native/sidecar-build/`，仅用于开发验证。

已覆盖：版本/字段检查、单 provider、无宿主时拒绝命令、AMS 与外挂参数原样传递、输出边界、异常处理、解绑等待回调、过期 token，以及 Python 新旧入口选择。

待宿主真正接入后，必须完成：原生连接对比、AMS 各槽/外挂/稀疏耗材、多机状态、完成事件、暂停/跳过/取消、断连恢复，以及 Open Bamboo 更新前后的回归。原型转发测试不等于真实 AMS 进料验收。

正式迁移时先完整退出 Orca，通过旧适配器恢复联网入口，再启用宿主 provider。只在真实接入和验收完成后更换默认安装包；不会让新旧两个活动入口同时发送队列。

## English summary

This is a proposed API and a tested local prototype, **not an interface currently implemented by Orca or Open Bamboo**. The independent DLL preserves the existing queue consumer ABI and accepts an explicitly registered host provider through a versioned C function table. No networking DLL replacement, credential reading, second login, callback interception or C++ SDK layout dependency is introduced.

The host must supply cached snapshots, asynchronous refresh/command handling, complete material mapping, task identity checks, idempotency and lifecycle management. Command bytes pass through unchanged. Registration alone does not prove printer readiness. Missing registration yields an unattached snapshot and rejects commands.

Callbacks are serialized and must not reenter the sidecar or synchronously wait for UI/network work. Successful unregister waits for in-flight callbacks; the host remains responsible for draining asynchronous work. Keep the sidecar loaded while consumers may retain its function pointers.

Windows fake-host tests and Python discovery tests exercise this prototype. A Linux build job tests portable source compilation only; this does not make the whole queue plugin cross-platform or add LAN mode. Real-printer and upstream integration acceptance remain outstanding. The existing compatibility adapter stays the transition path until those are complete.
