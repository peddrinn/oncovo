import csv
import copy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'etl'))
from a3_fixtures import fixture,batch_for,fixture_plan,response
from extracao_versionada import execute,export_results
from criar_revisao import make_review,import_decisions
from common import read_jsonl,write_jsonl
from preparar_publicacao import transform,build
from test_etl import NOW


class A4Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        row,payload=fixture();store=self.root/'a3';batch=batch_for([row],self.root,self.root/'a1')
        p=fixture_plan([row],store,batch)
        execute(p,store,execute_authorized=True,approved_plan_id=p['plan_id'],authorization_reference='SYNTHETIC_TEST_ONLY',
                budget='1',transport=lambda req:response(payload),synthetic=True)
        self.source=self.root/'extractions.jsonl';export_results(p,store,self.source)
        self.template=self.root/'review.jsonl';make_review(self.source,self.template)
    def edit_csv(self,changes):
        source=self.template.with_suffix('.csv')
        with source.open(newline='') as handle:rows=list(csv.DictReader(handle))
        rows[0].update(changes);target=self.root/'decisions.csv'
        with target.open('w',newline='') as handle:
            writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
        return target
    def test_csv_round_trip_keeps_review(self):
        target=self.root/'out.jsonl';import_decisions(self.template,self.template.with_suffix('.csv'),target)
        self.assertEqual(list(read_jsonl(target))[0]['publish_status'],'review')
    def test_explicit_fixture_approval_csv_is_version_bound(self):
        file=self.edit_csv(dict(publish_status='published',reviewed_by='SYNTHETIC_TEST_ONLY',reviewed_at='2026-10-22',
                                approval_reason='Somente fixture de revisão CSV',currentness_recheck_required='false'))
        target=self.root/'approved.jsonl';import_decisions(self.template,file,target)
        ext=list(read_jsonl(self.source))[0];decision=list(read_jsonl(target))[0]
        self.assertEqual(transform(decision,ext,NOW)[1],'published')
        decision['evidence_digest']='stale';self.assertEqual(transform(decision,ext,NOW)[1],'review')
    def test_csv_forged_version_is_rejected(self):
        file=self.edit_csv(dict(extraction_id='wrong'))
        with self.assertRaises(ValueError):import_decisions(self.template,file,self.root/'out.jsonl')
    def test_publication_does_not_choose_arbitrary_history_version(self):
        ext=list(read_jsonl(self.source))[0];other=copy.deepcopy(ext);other['extraction_id']='different'
        write_jsonl(self.root/'history.jsonl',[ext,other])
        with self.assertRaisesRegex(ValueError,'Múltiplas versões'):
            build(self.template,self.root/'history.jsonl',self.root/'items.jsonl',self.root/'audit.csv',now=NOW)

if __name__=='__main__':unittest.main()
