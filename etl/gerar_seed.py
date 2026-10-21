"""Gera UPSERT determinístico e idempotente, SEM DELETE geral nem DROP TABLE.

D1: npx wrangler d1 execute oncovo-db --remote --file db/seed.sql
Só execute após revisar etl/output/revisao.csv, backup e prévia do SQL.
"""
import argparse
import json
import hashlib
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from common import read_jsonl

COLUMNS=('id','source_id','source_url','type','status','title','subtitle','description',
         'city','neighborhood','address','starts_at','ends_at','is_recurring',
         'recurrence_text','price_label','price_type','categories','tags','search_text',
         'rank_score_base','source_label')

def sql_value(value):
    if value is None:return 'NULL'
    if isinstance(value,bool):return '1' if value else '0'
    if isinstance(value,(int,float)):
        if isinstance(value,float):
            import math
            if not math.isfinite(value):raise ValueError('Número não finito')
        return str(value)
    return "'"+str(value).replace("'","''")+"'"

def make_seed(source:Path, target:Path)->int:
    rows=[];seen=set()
    for item in read_jsonl(source):
        if item.get('status')!='published':continue
        if item.get('type') not in ('place','event'):continue
        item_id=item.get('id')
        if not item_id or item_id in seen:raise ValueError(f'ID ausente/duplicado: {item_id}')
        seen.add(item_id);rows.append(item)
    if not rows:raise ValueError('Nenhum item validado. Não gere seed vazio.')
    target.parent.mkdir(parents=True,exist_ok=True)
    version=hashlib.sha256(json.dumps(sorted(rows,key=lambda r:r['id']),sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:16]
    generated=datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat(timespec='seconds')
    with target.open('w',encoding='utf-8') as handle:
        handle.write('-- Gerado por etl/gerar_seed.py. NÃO APAGA tabela. Revisar antes do remoto.\n')
        for row in rows:
            cols=', '.join(COLUMNS)
            vals=', '.join(sql_value(row.get(col)) for col in COLUMNS)
            # Mantém created_at estável e atualiza updated_at em upserts.
            changes=', '.join(f'{col}=excluded.{col}' for col in COLUMNS if col!='id')
            handle.write(f'INSERT INTO search_items ({cols}) VALUES ({vals}) '
                         f'ON CONFLICT(id) DO UPDATE SET {changes}, updated_at=CURRENT_TIMESTAMP;\n')
        for key,value in [('dataset_version',version),('generated_at',generated),('row_count',str(len(rows)))]:
            handle.write('INSERT INTO publication_meta(key,value) VALUES ('+sql_value(key)+','+sql_value(value)+') '
                         'ON CONFLICT(key) DO UPDATE SET value=excluded.value;\n')
        # Não elimina registros históricos, mas corrige validade dos eventos importados.
        handle.write("UPDATE search_items SET status='expired', updated_at=CURRENT_TIMESTAMP "
                     "WHERE type='event' AND status='published' AND "
                     "(starts_at IS NULL OR substr(starts_at,5,1) != '-' "
                     "OR substr(COALESCE(ends_at,starts_at),1,10) < "
                     "substr(datetime('now','-3 hours'),1,10));\n")
    return len(rows)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--input',type=Path,default=Path('etl/output/search_items.jsonl'))
    p.add_argument('--output',type=Path,default=Path('db/seed.sql'))
    arg=p.parse_args()
    print(f'Seed pronto ({make_seed(arg.input,arg.output)} registros): {arg.output}')
