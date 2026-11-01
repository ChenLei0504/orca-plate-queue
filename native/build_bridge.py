"""Build typed SDK forwarding DLL with MSVC v142; no injection or guessed ABI.

Signatures come from the exact upstream source revision listed in the
installed networking plugin's NOTICE. Every installed export must match.
"""
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
SOURCE = PROJECT/'vendor/sources/open-bamboo-networking-b14f880'
BACKEND = Path(os.environ['APPDATA'])/'OrcaSlicer/plugins/bambu_networking_02.03.00.dll'
BACKEND_NAME = 'orca_queue_upstream_020300_b14f880.dll'


def exports(path):
    b = path.read_bytes()
    pe = struct.unpack_from('<I', b, 0x3c)[0]
    if b[pe:pe+4] != b'PE\0\0' or struct.unpack_from('<H', b, pe+4)[0] != 0x8664:
        raise ValueError('Expected x64 PE DLL')
    count = struct.unpack_from('<H', b, pe+6)[0]
    opt = pe+24
    osize = struct.unpack_from('<H', b, pe+20)[0]
    sections = [struct.unpack_from('<IIII', b, opt+osize+40*i+8) for i in range(count)]
    def pos(rva):
        return next(rp+rva-va for vs,va,rs,rp in sections if va <= rva < va+max(vs,rs))
    exp = pos(struct.unpack_from('<I', b, opt+112)[0])
    n = struct.unpack_from('<I', b, exp+24)[0]
    names = pos(struct.unpack_from('<I', b, exp+32)[0])
    result = []
    for i in range(n):
        at = pos(struct.unpack_from('<I', b, names+4*i)[0])
        name = b[at:b.index(0,at)].decode('ascii')
        if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', name):
            raise ValueError('Unreviewed decorated export: '+name)
        result.append(name)
    return result


def conditional_source(text, abi=0x020300):
    """Only the simple conditionals present in the pinned ABI source files."""
    stack = []
    active = True
    result = []
    for line in text.splitlines():
        m = re.match(r'\s*#\s*(if|ifdef|ifndef|else|endif)\b(.*)', line)
        if not m:
            if active: result.append(line)
            continue
        kind, expr = m[1], m[2].strip()
        if kind in ('if','ifdef','ifndef'):
            if kind == 'if' and re.fullmatch(r'ABI_VERSION >= 0x[0-9A-Fa-f]+',expr):
                yes = abi >= int(expr.split()[-1],16)
            elif kind == 'if' and expr == 'defined(_WIN32)':
                yes = True
            elif kind in ('ifdef','ifndef') and expr == 'OBN_VERSION_STRING':
                yes = kind == 'ifdef'
            else:
                raise ValueError('Unreviewed ABI conditional: '+line)
            stack.append((active,yes));active = active and yes
        elif kind == 'else':
            outer,yes = stack[-1];active = outer and not yes
        else:
            outer,yes = stack.pop();active = outer
    if stack: raise ValueError('Unbalanced ABI source conditionals')
    return '\n'.join(result)


def parameters(raw):
    # Upstream names unused parameters inside comments; restore only those names.
    raw = re.sub(r'/\*\s*([a-zA-Z_]\w*)\s*\*/', r'\1', raw)
    raw = re.sub(r'/\*.*?\*/', '', raw, flags=re.S)
    parts, start, depth = [], 0, 0
    for i,c in enumerate(raw):
        if c in '<(': depth += 1
        elif c in '>)': depth -= 1
        elif c == ',' and depth == 0:
            parts.append(raw[start:i]);start=i+1
    if raw.strip(): parts.append(raw[start:])
    names = []
    for part in parts:
        match = re.search(r'([a-zA-Z_]\w*)\s*$',part)
        if not match: raise ValueError('Unreviewed parameter: '+part)
        names.append(match[1])
    return re.sub(r'\s+', ' ',raw).strip(), names


def make_forwarders(names, abi=0x020300):
    definitions = {}
    for path in sorted((SOURCE/'src').glob('abi_*.cpp')):
        s = conditional_source(path.read_text(encoding='utf-8'), abi)
        for m in re.finditer(r'OBN_ABI\s+([\w:*& ]+?)\s+((?:bambu_network_|ft_|obn_)\w+)\s*\((.*?)\)\s*\{',s,re.S):
            ret,name,raw = m.groups()
            if name in definitions: raise ValueError('Duplicate ABI definition: '+name)
            definitions[name] = (ret.strip(), *parameters(raw))
        for m in re.finditer(r'^OBN_CB_EXPORT\((bambu_network_\w+),\s*\w+,\s*(\w+)\)',s,re.M):
            definitions[m[1]] = ('int', 'void* agent, BBL::'+m[2]+' fn', ['agent','fn'])
    # The narrow original helper exports live in config.cpp, not an ABI file.
    s = (SOURCE/'src/config.cpp').read_text(encoding='utf-8')
    for m in re.finditer(r'OBN_ABI\s+(int)\s+(obn_ensure_conf_\w+)\s*\((.*?)\)\s*\{',s,re.S):
        definitions[m[2]] = (m[1], *parameters(m[3]))
    custom_source = (ROOT/'queue_bridge.cpp').read_text(encoding='utf-8')
    custom = set(re.findall(r'QB_EXPORT\s+[\w:*& ]+?\s+((?:bambu_network_|ft_|obn_)\w+)\(',custom_source))
    unknown = set(names)-set(definitions)-custom
    if unknown: raise ValueError('Missing source ABI signatures: '+str(sorted(unknown)))
    body = ['// Generated from pinned upstream signatures. Do not edit.']
    for name in names:
        if name in custom: continue
        ret,decl,args = definitions[name]
        typelist = []
        for arg,n in zip(split_params(decl),args):
            typelist.append(re.sub(r'\b'+re.escape(n)+r'\s*$','',arg).strip())
        fallback = 'return;' if ret == 'void' else 'return false;' if ret == 'bool' else 'return {};' if ret in ('std::string','const char*','void*') else 'return static_cast<'+ret+'>(-1);'
        prefix = '' if ret == 'void' else 'return '
        body.append('QB_EXPORT '+ret+' '+name+'('+decl+') {\n'
                    ' try { using Fn = '+ret+' (__cdecl*)('+', '.join(typelist)+');\n'
                    ' static auto upstream_fn = backend_function<Fn>("'+name+'");\n'
                    ' '+prefix+'upstream_fn('+', '.join(args)+'); } catch (...) { '+fallback+' }\n}\n')
    return '\n'.join(body)


def split_params(raw):
    result,start,depth=[],0,0
    for i,c in enumerate(raw):
        if c in '<(': depth+=1
        elif c in '>)': depth-=1
        elif c==',' and depth==0: result.append(raw[start:i]);start=i+1
    if raw.strip(): result.append(raw[start:])
    return result


def compiler_environment():
    msvc = PROJECT/'vendor/msvc'
    vc = next((msvc/'VC/Tools/MSVC').iterdir())
    sdk = msvc/'Windows Kits/10'
    ver = next((sdk/'Include').iterdir()).name
    env = os.environ.copy()
    env['PATH'] = str(vc/'bin/Hostx64/x64')+';'+str(sdk/'bin'/ver/'x64')+';'+env['PATH']
    env['INCLUDE'] = ';'.join(map(str,[vc/'include',sdk/'Include'/ver/'ucrt',sdk/'Include'/ver/'shared',sdk/'Include'/ver/'um']))
    env['LIB'] = ';'.join(map(str,[vc/'lib/x64',sdk/'Lib'/ver/'ucrt/x64',sdk/'Lib'/ver/'um/x64']))
    return env


def main():
    out = ROOT/'build';out.mkdir(exist_ok=True)
    backend=BACKEND
    if 'obn_queue_abi_version_v1' in exports(backend):
        backend=backend.with_name(BACKEND_NAME)
    names = exports(backend)
    if any(n.startswith('obn_queue_') for n in names):
        raise ValueError('Cannot wrap a queue bridge as its own backend')
    (out/'forwarders.inc').write_text(make_forwarders(names),encoding='utf-8')
    shutil.copyfile(backend,out/BACKEND_NAME)
    manifest = dict(protocol=1,source_revision='b14f880',abi='02.03.00',backend=BACKEND_NAME,
                    backend_sha256=hashlib.sha256(backend.read_bytes()).hexdigest(),forwarded_exports=names)
    (out/'bridge-build.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    env = compiler_environment()
    command = [str(Path(env['PATH'].split(';')[0])/'cl.exe'),'/nologo','/std:c++17','/EHsc','/MD','/O2','/utf-8','/W4',
               '/DABI_VERSION=0x020300','/D_ITERATOR_DEBUG_LEVEL=0','/DNOMINMAX',
               '/I'+str(SOURCE/'include'),'/I'+str(out),'/I'+str(ROOT),'/LD',
               str(ROOT/'queue_bridge.cpp'),str(ROOT/'queue_cache.cpp'),str(SOURCE/'src/json_lite.cpp'),
               '/link','/OUT:'+str(out/'bambu_networking_02.03.00.dll')]
    subprocess.run(command,cwd=out,env=env,check=True)
    built = set(exports(out/'bambu_networking_02.03.00.dll'))
    if not set(names)<=built: raise ValueError('Bridge dropped upstream exports')
    print('Built native bridge; preserved '+str(len(names))+' upstream exports.')


if __name__ == '__main__': main()
