"""Integração: resolver A2 → gerar_seed existente → schema D1 sob SQLite local."""
import json
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'etl'))
from resolver_entidades import resolve, jsonl_write
from gerar_seed import make_seed

class SQLiteContractTests(unittest.TestCase):
    def test_resolved_catalog_upserts_idempotently_in_existing_schema(self):
        stamp=datetime(2026,10,22,12,0,tzinfo=ZoneInfo('America/Sao_Paulo'))
        def place(code):
            return {'id':'legacy_'+code,'source_id':code,
                'source_url':f'https://www.instagram.com/p/{code}/',
                'type':'place','status':'published','title':'Café Primavera',
                'subtitle':'Cafeteria','description':'Café e doces',
                'city':'Belo Horizonte','neighborhood':'Savassi','address':'Rua Paraíba, 123',
                'starts_at':None,'ends_at':None,'is_recurring':0,'recurrence_text':None,
                'price_label':'','price_type':'unknown',
                'categories':'["café"]','tags':'["doces"]','search_text':'cafe primavera doces',
                'rank_score_base':87.0,'source_label':'Instagram'}
        resolved=resolve([place('POSTAAAAAA1'),place('POSTAAAAAA2')],now=stamp)
        self.assertEqual(len(resolved['catalog']),1)
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);source=base/'catalog.jsonl';seed=base/'seed.sql'
            jsonl_write(source,resolved['catalog'])
            self.assertEqual(make_seed(source,seed),1)
            sql=seed.read_text()
            self.assertNotIn('DELETE FROM search_items',sql)
            db=sqlite3.connect(':memory:')
            db.executescript((ROOT/'db/schema.sql').read_text())
            db.executescript(sql)
            db.executescript(sql)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM search_items').fetchone()[0],1)
            self.assertEqual(db.execute("SELECT value FROM publication_meta WHERE key='row_count'").fetchone()[0],'1')
            self.assertEqual(db.execute('SELECT source_url FROM search_items').fetchone()[0],
                             resolved['catalog'][0]['source_url'])

if __name__=='__main__':unittest.main()
