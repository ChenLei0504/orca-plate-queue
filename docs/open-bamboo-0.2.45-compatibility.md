# Open Bamboo 0.2.45 compatibility record

Queue: 0.7.8, build 20261103.8. Connection adapter: 0.7.5, Windows x64.
This is a local compatibility candidate, not a published or real-printer-qualified release.

## Evidence

- Installed Open Bamboo plugin metadata: 0.2.45.
- Its packaged NOTICE names `persano/open-bamboo-networking` revision `32e31a3f0985ebf481ae738290a7482b92d3072f`.
- That revision was retrieved from the upstream repository for source comparison.
- Public `include/obn/bambu_networking.hpp` is byte-identical to the bridge baseline `b14f880`, including PrintParams and callback types.
- Exported function signatures and generated forwarding declarations match for 02.03.00, 02.08.01 and 02.08.04. The default entry uses 02.08.04.
- Static inspection of the actual installed-plugin package DLLs found no added or missing exports.

| Native binary from plugin 0.2.45 | SHA256 |
| --- | --- |
| bambu_networking_02.03.00.dll | 3ebc185c8e12c847594f836bb2cd70e1af5bd19c703bfe1a57a0bef135c5f2cb |
| bambu_networking_02.08.01.dll | 472e9341f8ca3a5104062093d7e4e056c9fa109ee9eb6b119c14b492bed32435 |
| bambu_networking.dll | f09fe57caeaf798834cda142069de27dc5e90316019b7a579a3cc164f3d4b9ab |

These hashes identify the inspected files. They are not an installer allowlist for future core versions.

## Completed offline checks

1. `native/verify_upstream_compatibility.py`: public header, signatures and export-set comparison; no DLL loading.
2. `native/test_compatible_bridges.py`: four wrapper entries against fake SDKs, covering AMS/external mapping, forwarding, status callbacks, multi-printer isolation, command handling and lifetime.
3. `ConnectionInstallerTests.exe`: installation, readaptation after full/partial updates, old-bridge migration, backups, rollback, restoration, busy-host and incompatible-file rejection.
4. Actual 0.2.45 DLL copies were installed and restored only in isolated fixture directories. Backend and restored entry hashes exactly match the originals. Real networking DLLs were not executed.

## Installation model

The adapter preserves the installed compatible core as `orca_queue_backend_*.dll` and installs a matching forwarding entry. It does not modify Open Bamboo Python code, account settings, camera binaries or queue files. No private cloud login is added. It still changes the networking entry DLL, so Open Bamboo can report a different entry hash.

First finish Install / Update Library inside Open Bamboo. Then exit Orca and run Check / Install / Readapt in the adapter. The Open Bamboo plugin version shown in the plugin list does not prove its current native core has been installed. After future updates replace the entry, readaptation is necessary.

The 0.2.45 source supports `cloud_for_makerworld_only` and `lan_only`, which can refuse this queue's cloud submission of custom files. The adapter does not override these choices. Current queue transport requires a compatible cloud-print policy such as `cloud_only`; LAN-direct queue submission is not added here.

## Remaining acceptance

Real Orca connection and temperatures, AMS feed on a user-started small plate, Handy simultaneously online, completion detection, object skipping and A1 swap/next-task continuation remain pending. Offline tests do not replace these checks.

## Reproduce

Run `python native/verify_upstream_compatibility.py --source <32e31a3-source> --binaries <0.2.45-bin/win_x64> --output <report.json>` after building the adapter manifest.
Build/fixture commands are in `兼容适配器说明.txt`. Preferred source and original baseline source/notices are included in the connection ZIP.

Source: https://github.com/persano/open-bamboo-networking/tree/32e31a3f0985ebf481ae738290a7482b92d3072f
