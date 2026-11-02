# Orca Plate Queue

A1 / P1S 独立打印队列插件，Windows x64，适配已验证的 OrcaSlicer 2.5.0 beta。

当前队列版本 **0.7.5**，构建 **20261102.1**。独立连接组件继续使用 **0.7.3**。

0.7.5 修复 Windows Python 3.12+ 绑定已有联网组件时的 TypeError。升级后完整退出并重启 Orca；已经安装匹配连接组件的用户无需重新安装组件。

从本仓库 Releases 下载队列 wheel；初次使用另需安装独立连接组件。A1 使用用户指定的换盘文件，P1S 手动换板；保留 Orca 的 Bambu Cloud / Handy 连接。需要电脑与 Orca 持续运行。

- [安装与使用](发布版说明.txt)
- [连接组件说明](连接组件安装说明.txt)
- [兼容性检查与验证边界](兼容性检查.txt)
- [GitHub 自动发布配置](GitHub自动发布说明.txt)

源码与测试按 AGPL-3.0-or-later 提供。连接组件对应的源码与许可证随独立连接 ZIP 提供。
