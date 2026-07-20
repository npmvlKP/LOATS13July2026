import ast
with open('src/loats/openalgo.py') as f:
    content = f.read()
try:
    ast.parse(content)
    print("Syntax OK")
except SyntaxError as e:
    print(f"Syntax Error at line {e.lineno}: {e.msg}")
    lines = content.split('\n')
    if e.lineno:
        for i in range(max(0, e.lineno-3), min(len(lines), e.lineno+2)):
            print(f"{i+1}: {repr(lines[i])}")