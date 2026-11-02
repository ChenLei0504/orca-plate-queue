"""Windows long-path handling at file-I/O boundaries, not in saved identities.

Embedded Python inherits the host's Win32 manifest. Explicit extended paths work
even when that host has not opted into longPathAware. Public metadata stays in
the normal form, so existing queue records and containment checks are unchanged.
"""
import ntpath
import os
from pathlib import Path


def fs_path(value, *, force=False):
    path = Path(value)
    if os.name != 'nt':
        return path
    text = os.fspath(path)
    if text.startswith(('\\\\?\\', '\\\\.\\')):
        return path
    absolute = ntpath.abspath(text)
    units = len(absolute.encode('utf-16-le', errors='surrogatepass')) // 2
    # Keep ordinary paths inside the host's private-directory audit allow-list.
    # 248 is the legacy directory boundary; longer paths still need Win32 support.
    if not force and units < 248:
        return path
    if absolute.startswith('\\\\'):
        return Path('\\\\?\\UNC\\' + absolute[2:])
    return Path('\\\\?\\' + absolute)


def normal_path(value):
    text = os.fspath(value)
    if os.name == 'nt':
        if text.lower().startswith('\\\\?\\unc\\'):
            text = '\\\\' + text[8:]
        elif text.startswith('\\\\?\\') and len(text) > 6 and text[5:7] == ':\\':
            text = text[4:]
    return Path(text)


def canonical_path(value):
    return normal_path(fs_path(value).resolve())


def replace_file(source, destination):
    os.replace(fs_path(source), fs_path(destination))
