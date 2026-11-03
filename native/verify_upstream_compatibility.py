"""Compare an explicitly selected upstream source/binary set without loading a DLL."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import build_bridge


def signatures(source, abi):
    result = {}
    for path in sorted((source / 'src').glob('abi_*.cpp')):
        text = build_bridge.conditional_source(path.read_text(encoding='utf8'), abi)
        for match in re.finditer(r'OBN_ABI\s+([\w:*& ]+?)\s+((?:bambu_network_|ft_|obn_)\w+)\s*\((.*?)\)\s*\{', text, re.S):
            ret, name, args = match.groups()
            result[name] = (ret.strip(), build_bridge.parameters(args)[0])
        for match in re.finditer(r'^OBN_CB_EXPORT\((bambu_network_\w+),\s*\w+,\s*(\w+)\)', text, re.M):
            result[match[1]] = ('int', 'callback ' + match[2])
    return result


def verify(source, binaries):
    baseline = build_bridge.PROJECT / 'vendor/sources/open-bamboo-networking-b14f880'
    header = 'include/obn/bambu_networking.hpp'
    if (source / header).read_bytes() != (baseline / header).read_bytes():
        raise ValueError('Public ABI header changed; manual parameter/layout review required')
    manifest = json.loads((build_bridge.ROOT / 'compatible-build/components.json').read_text())
    result = {'schema': 1, 'baseline': 'b14f880', 'public_header_identical': True,
              'dll_execution': False, 'real_printer_tested': False, 'series': {}}
    original = build_bridge.SOURCE
    try:
        for key, spec in manifest['series'].items():
            abi = int(spec['abi'].replace('.', ''), 16)
            filename = 'bambu_networking.dll' if spec['abi'] == '02.08.04' else spec['bridge']
            binary = binaries / filename
            if set(build_bridge.exports(binary)) != set(spec['exports']):
                raise ValueError('Export set changed: ' + key)
            if signatures(source, abi) != signatures(baseline, abi):
                raise ValueError('Export signatures changed: ' + key)
            build_bridge.SOURCE = baseline
            before = build_bridge.make_forwarders(spec['exports'], abi)
            build_bridge.SOURCE = source
            if before != build_bridge.make_forwarders(spec['exports'], abi):
                raise ValueError('Forwarding signatures changed: ' + key)
            result['series'][key] = {'file': filename,
                'sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
                'exports': len(spec['exports']), 'signatures_identical': True}
    finally:
        build_bridge.SOURCE = original
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--binaries', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.source, args.binaries)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf8')
    print('PASS: ABI header, exported signatures and four wrapper entries. No native code executed.')
