"""A2.1: regressões de revisão e reconciliação offline, sem rede ou SQL remoto."""
import csv
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
from auditar_reconciliacao import audit, main as reconciliation_cli
from resolver_entidades import resolve, jsonl_write
from gerar_seed import make_seed

NOW=datetime(2026,10,22,12,0,tzinfo=ZoneInfo('America/Sao_Paulo'))


def place(code,name='Bar Horizonte',address='Rua Catumbi, 390 – Caiçara – BH', status='published'):
    return dict(id='legacy_'+code,source_id=code,
        source_url=f'https://www.instagram.com/p/{code}/',type='place',
        status=status,title=name,city='Belo Horizonte',neighborhood='Caiçara',
        address=address,rank_score_base=85,description='bar',search_text='bar')


class A21Tests(unittest.TestCase):
    def test_same_address_renamed_place_requires_review(self):
        rows=[place('FAKEPOST001','SPACE FRIENDS'),place('FAKEPOST002','Space Friends Park')]
        result=resolve(rows,now=NOW)
        self.assertEqual(result['report']['entity_count'],2)
        self.assertEqual(result['report']['merge_candidates'],1)
        self.assertEqual(result['candidates'][0]['candidate_basis'],'same_full_address')
        self.assertEqual(result['candidates'][0]['decision'],'pending_review')

    def test_different_suite_not_equal_address_evidence(self):
        rows=[place('FAKEPOST001','Atração Um','Rua Catumbi, 390, loja 1'),
              place('FAKEPOST002','Atração Dois','Rua Catumbi, 390, loja 2')]
        result=resolve(rows,now=NOW)
        self.assertEqual(result['report']['merge_candidates'],0)
        self.assertEqual(result['report']['entity_count'],2)

    def test_merge_creates_explicit_proposal_not_sql(self):
        rows=[place('FAKEPOST001'),place('FAKEPOST002')]
        r=resolve(rows,now=NOW)
        result=audit(rows,r['catalog'],r['source_map'])
        self.assertEqual(len(r['catalog']),1)
        self.assertEqual(len(result['actions']),1)
        self.assertEqual(result['actions'][0]['action'],'propose_hide_duplicate')
        self.assertEqual(result['actions'][0]['editorial_decision'],'pending_review')
        self.assertFalse(result['report']['publish_ready'])

    def test_partial_snapshot_never_hides_unknown_published(self):
        a=place('FAKEPOST001');b=place('FAKEPOST002');unknown=place('FAKEPOST003',address='Rua Verde, 1')
        r=resolve([a,b],now=NOW)
        result=audit([a,b,unknown],r['catalog'],r['source_map'])
        self.assertEqual(result['report']['counts']['unmapped_published_untouched'],1)
        self.assertEqual(result['report']['unmapped_published_ids'],['legacy_FAKEPOST003'])
        self.assertEqual(len(result['actions']),1)

    def test_unchanged_standalone_never_hidden(self):
        a=place('FAKEPOST001')
        r=resolve([a],now=NOW)
        result=audit([a],r['catalog'],r['source_map'])
        self.assertEqual(result['actions'],[])

    def test_prev_source_mismatch_fails(self):
        a=place('FAKEPOST001');b=place('FAKEPOST002')
        r=resolve([a,b],now=NOW)
        prev=[dict(a),dict(b)]
        for row in prev:row['source_id']='WRONGCODE00'
        with self.assertRaisesRegex(ValueError,'divergentes'):
            audit(prev,r['catalog'],r['source_map'])

    def test_current_hidden_card_does_not_propose_hide(self):
        rows=[place('FAKEPOST001'),place('FAKEPOST002')]
        r=resolve(rows,now=NOW)
        previous=[dict(row) for row in rows]
        for row in previous:
            if row['id']!=r['catalog'][0]['id']:row['status']='hidden'
        result=audit(previous,r['catalog'],r['source_map'])
        self.assertEqual(result['actions'],[])
        self.assertEqual(result['report']['counts']['already_not_published'],1)

    def test_idempotent_seed_alone_leaves_previous_duplicate(self):
        # Confirma por que A5 exige decisão explícita: o seed novo não retira old PK.
        rows=[place('FAKEPOST001'),place('FAKEPOST002')]
        r=resolve(rows,now=NOW)
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);original=base/'original.jsonl';canonical=base/'canonical.jsonl'
            jsonl_write(original,rows);jsonl_write(canonical,r['catalog'])
            make_seed(original,base/'old.sql');make_seed(canonical,base/'new.sql')
            db=sqlite3.connect(':memory:')
            db.executescript((ROOT/'db/schema.sql').read_text())
            db.executescript((base/'old.sql').read_text())
            db.executescript((base/'new.sql').read_text())
            db.executescript((base/'new.sql').read_text())
            self.assertEqual(db.execute("SELECT COUNT(*) FROM search_items WHERE status='published'").fetchone()[0],2)

    def test_cli_only_writes_reports(self):
        rows=[place('FAKEPOST001'),place('FAKEPOST002')]
        r=resolve(rows,now=NOW)
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);old=base/'old.jsonl';new=base/'new.jsonl';mapping=base/'map.csv'
            jsonl_write(old,rows);jsonl_write(new,r['catalog'])
            with mapping.open('w',newline='',encoding='utf-8') as f:
                writer=csv.DictWriter(f,fieldnames=r['source_map'][0].keys());writer.writeheader();writer.writerows(r['source_map'])
            self.assertEqual(reconciliation_cli(['--previous',str(old),'--canonical',str(new),
                         '--source-map',str(mapping),'--outdir',str(base/'out')]),0)
            self.assertEqual(sorted(x.name for x in (base/'out').iterdir()),
                             ['reconciliation_report.json','reconciliation_review.csv'])
            self.assertEqual(json.loads((base/'out/reconciliation_report.json').read_text())['counts']['proposed_hide_duplicate'],1)

if __name__=='__main__':unittest.main()
