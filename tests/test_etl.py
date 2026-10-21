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
from common import event_dates,search_index,canonical_id
from preparar_publicacao import transform,build
from gerar_seed import make_seed

T=ZoneInfo('America/Sao_Paulo')
NOW=datetime(2026,10,20,12,0,tzinfo=T)

def fixture(date_value='2026-10-22',status='published',kind='event'):
    approve={'post_code':'ABCDEFGHIJK','content_type':kind,'publish_status':status,
             'display_title':'Samba no Centro','display_subtitle':'música - samba'}
    ext={'post_code':'ABCDEFGHIJK','extraction_status':'ok','content_type':kind,
         'main_entity':{'name':'Samba no Centro'},
         'event':{'date_start':date_value,'date_end':date_value,'time_start':'19:00','time_end':'23:00'},
         'location':{'city':'Belo Horizonte','neighborhood':'Centro','venue_name':'Bar X'},
         'commercial_info':{'is_free':True},
         'classification':{'category':'música','subcategories':[],'tags':['samba','ao vivo']},
         'quality':{'confidence_overall':.95,'risk_flags':[]}}
    return approve,ext

class ETLTests(unittest.TestCase):
    def test_dates(self):
        starts,ends=event_dates({'date_start':'2026-10-22','time_start':'19:00'})
        self.assertEqual(starts,'2026-10-22T19:00:00-03:00')
        self.assertEqual(ends,'2026-10-22T23:59:00-03:00')
        self.assertEqual(event_dates({'date_start':'22/10'}),(None,None))
        self.assertEqual(event_dates({'date_start':'2026-10-22','time_start':'23:00','time_end':'02:00'}),(None,None))
    def test_expiration_and_review(self):
        a,b=fixture('2026-07-04')
        row,status,_=transform(a,b,NOW)
        self.assertIsNone(row);self.assertEqual(status,'expired')
        a['publish_status']='review';b['event']['date_start']='2026-10-22';b['event']['date_end']='2026-10-22'
        row,status,_=transform(a,b,NOW)
        self.assertIsNone(row);self.assertEqual(status,'review')
    def test_no_promotion_or_multi_event(self):
        a,b=fixture(kind='promotion')
        self.assertEqual(transform(a,b,NOW)[1],'hidden')
        a,b=fixture();b['quality']['risk_flags']=['multiple_events_in_post']
        self.assertEqual(transform(a,b,NOW)[1],'review')
    def test_normalization(self):
        indexed=search_index('Hamburgueria artesanal','Savassi')
        self.assertIn('hamburguer',indexed)
        self.assertIn('burger',indexed)
        self.assertEqual(canonical_id('instagram','a'),canonical_id('instagram','a'))
    def test_seed_idempotent(self):
        a,b=fixture()
        item,status,_=transform(a,b,NOW)
        self.assertEqual(status,'published')
        with tempfile.TemporaryDirectory() as d:
            path=Path(d); inputfile=path/'input.jsonl'; seed=path/'seed.sql'
            inputfile.write_text(json.dumps(item,ensure_ascii=False)+'\n',encoding='utf-8')
            self.assertEqual(make_seed(inputfile,seed),1)
            self.assertNotIn('DELETE FROM search_items',seed.read_text())
            db=sqlite3.connect(':memory:')
            db.executescript((ROOT/'db/schema.sql').read_text())
            db.executescript(seed.read_text())
            db.executescript(seed.read_text())
            self.assertEqual(db.execute('SELECT COUNT(*) FROM search_items').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT price_type FROM search_items').fetchone()[0],'free')
    def test_real_data_if_present(self):
        source=ROOT/'etl/items_publicaveis.jsonl'
        if not source.exists(): self.skipTest('amostra editorial ausente')
        from common import read_jsonl
        records=list(read_jsonl(source))
        self.assertEqual(len(records),100)
        self.assertGreaterEqual(len({r['post_code'] for r in records}),98)

if __name__=='__main__':unittest.main()
