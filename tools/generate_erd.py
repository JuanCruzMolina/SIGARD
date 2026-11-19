"""Generate the entity-relationship model of both SIGARD databases from their migrations.

- Public API database: the Alembic chain (`backend/alembic.ini`) is rendered in offline mode
  (`upgrade head --sql`, PostgreSQL dialect). Nothing connects to a database.
- Research database: its migrations (`backend/alembic-epidemiology.ini`, epi01…epi15) execute
  SQL through the connection and cannot run offline, so the SQL they apply is collected in
  revision order: the `backend/database/epidemiology/*.sql` files each one reads plus the SQL
  embedded in the migration source.

The DDL is parsed (tables, columns, primary and foreign keys, later ALTER/DROP) and written as
Mermaid diagrams to docs/tecnica/modelo-datos.md. `--check` fails if that file is outdated.
Run with the backend environment from the repository root:
    .\\backend\\.venv\\Scripts\\python.exe -B tools/generate_erd.py [--check]
"""
import argparse
import ast
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'backend'
OUTPUT = ROOT / 'docs/tecnica/modelo-datos.md'
EPI_SCHEMAS = ('ingestion', 'epidemiology', 'territory', 'analytics')


def public_sql():
    # Offline rendering only: placeholder settings and an unreachable URL; nothing connects.
    env = {**os.environ, 'SECRET_KEY': 'offline-rendering-placeholder-not-a-secret-0123456789',
           'DATABASE_URL': 'postgresql://offline@127.0.0.1:1/offline', 'PYTHONPATH': str(BACKEND), 'PYTHONIOENCODING': 'utf-8'}
    result = subprocess.run([sys.executable, '-B', '-m', 'alembic', '-c', str(BACKEND / 'alembic.ini'), 'upgrade', 'head', '--sql'],
                            cwd=BACKEND, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if result.returncode:
        raise SystemExit(f'Alembic offline falló:\n{result.stderr[-2000:]}')
    return result.stdout


def epidemiology_sql():
    parts = []
    for migration in sorted((BACKEND / 'epidemiology_migrations/versions').glob('*_epi*.py')):
        source = migration.read_text(encoding='utf-8')
        found = []
        for match in re.finditer(r"database/epidemiology/(\d{3}_[a-z_]+\.sql)", source):
            found.append((match.start(), (BACKEND / 'database/epidemiology' / match.group(1)).read_text(encoding='utf-8')))
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and re.search(r'\b(CREATE|ALTER|DROP)\s+TABLE\b', node.value, re.I):
                found.append((node.col_offset + 10 ** 6 * node.lineno, node.value))
        parts.extend(sql for _, sql in sorted(found, key=lambda item: item[0]))
    return '\n;\n'.join(parts)


def statements(sql):
    sql = re.sub(r'--[^\n]*', '', sql)
    sql = re.sub(r'\$([A-Za-z_]*)\$.*?\$\1\$', "''", sql, flags=re.S)  # function bodies
    sql = re.sub(r"'(?:[^']|'')*'", "''", sql)                          # string literals
    return [s.strip() for s in sql.split(';') if s.strip()]


def split_top(body):
    items, depth, current = [], 0, ''
    for char in body:
        depth += char == '('
        depth -= char == ')'
        if char == ',' and depth == 0:
            items.append(current.strip()); current = ''
        else:
            current += char
    if current.strip(): items.append(current.strip())
    return items


NAME = r'"?([A-Za-z_][\w]*)"?(?:\."?([A-Za-z_][\w]*)"?)?'


def qualified(match, default_schema):
    first, second = match
    return (first, second) if second else (default_schema, first)


def columns_of(text):
    return [c.strip().strip('"') for c in text.split(',')]


def simple_type(definition):
    word = re.match(r'([A-Za-z_]+)', definition)
    kind = (word.group(1) if word else 'value').lower()
    return {'character': 'varchar', 'double': 'float', 'timestamp': 'timestamp'}.get(kind, kind)


class Model:
    def __init__(self, default_schema):
        self.default = default_schema
        self.tables = {}

    def table(self, key):
        return self.tables.setdefault(key, {'columns': {}, 'pk': set(), 'fks': []})

    def column(self, table, item):
        match = re.match(r'"?([A-Za-z_]\w*)"?\s+(.*)$', item, re.S)
        if not match: return
        name, rest = match.groups()
        table['columns'][name] = simple_type(rest)
        if re.search(r'\bPRIMARY\s+KEY\b', rest, re.I): table['pk'].add(name)
        ref = re.search(r'\bREFERENCES\s+' + NAME + r'\s*(?:\(([^)]*)\))?', rest, re.I)
        if ref: table['fks'].append(([name], qualified(ref.group(1, 2), self.default_for(table)), columns_of(ref.group(3) or 'id')))

    def default_for(self, table):
        return next(key for key, value in self.tables.items() if value is table)[0]

    def constraint(self, table, item):
        body = re.sub(r'^CONSTRAINT\s+"?\w+"?\s+', '', item, flags=re.I)
        pk = re.match(r'PRIMARY\s+KEY\s*\(([^)]*)\)', body, re.I)
        if pk: table['pk'].update(columns_of(pk.group(1))); return True
        fk = re.match(r'FOREIGN\s+KEY\s*\(([^)]*)\)\s*REFERENCES\s+' + NAME + r'\s*(?:\(([^)]*)\))?', body, re.I)
        if fk:
            table['fks'].append((columns_of(fk.group(1)), qualified(fk.group(2, 3), self.default_for(table)), columns_of(fk.group(4) or 'id')))
            return True
        return bool(re.match(r'(UNIQUE|CHECK|EXCLUDE)\b', body, re.I))

    def apply(self, statement):
        create = re.match(r'CREATE\s+(?:UNLOGGED\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?' + NAME + r'\s*\((.*)\)\s*(?:PARTITION|INHERITS|WITH|$)', statement, re.I | re.S)
        if create:
            key = qualified(create.group(1, 2), self.default)
            if key[1] == 'alembic_version': return
            table = self.table(key)
            for item in split_top(create.group(3)):
                if not self.constraint(table, item): self.column(table, item)
            return
        drop = re.match(r'DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?' + NAME, statement, re.I)
        if drop:
            self.tables.pop(qualified(drop.group(1, 2), self.default), None); return
        alter = re.match(r'ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:ONLY\s+)?' + NAME + r'\s+(.*)$', statement, re.I | re.S)
        if alter:
            key = qualified(alter.group(1, 2), self.default)
            if key not in self.tables: return
            table = self.tables[key]
            for action in split_top(alter.group(3)):
                add_column = re.match(r'ADD\s+(?:COLUMN\s+)?(?:IF\s+NOT\s+EXISTS\s+)?(?!CONSTRAINT|PRIMARY|FOREIGN|UNIQUE|CHECK)(.*)$', action, re.I | re.S)
                add_constraint = re.match(r'ADD\s+(CONSTRAINT.*|PRIMARY.*|FOREIGN.*|UNIQUE.*|CHECK.*)$', action, re.I | re.S)
                drop_column = re.match(r'DROP\s+COLUMN\s+(?:IF\s+EXISTS\s+)?"?(\w+)"?', action, re.I)
                if add_constraint: self.constraint(table, add_constraint.group(1))
                elif add_column: self.column(table, add_column.group(1))
                elif drop_column:
                    table['columns'].pop(drop_column.group(1), None)
                    table['fks'] = [fk for fk in table['fks'] if drop_column.group(1) not in fk[0]]


def parse(sql, default_schema):
    model = Model(default_schema)
    for statement in statements(sql):
        model.apply(statement)
    return model.tables


def entity(key, local_schema=None):
    schema, name = key
    return name if schema == local_schema else f'{schema}__{name}'


def diagram(tables, keys, local_schema):
    lines = ['```mermaid', 'erDiagram']
    for key in keys:
        table = tables[key]
        fk_columns = {c for cols, _, _ in table['fks'] for c in cols}
        lines.append(f'    {entity(key, local_schema)} {{')
        for column, kind in table['columns'].items():
            marks = ', '.join(m for m, on in (('PK', column in table['pk']), ('FK', column in fk_columns)) if on)
            lines.append(f'        {kind} {column}{" " + marks if marks else ""}')
        lines.append('    }')
    seen = set()
    for key in keys:
        for cols, target, _ in tables[key]['fks']:
            edge = (entity(target, local_schema), entity(key, local_schema), '_'.join(cols))
            if edge in seen: continue
            seen.add(edge)
            lines.append(f'    {edge[0]} ||--o{{ {edge[1]} : "{", ".join(cols)}"')
    lines.append('```')
    return '\n'.join(lines)


def summary(tables, keys):
    rows = ['| Tabla | Columnas | Clave primaria | Referencia a |', '|---|---|---|---|']
    for key in keys:
        table = tables[key]
        targets = sorted({'.'.join(target) for _, target, _ in table['fks']})
        rows.append(f"| `{'.'.join(key)}` | {len(table['columns'])} | {', '.join(sorted(table['pk'])) or '—'} | {', '.join(f'`{t}`' for t in targets) or '—'} |")
    return '\n'.join(rows)


def render():
    public = parse(public_sql(), 'public')
    epi = parse(epidemiology_sql(), 'ingestion')
    out = ['# Modelo de datos (entidad-relación)', '',
           '> **Archivo generado** por `tools/generate_erd.py` a partir de las migraciones. No editar a mano:',
           '> volver a generarlo con `.\\backend\\.venv\\Scripts\\python.exe -B tools/generate_erd.py`. `--check`',
           '> falla si quedó desactualizado.', '',
           'SIGARD usa **dos bases separadas**:', '',
           '| Base | Uso | Migraciones | Origen de este modelo |', '|---|---|---|---|',
           '| API pública (PostgreSQL/PostGIS; SQLite en demos y pruebas) | Reportes ciudadanos, cuentas, contenido preventivo, alertas internas, publicación | `backend/migrations` (Alembic, 20260819_01…20261114_06) | SQL de `alembic upgrade head --sql` (sin conexión) |',
           '| Investigación (PostgreSQL 16/PostGIS 3, clúster local 55439) | Ingesta SISA, territorio, analítica, consolidación y registro del motor | `backend/epidemiology_migrations` (epi01…epi15) | SQL que aplican esas migraciones, en orden de revisión |',
           '', 'Las dos bases no comparten tablas ni conexiones. Los modelos y la API de investigación leen paquetes',
           'offline verificados por hash, no estas tablas en línea. Las vistas no se incluyen en los diagramas.', '',
           f'## 1. Base de la API pública ({len(public)} tablas)', '']
    keys = sorted(public)
    out += [diagram(public, keys, 'public'), '', summary(public, keys), '']
    out += [f'## 2. Base de investigación ({len(epi)} tablas en {len({k[0] for k in epi})} esquemas)', '',
            'Un diagrama por esquema. Las entidades de otro esquema aparecen como `esquema__tabla`.', '']
    for number, schema in enumerate(sorted({k[0] for k in epi}, key=lambda s: (EPI_SCHEMAS + (s,)).index(s)), start=1):
        keys = sorted(k for k in epi if k[0] == schema)
        out += [f'### 2.{number} Esquema `{schema}` ({len(keys)} tablas)', '', diagram(epi, keys, schema), '', summary(epi, keys), '']
    return '\n'.join(out).rstrip() + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--check', action='store_true')
    content = render()
    if parser.parse_args().check:
        current = OUTPUT.read_text(encoding='utf-8') if OUTPUT.exists() else ''
        if current.replace('\r\n', '\n') != content:
            raise SystemExit('docs/tecnica/modelo-datos.md está desactualizado: volver a generarlo')
        print('modelo-datos.md al día')
        return
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(content, encoding='utf-8', newline='\n')
    print(f'{OUTPUT.relative_to(ROOT)} generado')


if __name__ == '__main__':
    main()
