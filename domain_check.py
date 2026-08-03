"""Domain validation scan for LOATS13July2026."""
import pathlib
src = pathlib.Path('src/loats')
files = list(src.rglob('*.py'))
print('Total src files:', len(files))

def has(text, token):
    return token.lower() in text.lower()

dec_used = [f.name for f in files if 'from decimal import' in f.read_text(encoding='utf-8') or 'import decimal' in f.read_text(encoding='utf-8')]
print('Files using Decimal:', len(dec_used), dec_used)

aware = [f.name for f in files if 'datetime.now(tz' in f.read_text(encoding='utf-8') or 'datetime.now(timezone' in f.read_text(encoding='utf-8') or 'timezone.utc' in f.read_text(encoding='utf-8')]
print('Files with TZ-aware datetime:', len(aware), aware)

paper = [f.name for f in files if has(f.read_text(encoding='utf-8'), 'paper')]
print('Files referencing paper-trading:', len(paper), paper)

audit = [f.name for f in files if has(f.read_text(encoding='utf-8'), 'audit')]
print('Files referencing audit:', len(audit), audit)

risk = [f.name for f in files if has(f.read_text(encoding='utf-8'), 'risk')]
print('Files referencing risk:', len(risk), risk)

sebi = [f.name for f in files if has(f.read_text(encoding='utf-8'), 'sebi')]
print('Files referencing SEBI:', len(sebi), sebi)

kill = [f.name for f in files if 'kill_switch' in f.read_text(encoding='utf-8') or 'kill switch' in f.read_text(encoding='utf-8').lower()]
print('Files referencing kill_switch:', len(kill), kill)

struct = [f.name for f in files if 'jsonlogger' in f.read_text(encoding='utf-8').lower() or 'JsonFormatter' in f.read_text(encoding='utf-8')]
print('Files using structured logging:', len(struct), struct)

rate = [f.name for f in files if has(f.read_text(encoding='utf-8'), 'rate_limit')]
print('Files referencing rate_limit:', len(rate), rate)

circ = [f.name for f in files if 'circuit' in f.read_text(encoding='utf-8').lower()]
print('Files referencing circuit:', len(circ), circ)
