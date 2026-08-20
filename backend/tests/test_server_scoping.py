import ast
import unittest
from pathlib import Path


class ServerScopingTests(unittest.TestCase):
    def test_server_functions_do_not_shadow_global_os_module(self):
        server_path = Path(__file__).resolve().parents[1] / "app" / "core" / "server.py"
        tree = ast.parse(server_path.read_text(encoding="utf-8"))

        local_os_imports = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for child in ast.walk(node):
                if isinstance(child, ast.Import):
                    if any(alias.name == "os" for alias in child.names):
                        local_os_imports.append((node.name, child.lineno))
                elif isinstance(child, ast.ImportFrom) and child.module == "os":
                    local_os_imports.append((node.name, child.lineno))

        self.assertEqual(local_os_imports, [])


if __name__ == "__main__":
    unittest.main()
