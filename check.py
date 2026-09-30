import ast
from pathlib import Path
src = Path("app.py").read_text(encoding="utf-8")
ast.parse(src)
print("syntax OK")
