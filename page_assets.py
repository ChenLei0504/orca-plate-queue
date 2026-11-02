"""Read only this package's own page assets. No remote page or generated code."""
from local_paths import fs_path, canonical_path, replace_file
from pathlib import Path

_assets = canonical_path(Path(__file__).parent)
QUEUE_PAGE_HTML = fs_path(_assets / 'plugin_page.html').read_text(encoding='utf8')
QUEUE_PAGE_HTML = QUEUE_PAGE_HTML.replace('<link rel="stylesheet" href="plugin_page.css">',
    '<style>\n' + fs_path(_assets / 'plugin_page.css').read_text(encoding='utf8') + '\n</style>')
for _name in ('page_messages.js','page_i18n.js','plugin_page.js'):
    QUEUE_PAGE_HTML = QUEUE_PAGE_HTML.replace('<script src="'+_name+'"></script>',
        '<script>\n' + fs_path(_assets / _name).read_text(encoding='utf8') + '\n</script>')
