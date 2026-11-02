"""Small plugin-wide UI preferences, independent of printer queues."""
from local_paths import fs_path, canonical_path, replace_file
import json
import os
from pathlib import Path
import uuid


class PagePreferences:
    LANGUAGES = ('zh-CN', 'en')

    def __init__(self, storage):
        self.path = Path(storage) / 'page-preferences.json'
        self.language = 'zh-CN'
        self.revision = 0
        try:
            saved = json.loads(fs_path(self.path).read_text(encoding='utf-8'))
            if isinstance(saved, dict) and saved.get('language') in self.LANGUAGES:
                self.language = saved['language']
        except PermissionError:
            raise  # Let the page offer retry after the host grants access.
        except (OSError, UnicodeError, ValueError):
            pass

    def set_language(self, language):
        if not isinstance(language, str) or language not in self.LANGUAGES:
            raise ValueError('不支持此界面语言。')
        if self.language == language:
            return
        fs_path(self.path.parent).mkdir(parents=True, exist_ok=True)
        pending = self.path.with_name(self.path.name + '.pending-' + uuid.uuid4().hex)
        try:
            with fs_path(pending).open('w', encoding='utf-8') as stream:
                json.dump({'language': language}, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            replace_file(pending, self.path)
        finally:
            fs_path(pending).unlink(missing_ok=True)
        self.language = language
        self.revision += 1
