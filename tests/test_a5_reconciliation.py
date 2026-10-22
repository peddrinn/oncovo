"""A5: operações atômicas e reversíveis no modelo real SQLite/D1, SEM rede."""
import csv
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'etl'))
from auditar_reconciliacao import audit
from reconciliar_d1_local import (APPROVAL, main, proposal_plan, snapshot,
                                 sql_update, verify_snapshot, sql_verify)

T='2026-10-22 12:45:00'
ID_KEEP='7f9c258e215d8a594ab37aca'; ID_DROP='6c4ca31679b544b260f84863'
A='DXiKNIzEbfP';B='DYp5wrURWxO'

def row(id_, code, title='Pescados da Esquina', status='published', address='Rua Bocaiuva, 3',updated=T):
    return dict(id=id_,source_id=code,type='place',status=status,title=title,
                address=address,updated_at=updated,search_text='pescados')

def setup(extra_count=0):
    db=sqlite3.connect(':memory:')
    db.row_factory=sqlite3.Row
    db.executescript((ROOT/'db/schema.sql').read_text(encoding='utf-8'))
    # Snapshot após seed: o card retido usa B como fonte principal.
    originals=[row(ID_KEEP,B),row(ID_DROP,B)]
    for i in range(extra_count): originals.append(row(f'other-{i}',f'OTHER{i:05}',f'Bar {i}'))
    for r in originals:
        db.execute('INSERT INTO search_items (id,source_id,status,type,title,address,updated_at,search_text) '
                   'VALUES(:id,:source_id,:status,:type,:title,:address,:updated_at,:search_text)',r)
    db.commit()
    return db

def db_snapshot(db):return [dict(x) for x in db.execute('SELECT id,source_id,status,type,title,address,updated_at FROM search_items')]

def fixture(db, approved=True):
    prior=db_snapshot(db)
    canonical=[row(ID_KEEP,B)]
    mappings=[
        dict(post_code=A,card_id=ID_KEEP,original_card_id=ID_KEEP,entity_id='pl_abc',source_url='https://www.instagram.com/p/'+A+'/',is_primary='0'),
        dict(post_code=B,card_id=ID_KEEP,original_card_id=ID_DROP,entity_id='pl_abc',source_url='https://www.instagram.com/p/'+B+'/',is_primary='1')]
    decisions=audit(prior,canonical,mappings)['actions']
    assert len(decisions)==1
    if approved:
        decisions[0].update(editorial_decision=APPROVAL,reviewed_by='editor_test',reviewed_at='2026-10-22',
            approval_reason='Duas fontes mostram a mesma unidade e endereço',
            approval_evidence_url='https://www.instagram.com/p/'+B+'/')
    return prior,canonical,mappings,decisions

class A5Tests(unittest.TestCase):
    def test_post_verification_rejects_changed_canonical(self):
        for field,value in [('type','event'),('updated_at','LATER'),('status','hidden')]:
            with self.subTest(field=field):
                db=setup();old,can,mapping,review=fixture(db)
                plan=proposal_plan(old,can,mapping,review)
                db.executescript(sql_update(plan,'apply'))
                db.execute(f'UPDATE search_items SET {field}=? WHERE id=?',(value,ID_KEEP))
                db.commit()
                self.assertFalse(verify_snapshot(plan,db_snapshot(db))['passed'])
                self.assertEqual(db.execute(sql_verify(plan,'hidden').split(';')[0]).fetchone()[0],'FAIL')

    def test_sql_verification_rejects_changed_hidden_source(self):
        db=setup();old,can,mapping,review=fixture(db)
        plan=proposal_plan(old,can,mapping,review)
        db.executescript(sql_update(plan,'apply'))
        db.execute("UPDATE search_items SET source_id='WRONG' WHERE id=?",(ID_DROP,))
        db.commit()
        self.assertEqual(db.execute(sql_verify(plan,'hidden').split(';')[0]).fetchone()[0],'FAIL')

    def test_no_approval_means_no_sql(self):
        db=setup();old,can,mapping,review=fixture(db,False)
        with self.assertRaisesRegex(ValueError,'Nenhuma despublicação aprovada'):
            proposal_plan(old,can,mapping,review)
    def test_rejected_editorial_decision_does_not_create_sql(self):
        db=setup();old,can,mapping,review=fixture(db,False)
        review[0]['editorial_decision']='rejected'
        with self.assertRaisesRegex(ValueError,'Nenhuma despublicação aprovada'):
            proposal_plan(old,can,mapping,review)
    def test_apply_atomic_and_idempotent(self):
        db=setup(2);old,can,mapping,review=fixture(db)
        plan=proposal_plan(old,can,mapping,review)
        statement=sql_update(plan,'apply')
        self.assertNotIn('BEGIN TRANSACTION',statement)
        self.assertNotIn('DELETE FROM',statement)
        db.executescript(statement)
        self.assertEqual(db.execute('SELECT status FROM search_items WHERE id=?',(ID_DROP,)).fetchone()[0],'hidden')
        self.assertEqual(db.execute("SELECT COUNT(*) FROM search_items WHERE status='published'").fetchone()[0],3)
        self.assertTrue(verify_snapshot(plan,db_snapshot(db))['passed'])
        state=db_snapshot(db)
        db.executescript(statement)
        self.assertEqual(state,db_snapshot(db))
    def test_stale_timestamp_no_changes(self):
        db=setup(1);old,can,mapping,review=fixture(db);plan=proposal_plan(old,can,mapping,review)
        db.execute("UPDATE search_items SET updated_at='LATER' WHERE id=?",(ID_DROP,))
        db.commit();db.executescript(sql_update(plan,'apply'))
        self.assertEqual(db.execute('SELECT status FROM search_items WHERE id=?',(ID_DROP,)).fetchone()[0],'published')
        self.assertFalse(verify_snapshot(plan,db_snapshot(db))['passed'])
    def test_missing_canonical_prevents_write(self):
        db=setup();old,can,mapping,review=fixture(db);plan=proposal_plan(old,can,mapping,review)
        db.execute('DELETE FROM search_items WHERE id=?',(ID_KEEP,));db.commit()
        db.executescript(sql_update(plan,'apply'))
        self.assertEqual(db.execute('SELECT status FROM search_items WHERE id=?',(ID_DROP,)).fetchone()[0],'published')
    def test_wrong_canonical_source_prevents_write(self):
        db=setup();old,can,mapping,review=fixture(db);plan=proposal_plan(old,can,mapping,review)
        db.execute("UPDATE search_items SET source_id='OTHER' WHERE id=?",(ID_KEEP,));db.commit()
        db.executescript(sql_update(plan,'apply'))
        self.assertEqual(db.execute('SELECT status FROM search_items WHERE id=?',(ID_DROP,)).fetchone()[0],'published')
    def test_missing_or_modified_approval_fields_block(self):
        db=setup();old,can,mapping,review=fixture(db)
        for key,value in [('reviewed_by',''),('reviewed_at','31/10'),('approval_reason',''),
                          ('approval_evidence_url','not-https')]:
            candidate=[dict(review[0])];candidate[0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):
                proposal_plan(old,can,mapping,candidate)
    def test_cannot_approve_forged_destination(self):
        db=setup();old,can,mapping,review=fixture(db)
        review[0]['new_card_id']='attacker'
        with self.assertRaisesRegex(ValueError,'alterou evidência'):
            proposal_plan(old,can,mapping,review)
    def test_rollback_cannot_be_generated_without_post_snapshot(self):
        db=setup();old,can,mapping,review=fixture(db);plan=proposal_plan(old,can,mapping,review)
        with self.assertRaisesRegex(ValueError,'snapshot pós-aplicação'):
            sql_update(plan,'rollback')
    def test_rollback_restores_card_with_guards(self):
        db=setup();old,can,mapping,review=fixture(db);plan=proposal_plan(old,can,mapping,review)
        db.executescript(sql_update(plan,'apply'))
        post=db_snapshot(db)
        sql=sql_update(plan,'rollback',post_snapshot=post)
        db.executescript(sql)
        self.assertTrue(verify_snapshot(plan,db_snapshot(db),rolled_back=True)['passed'])
        db.executescript(sql)
        self.assertEqual(db.execute('SELECT status FROM search_items WHERE id=?',(ID_DROP,)).fetchone()[0],'published')
    def test_rollback_rejects_modified_hidden_row(self):
        db=setup();old,can,mapping,review=fixture(db);plan=proposal_plan(old,can,mapping,review)
        db.executescript(sql_update(plan,'apply'))
        db.execute("UPDATE search_items SET title='Renomeado' WHERE id=?",(ID_DROP,));db.commit()
        with self.assertRaisesRegex(ValueError,'foi alterado'):
            sql_update(plan,'rollback',post_snapshot=db_snapshot(db))
    def test_snapshot_supports_wranger_json_shape(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'snapshot.json'
            p.write_text(json.dumps([{'results':[row(ID_DROP,B)]}]))
            self.assertEqual(snapshot(p)[0]['id'],ID_DROP)
            p.write_text(json.dumps({'results':[row(ID_DROP,B)]}))
            self.assertEqual(snapshot(p)[0]['id'],ID_DROP)
            p.write_text(json.dumps([row(ID_DROP,B)]))
            self.assertEqual(snapshot(p)[0]['id'],ID_DROP)
    def test_snapshot_missing_updated_at_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'snapshot.json';data=row(ID_DROP,B);data.pop('updated_at')
            p.write_text(json.dumps([data]))
            with self.assertRaisesRegex(ValueError,'updated_at'):
                snapshot(p)
    def test_unmapped_other_cards_untouched(self):
        db=setup(3);old,can,mapping,review=fixture(db)
        before={r['id']:r for r in db_snapshot(db)}
        plan=proposal_plan(old,can,mapping,review)
        db.executescript(sql_update(plan,'apply'))
        after={r['id']:r for r in db_snapshot(db)}
        for key in ['other-0','other-1','other-2']:
            self.assertEqual(before[key],after[key])
    def test_sql_verify(self):
        db=setup();old,can,mapping,review=fixture(db)
        plan=proposal_plan(old,can,mapping,review)
        db.executescript(sql_update(plan,'apply'))
        self.assertIn('PASS',str(db.execute(sql_verify(plan,'hidden').split(';')[0].replace('-- Verificar após A5 '+plan['plan_id']+' no D1 LOCAL.\n','')).fetchall()[0][0]))
    def test_cli_generates_plan_not_executes(self):
        db=setup(1);old,can,mapping,review=fixture(db)
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            (p/'snapshot.json').write_text(json.dumps({'results':old}))
            (p/'catalog.jsonl').write_text('\n'.join(json.dumps(r) for r in can)+'\n')
            for name,rows in [('map.csv',mapping),('review.csv',review)]:
                with (p/name).open('w',newline='') as f:
                    writer=csv.DictWriter(f,fieldnames=rows[0].keys());writer.writeheader();writer.writerows(rows)
            code=main(['plan','--snapshot',str(p/'snapshot.json'),'--canonical',str(p/'catalog.jsonl'),
                '--source-map',str(p/'map.csv'),'--decisions',str(p/'review.csv'),'--outdir',str(p/'out')])
            self.assertEqual(code,0)
            self.assertEqual(sorted(x.name for x in (p/'out').iterdir()),['a5_apply.sql','a5_plan.json','a5_verify.sql'])
            self.assertEqual(db.execute('SELECT status FROM search_items WHERE id=?',(ID_DROP,)).fetchone()[0],'published')

    def test_all_or_nothing_when_two_actions_and_one_is_stale(self):
        db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
        db.executescript((ROOT/'db/schema.sql').read_text())
        records=[row('keep-one','FAKEPOST001','Bar Um'),row('drop-one','FAKEPOST001','Bar Um'),
                 row('keep-two','FAKEPOST003','Bar Dois'),row('drop-two','FAKEPOST003','Bar Dois')]
        for item in records:
            db.execute('INSERT INTO search_items (id,source_id,status,type,title,address,updated_at,search_text) '
                       'VALUES(:id,:source_id,:status,:type,:title,:address,:updated_at,:search_text)',item)
        db.commit()
        old=db_snapshot(db);canonical=[records[0],records[2]]
        mapped=[]
        for source,keep,drop,code in [
            ('FAKEPOST001','keep-one','drop-one','FAKEPOST002'),
            ('FAKEPOST003','keep-two','drop-two','FAKEPOST004')]:
            mapped.append(dict(post_code=source,original_card_id=keep,card_id=keep,entity_id=keep,source_url='https://www.instagram.com/p/'+source+'/'))
            mapped.append(dict(post_code=code,original_card_id=drop,card_id=keep,entity_id=keep,source_url='https://www.instagram.com/p/'+code+'/'))
            db.execute('UPDATE search_items SET source_id=? WHERE id=?',(code,drop))
        db.commit()
        old=db_snapshot(db)
        review=audit(old,canonical,mapped)['actions']
        for r in review:
            r.update(editorial_decision=APPROVAL,reviewed_by='revisor',reviewed_at='2026-10-22',
               approval_reason='Fontes conferidas para a mesma unidade',
               approval_evidence_url=r['evidence_url'])
        plan=proposal_plan(old,canonical,mapped,review)
        self.assertEqual(len(plan['actions']),2)
        statement=sql_update(plan,'apply')
        db.execute("UPDATE search_items SET updated_at='novo' WHERE id='drop-two'")
        db.commit();db.executescript(statement)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM search_items WHERE id IN ('drop-one','drop-two') AND status='published'").fetchone()[0],2)

    def test_prepare_review_remains_pending(self):
        db=setup();old,canonical,mapping,review=fixture(db)
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)
            (folder/'snapshot.json').write_text(json.dumps({'results':old}))
            (folder/'catalog.jsonl').write_text('\n'.join(json.dumps(r) for r in canonical)+'\n')
            with (folder/'map.csv').open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=mapping[0].keys());w.writeheader();w.writerows(mapping)
            self.assertEqual(main(['prepare-review','--snapshot',str(folder/'snapshot.json'),
                '--canonical',str(folder/'catalog.jsonl'), '--source-map',str(folder/'map.csv'),
                '--output',str(folder/'review.csv')]),0)
            with (folder/'review.csv').open(newline='') as f:records=list(csv.DictReader(f))
            self.assertEqual(records[0]['editorial_decision'],'pending_review')
            self.assertIn('approval_reason',records[0])
            self.assertIn('approval_evidence_url',records[0])
            with self.assertRaisesRegex(ValueError,'já existe'):
                main(['prepare-review','--snapshot',str(folder/'snapshot.json'),
                    '--canonical',str(folder/'catalog.jsonl'), '--source-map',str(folder/'map.csv'),
                    '--output',str(folder/'review.csv')])

    def test_missing_canonical_in_baseline_refused(self):
        db=setup();old,can,mapping,review=fixture(db)
        old=[r for r in old if r['id']!=ID_KEEP]
        with self.assertRaisesRegex(ValueError,'Canônico deve estar publicado'):
            proposal_plan(old,can,mapping,review)

    def test_tampered_plan_cannot_execute(self):
        db=setup();old,can,mapping,review=fixture(db)
        plan=proposal_plan(old,can,mapping,review)
        plan['actions'][0]['old_id']='another_card'
        with self.assertRaisesRegex(ValueError,'Plano modificado'):
            sql_update(plan,'apply')

    def test_sql_literal_quotes_are_escaped(self):
        db=setup();old,can,mapping,review=fixture(db)
        for i in old:
            if i['id']==ID_DROP:i['title']="Pescados d'Esquina"
        plan=proposal_plan(old,can,mapping,review)
        self.assertIn("Pescados d''Esquina",sql_update(plan,'apply'))

if __name__=='__main__':unittest.main()
