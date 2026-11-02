# Legacy embedded Python path test / 旧式宿主长路径验证

The manifest explicitly sets `longPathAware` to false. The host embeds the Python 3.12 runtime from an Orca installation, reproduces unprefixed long-file creation failure, then runs the fixed-path regression tests. It has no printer SDK or login code and does not change system settings.

清单显式关闭长路径感知；嵌入 Orca 的 Python 3.12，先复现普通路径创建失败，再运行修复回归。所有临时文件位于仓库 `.test-temp`，设备提交使用假传输。

From the repository root in PowerShell / 在仓库根目录执行：

```powershell
$fixtureRoot = (Resolve-Path tools/legacy_path_host).Path
$testOutput = Join-Path (Get-Location) 'verification/path-tests'
New-Item -ItemType Directory -Path $testOutput -Force | Out-Null
$fixtureArgs = @('/nologo','/utf8output','/platform:x64','/target:exe',('/win32manifest:' + (Join-Path $fixtureRoot 'legacy-host.manifest')),('/out:' + (Join-Path $testOutput 'LegacyPythonHost.exe')),(Join-Path $fixtureRoot 'LegacyPythonHost.cs'))
& "$env:WINDIR/Microsoft.NET/Framework64/v4.0.30319/csc.exe" @fixtureArgs
# Supply your actual Orca Python directory / 替换为实际 Orca Python 目录
& (Join-Path $testOutput 'LegacyPythonHost.exe') 'D:/Program Files/OrcaSlicer/python' (Join-Path $fixtureRoot 'verify_legacy_paths.py')
```

This is a developer verification tool, not an installer or a queue plugin. The executable is not distributed inside the queue wheel.
