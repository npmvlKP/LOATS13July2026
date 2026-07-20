f=open('src/loats/openalgo.py','rb')
d=f.read()
f.close()
import ast, tokenize, io

print('Total bytes:',len(d))
print('First 200 bytes hex:',d[:200].hex())
print()

# tokenize
try:
    tokens=list(tokenize.tokenize(io.BytesIO(d).readline))
    for t in tokens[:20]:
        print(f'{tokenize.tok_name[t.type]:10s}{t.string!r}({t.start},{t.end})')
except SyntaxError as e:
    print('Tokenize failed:',e)
    lines=d.decode('utf-8','replace').split('\n')
    for i in range(max(0,e.lineno-3),min(len(lines),e.lineno+3)):
        print(i+1,repr(lines[i]))
print()

# parse
try:
    ast.parse(d)
    print('Parse OK')
except SyntaxError as e:
    print('Parse failed line',e.lineno)
    print('msg:',e.msg)
    print('offset:',e.offset)
    lines=d.decode('utf-8','replace').split('\n')
    print('Context:')
    for i in range(max(0,e.lineno-3),min(len(lines),e.lineno+3)):
        print(i+1,repr(lines[i]))