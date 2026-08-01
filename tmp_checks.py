import ast
src = open('src/loats/database.py', encoding='utf-8').read()
t = ast.parse(src)
names = []
for n in ast.iter_child_nodes(t):
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        names.append(n.name)
    elif isinstance(n, ast.Assign):
        for tgt in n.targets:
            if isinstance(tgt, ast.Name):
                names.append(tgt.id)
print('db' in names, [n for n in names if n.startswith('db')])
print('LC结束语'[:0], [line.rstrip() for line in src.split(chr(10)) if line.strip().startswith('db')][:10])