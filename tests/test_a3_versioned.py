import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'etl'))
from a3_fixtures import fixture,batch_for,fixture_plan,response
from extracao_versionada import request_for,plan,execute,cached,import_legacy,export_results
from extrair_llm import PROMPT,messages_for
from criar_revisao import make_review
from common import read_jsonl,write_jsonl
from lotes_incrementais import atomic_json,load
from preparar_publicacao import transform,build
from avaliar_extracoes import prepare,score
from test_etl import NOW


class A3Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.store=self.root/'a3';self.row,self.payload=fixture();self.batch=batch_for([self.row],self.root,self.root/'a1')
    def planned(self,**kwargs):return fixture_plan([self.row],self.store,self.batch,**kwargs)
    def run_fixture(self,p=None,transport=None,**kwargs):
        p=p or self.planned()
        return execute(p,self.store,execute_authorized=True,approved_plan_id=p['plan_id'],authorization_reference='SYNTHETIC_TEST_ONLY',
                       budget='1',transport=transport or (lambda req:response(self.payload)),synthetic=True,**kwargs)
    def extraction(self):
        self.run_fixture();return cached(self.store,self.planned()['requests'][0])
    def test_cache_hit_and_deterministic_reexecution(self):
        p=self.planned();a=self.run_fixture(p);b=self.run_fixture(p)
        self.assertEqual(a['calls'],1);self.assertEqual(b['calls'],0);self.assertEqual(b['cache_hits'],1)
        self.assertEqual(a['results'],b['results']);self.assertEqual(self.planned()['metrics']['cache_hits'],1)
        self.assertEqual(p['plan_id'],self.planned()['plan_id'])
    def test_cache_miss(self):self.assertEqual(self.planned()['metrics']['new_inferences'],1)
    def test_caption_change_changes_identity(self):
        r=copy.deepcopy(self.row);r['caption_text_clean']+=' Alterado.'
        self.assertNotEqual(request_for(r)['request_id'],request_for(self.row)['request_id'])
    def test_prompt_change_invalidates_cache(self):
        p=self.root/'prompt.txt';p.write_text(PROMPT.read_text()+'\nVariação somente em cópia de teste.')
        self.assertNotEqual(request_for(self.row,prompt=p)['request_id'],request_for(self.row)['request_id'])
    def test_model_change(self):self.assertNotEqual(request_for(self.row,model='one')['request_id'],request_for(self.row,model='two')['request_id'])
    def test_parameter_change(self):self.assertNotEqual(request_for(self.row,max_tokens=500)['request_id'],request_for(self.row,max_tokens=600)['request_id'])
    def test_acquisition_metadata_does_not_invalidate(self):
        r=dict(self.row,batch_id='other',_scraped_at='later',_source_profiles=['new'],like_count=99,
               triage_score=1,triage_class='another_rank',source_profile='another_discovery_profile')
        self.assertEqual(request_for(r)['request_id'],request_for(self.row)['request_id'])
    def test_legacy_unknown_is_never_cache_hit(self):
        file=self.root/'legacy.jsonl';write_jsonl(file,[dict(self.payload,post_code=self.row['post_code'])])
        ids=import_legacy(file,self.store);self.assertEqual(import_legacy(file,self.store),ids)
        self.assertEqual(load(self.store/'legacy'/(ids[0]+'.json'))['provenance'],'legacy_unverified')
        self.assertEqual(self.planned()['metrics']['cache_hits'],0)
    def test_interrupted_legacy_jsonl_blocks_all_writes(self):
        file=self.root/'bad.jsonl';file.write_text(json.dumps(self.payload)+'\n{"broken":')
        with self.assertRaises(ValueError):import_legacy(file,self.store)
        self.assertFalse((self.store/'legacy').exists())
    def test_invalid_json_records_error_and_reserves_budget(self):
        r=self.run_fixture(transport=lambda req:dict(content='{broken',finish_reason='stop',usage=None))
        self.assertEqual(r['calls'],1);self.assertIsNone(r['actual_cost']);self.assertTrue(r['errors'])
        self.assertEqual(self.planned()['metrics']['cache_hits'],0)
        self.assertEqual(self.run_fixture()['calls'],0)
    def test_partial_is_not_reusable(self):
        payload=copy.deepcopy(self.payload);payload['extraction_status']='partial'
        self.run_fixture(transport=lambda req:response(payload));self.assertEqual(self.planned()['metrics']['cache_hits'],0)
        self.assertEqual(self.run_fixture()['calls'],0)
    def test_incomplete_response_never_cached(self):
        self.run_fixture(transport=lambda req:response(self.payload,'length'))
        self.assertEqual(self.planned()['metrics']['cache_hits'],0)
    def test_bounded_transient_retry(self):
        count=[]
        def transport(req):
            count.append(1)
            if len(count)==1:raise urllib.error.HTTPError('https://example.test',429,'synthetic',{},None)
            return response(self.payload)
        r=self.run_fixture(transport=transport,max_attempts=2,sleep=lambda sec:None)
        self.assertEqual(r['calls'],2);self.assertEqual(len(r['results']),1)
    def test_budget_insufficient_no_call(self):
        p=self.planned();calls=[]
        r=execute(p,self.store,execute_authorized=True,approved_plan_id=p['plan_id'],authorization_reference='fixture',budget='0',
                  transport=lambda req:calls.append(req),synthetic=True)
        self.assertEqual(calls,[]);self.assertEqual(r['calls'],0)
    def test_unverified_estimate_blocks_execution(self):
        p=plan([self.row],self.store,batch=self.batch,provider='synthetic-fixture',pricing=dict(input_per_million='1',output_per_million='2',currency='TEST',reference='fixture'))
        with self.assertRaisesRegex(ValueError,'Estimativa'):self.run_fixture(p)
    def test_execute_requires_authorization(self):
        p=self.planned()
        with self.assertRaises(ValueError):execute(p,self.store,transport=lambda req:response(self.payload),synthetic=True)
    def test_dry_plan_never_networks(self):
        with patch('urllib.request.urlopen',side_effect=AssertionError('network forbidden')):self.planned()
    def test_crash_after_response_recovers_without_call(self):
        import extracao_versionada as module
        original=module.save_response
        with patch('extracao_versionada.save_response',side_effect=OSError('synthetic disk failure')):
            with self.assertRaises(OSError):self.run_fixture()
        r=self.run_fixture(transport=lambda req:(_ for _ in ()).throw(AssertionError('no second call')))
        self.assertEqual(r['calls'],0);self.assertEqual(r['cache_hits'],1)
        self.assertEqual(r['authorization_ledger']['input_tokens'],100)
    def test_result_corruption_is_blocked(self):
        ext=self.extraction();path=self.store/'results'/ext['request_id']/(ext['extraction_id']+'.json')
        data=load(path);data['location']['city']='changed';atomic_json(path,data)
        with self.assertRaises(ValueError):self.planned()
    def test_versioned_review_defaults_and_stale_approval(self):
        ext=self.extraction();file=self.root/'ext.jsonl';write_jsonl(file,[ext]);make_review(file,self.root/'review.jsonl')
        item=list(read_jsonl(self.root/'review.jsonl'))[0]
        self.assertEqual(transform(item,ext,NOW)[1],'review')
        item.update(publish_status='published',reviewed_by='SYNTHETIC_TEST_ONLY',reviewed_at='2026-10-22',
                    approval_reason='Fixture de publicação apenas para teste',currentness_recheck_required=False)
        self.assertEqual(transform(item,ext,NOW)[1],'published')
        changed=copy.deepcopy(ext);changed['location']['address']='Rua Alterada, 2'
        self.assertEqual(transform(item,changed,NOW)[1],'review')
        with self.assertRaises(ValueError):make_review(file,self.root/'review.jsonl')
    def test_new_extraction_id_requires_new_approval(self):
        ext=self.extraction();item=dict(post_code=ext['post_code'],publish_status='published',extraction_id='old',evidence_digest='old')
        self.assertEqual(transform(item,ext,NOW)[1],'review')
    def test_event_missing_date_is_partial(self):
        row,payload=fixture(kind='event');payload['event']['date_start']=None
        from validacao_extracao import validate_versioned
        value,checks=validate_versioned(payload,messages_for(row))
        self.assertEqual(value['extraction_status'],'partial');self.assertIn('event_without_date',checks['issues'])
    def test_free_and_ticket_contradiction(self):
        payload=copy.deepcopy(self.payload);payload['commercial_info'].update(is_free=True,ticket_required=True)
        from validacao_extracao import validate_versioned
        value,_=validate_versioned(payload,messages_for(self.row))
        self.assertEqual(value['extraction_status'],'partial');self.assertIn('free_and_ticket_required_conflict',value['quality']['risk_flags'])
    def test_unsupported_evidence_is_flagged(self):
        payload=copy.deepcopy(self.payload);payload['quality']['evidence'][0]['quote']='invented quote'
        from validacao_extracao import validate_versioned
        value,checks=validate_versioned(payload,messages_for(self.row));self.assertFalse(checks['literal_evidence_valid'])
        self.assertEqual(value['extraction_status'],'partial')
    def test_no_accuracy_without_human_reference(self):
        ext=self.extraction();path=self.root/'ref.jsonl';prepare([ext],path)
        report=score([ext],list(read_jsonl(path)))
        self.assertIsNone(report['accuracy']);self.assertEqual(report['human_references'],0)
    def test_per_field_metrics_require_exact_reference_version(self):
        ext=self.extraction();ref=dict(human_review_status='reviewed',reviewed_by='SYNTHETIC_REFERENCE_ONLY',reviewed_at='2026-10-22',
              evidence_reference='fixture',extraction_id=ext['extraction_id'],labels={'location.city':'BH'})
        report=score([ext],[ref]);self.assertEqual(report['metrics']['all']['location.city']['accuracy'],1)
        ref['extraction_id']='wrong'
        with self.assertRaises(ValueError):score([ext],[ref])
    def test_export_keeps_legacy_contract(self):
        self.extraction();p=self.planned();target=self.root/'export.jsonl';self.assertEqual(export_results(p,self.store,target),1)
        self.assertEqual(list(read_jsonl(target))[0]['post_code'],self.row['post_code'])

    def test_timeout_reserves_budget_and_retry_requires_reference(self):
        def timeout(req):raise TimeoutError('synthetic')
        first=self.run_fixture(transport=timeout)
        self.assertEqual(first['unknown_usage_attempts'],1)
        self.assertIsNone(first['authorization_ledger']['usage_priced_cost'])
        self.assertEqual(self.run_fixture()['calls'],0)
        self.assertEqual(self.run_fixture(retry_reference='SYNTHETIC_RETRY_ONLY')['calls'],1)

    def test_provider_usage_exceeding_bound_stops_further_requests(self):
        def exceeded(req):
            data=response(self.payload);data['usage']['prompt_tokens']=40000;return data
        self.run_fixture(transport=exceeded)
        with self.assertRaisesRegex(ValueError,'Limite de tokens'):self.run_fixture()

    def test_numeric_schema_error_is_not_valid_result(self):
        payload=copy.deepcopy(self.payload);payload['commercial_info']['ticket_required']='false'
        r=self.run_fixture(transport=lambda req:response(payload));self.assertTrue(r['errors'])
        self.assertEqual(self.planned()['metrics']['cache_hits'],0)

    def test_live_and_synthetic_cache_are_separate(self):
        self.extraction()
        live=plan([self.row],self.store,batch=self.batch,model='fixture-model')
        self.assertEqual(live['metrics']['cache_hits'],0)

    def test_truncated_or_tampered_plan_is_rejected(self):
        p=self.planned();p['requests'][0]['row']['caption_text_clean']='tampered'
        with self.assertRaisesRegex(ValueError,'Plano alterado'):self.run_fixture(p)

    def test_hallucinated_address_is_flagged_even_with_literal_quote(self):
        from validacao_extracao import validate_versioned
        payload=copy.deepcopy(self.payload);payload['location']['address']='Rua Inventada, 999'
        value,checks=validate_versioned(payload,messages_for(self.row))
        self.assertIn('unsupported_value:location.address',checks['issues']);self.assertEqual(value['extraction_status'],'partial')

    def test_false_ticket_without_explicit_support_is_partial(self):
        from validacao_extracao import validate_versioned
        payload=copy.deepcopy(self.payload);payload['commercial_info']['ticket_required']=False
        payload['quality']['evidence'].append(dict(field='commercial_info.ticket_required',quote=self.row['caption_text_clean']))
        value,checks=validate_versioned(payload,messages_for(self.row))
        self.assertIn('unsupported_boolean:ticket_required',checks['issues']);self.assertEqual(value['extraction_status'],'partial')

    def test_cli_execute_first_writes_preview_and_stops(self):
        from extracao_versionada import main
        source=self.root/'queue.jsonl';write_jsonl(source,[self.row]);report=self.root/'plan.json'
        with patch('urllib.request.urlopen',side_effect=AssertionError('network forbidden')):
            with self.assertRaisesRegex(ValueError,'Prévia gravada'):
                main(['--input',str(source),'--batch',str(self.batch),'--report',str(report),
                      '--store',str(self.store),'--execute'])
        self.assertTrue(report.exists());self.assertFalse((self.store/'attempts').exists())

    def test_provider_usage_parsed_with_mocked_http_only(self):
        import io
        from extracao_versionada import provider_call
        request=request_for(self.row)
        body=json.dumps(dict(id='SYNTHETIC_ID',model='SYNTHETIC_MODEL',usage=dict(prompt_tokens=12,completion_tokens=4),
             choices=[dict(message=dict(content='{}'),finish_reason='stop')])).encode()
        with patch('urllib.request.urlopen',return_value=io.BytesIO(body)) as mocked:
            result=provider_call(request,'SYNTHETIC_KEY')
        self.assertEqual(result['usage']['prompt_tokens'],12);self.assertEqual(result['provider_model'],'SYNTHETIC_MODEL')
        self.assertEqual(mocked.call_count,1)

    def test_final_discard_can_be_reused_without_inference(self):
        payload=copy.deepcopy(self.payload);payload.update(content_type='irrelevant',extraction_status='discard')
        self.run_fixture(transport=lambda req:response(payload))
        self.assertEqual(self.planned()['metrics']['cache_hits'],1)
        self.assertEqual(self.run_fixture()['calls'],0)

    def test_model_error_status_is_queued_not_success_or_cache(self):
        payload=copy.deepcopy(self.payload);payload['extraction_status']='error'
        report=self.run_fixture(transport=lambda req:response(payload))
        self.assertTrue(any(e['error']=='error_requires_review' for e in report['errors']))
        self.assertEqual(self.planned()['metrics']['cache_hits'],0)

if __name__=='__main__':unittest.main()
