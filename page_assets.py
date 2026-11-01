"""Read only this package's own page assets. No remote page or generated code."""
from pathlib import Path

_assets = Path(__file__).resolve().parent
QUEUE_PAGE_HTML = (_assets / 'plugin_page.html').read_text(encoding='utf8')
QUEUE_PAGE_HTML = QUEUE_PAGE_HTML.replace('<link rel="stylesheet" href="plugin_page.css">',
    '<style>\n' + (_assets / 'plugin_page.css').read_text(encoding='utf8') + '\n</style>')
QUEUE_PAGE_HTML = QUEUE_PAGE_HTML.replace('<script src="plugin_page.js"></script>',
    '<script>\n' + (_assets / 'plugin_page.js').read_text(encoding='utf8') + '\n</script>')
