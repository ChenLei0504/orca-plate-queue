"""Check the real runtime module boundaries; no printers or accounts."""
import ast
from pathlib import Path
import unittest
from build_public_release import runtime_entries

class SplitRuntimeTests(unittest.TestCase):
    def test_no_process_dynamic_code_environment_or_installer_access(self):
        banned={'subprocess','runpy','connection_components','winreg','socket','http','urllib','requests'}
        for name,data in runtime_entries().items():
            if not name.endswith('.py'):continue
            for node in ast.walk(ast.parse(data.decode(),name)):
                if isinstance(node,(ast.Import,ast.ImportFrom)):
                    modules=[a.name for a in node.names] if isinstance(node,ast.Import) else [node.module or '']
                    self.assertFalse(banned.intersection(m.split('.')[0] for m in modules),(name,modules))
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Name):self.assertNotIn(node.func.id,{'exec','eval','compile','__import__'},name)
                if isinstance(node,ast.Attribute):self.assertNotIn(node.attr,{'environ','getenv','system','popen','spawnl','spawnv'},name)

    def test_native_calls_bind_only_existing_handle(self):
        source=Path(__file__).with_name('native_connection.py').read_text(encoding='utf8')
        calls=[n for n in ast.walk(ast.parse(source)) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='CDLL']
        self.assertEqual(len(calls),1);self.assertEqual(calls[0].args[0].value,'');self.assertEqual(calls[0].keywords[0].arg,'handle')
        self.assertNotIn('GetModuleFileNameW',source)

    def test_runtime_modules_have_no_installation_paths(self):
        for name,data in runtime_entries().items():
            if not name.endswith('.py'):continue
            for forbidden in ('APPDATA','BUNDLED_CONNECTION_ROOT','ConnectionComponents','queue-connection-backups','bambu_network_create_agent'):
                self.assertNotIn(forbidden,data.decode(),name)

if __name__=='__main__':unittest.main()
