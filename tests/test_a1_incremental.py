"""A1 offline: durabilidade, identidade global, versões e contrato com triagem."""
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'etl'))
from lotes_incrementais import ingest, load, content_hash, atomic_json
from triagem import triage
from extrair_llm import messages_for
from resolver_entidades import resolve
from test_entity_resolution import place, event, NOW


def post(code='FAKEA1001', profile='perfil_a', caption=None):
    return dict(code=code,_profile_username=profile,user={'username':'autor_real'},
                coauthor_producers=[{'username':'colaborador'}],taken_at='2026-10-22T10:00:00-03:00',
                caption_text=caption or ('Restaurante café em BH, Rua Bahia, 123, Centro. Cardápio, reservas e funcionamento. '*2))


class IncrementalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.store=self.root/'store';self.serial=0
    def source(self,rows):
        self.serial+=1;p=self.root/f'input{self.serial}.jsonl'
        p.write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in rows),encoding='utf-8');return p
    def batch(self,rows,**kwargs):
        return ingest(self.source(rows),self.store,**kwargs)
    def catalog(self,result):
        with (self.store/'batches'/result['batch_id']/'catalog.jsonl').open() as handle:
            return [json.loads(x) for x in handle]
    def test_new_post_and_manifest_checksums(self):
        result=self.batch([post()]);self.assertEqual(result['status'],'complete')
        self.assertEqual(result['metrics']['new'],1);self.assertEqual(result['metrics']['to_triage'],1)
        self.assertIn('input.jsonl',result['checksums']);self.assertTrue(result['finished_at'])
    def test_same_post_same_profile_global_duplicate(self):
        self.batch([post()]);r=self.batch([post(),post()]);self.assertEqual(r['metrics']['duplicates'],2)
        self.assertEqual(r['metrics']['to_triage'],0);self.assertEqual(len(self.catalog(r)),1)
    def test_multiple_profiles_single_extraction_candidate(self):
        r=self.batch([post(),post(profile='perfil_b')]);c=self.catalog(r)
        self.assertEqual(r['metrics']['to_triage'],1)
        self.assertEqual(c[0]['_source_profiles'],['perfil_a','perfil_b'])
        self.assertEqual(c[0]['user']['username'],'autor_real')
    def test_caption_change_keeps_original_raw(self):
        p=self.source([post()]);raw=p.read_bytes();first=ingest(p,self.store)
        changed=post(caption='Nova legenda');second=self.batch([changed]);self.assertEqual(second['metrics']['changed'],1)
        self.assertEqual(p.read_bytes(),raw);self.assertNotEqual(content_hash(post()),content_hash(changed))
        old=load(self.store/'batches'/first['batch_id']/'chunk_00000000.json')
        self.assertEqual(old['observations'][0]['row']['caption_text'],post()['caption_text'])
    def test_unicode_separator_preserved(self):
        r=self.batch([post(caption='Café\u2028Restaurante')]);self.assertEqual(self.catalog(r)[0]['caption_text'],'Café\u2028Restaurante')
    def test_invalid_json_does_not_commit_or_change_parent(self):
        first=self.batch([post()]);p=self.root/'bad';p.write_text('{broken}\n')
        r=ingest(p,self.store);self.assertEqual(r['status'],'failed');self.assertEqual(r['metrics']['invalid'],1)
        self.assertEqual(len(list((self.store/'batches').iterdir())),1);self.assertEqual(len(self.catalog(first)),1)
    def test_interrupted_input_not_promoted(self):
        p=self.root/'broken';p.write_text(json.dumps(post())+'\n'+json.dumps(post('FAKEA1002')))
        r=ingest(p,self.store);self.assertEqual(r['status'],'failed');self.assertFalse((self.store/'batches').exists())
    def test_partial_resume_checkpoint_and_no_duplicates(self):
        p=self.source([post(f'FAKEA1{i:03d}') for i in range(5)])
        partial=ingest(p,self.store,max_records=2,chunk_size=1)
        self.assertEqual(partial['status'],'partial');self.assertEqual(partial['checkpoint']['processed_lines'],2)
        self.assertFalse((self.store/'batches').exists())
        self.assertEqual(partial['checkpoint']['profiles']['perfil_a']['last_input_line'],2)
        result=ingest(p,self.store,chunk_size=1);self.assertEqual(result['metrics']['new'],5)
        self.assertEqual(len(self.catalog(result)),5)
    def test_replay_identical_batch_is_immutable(self):
        p=self.source([post()]);a=ingest(p,self.store);b=ingest(p,self.store)
        self.assertEqual(a,b);self.assertEqual(len(list((self.store/'batches').iterdir())),1)
    def test_batch_id_cannot_be_reused_for_different_input(self):
        self.batch([post()],batch_id='one')
        with self.assertRaises(ValueError):self.batch([post('FAKEA1002')],batch_id='one')
    def test_missing_source_in_partial_batch_preserved(self):
        self.batch([post(),post('FAKEA1002')]);r=self.batch([post()]);self.assertEqual(len(self.catalog(r)),2)
    def test_timezone_required_and_window(self):
        row=post();row['taken_at']='2026-10-22T10:00:00'
        self.assertEqual(self.batch([row])['status'],'failed')
        with self.assertRaises(ValueError):self.batch([post()],window_start='2026-10-22T10:00:00')
    def test_interrupted_temporary_chunk_ignored_on_resume(self):
        p=self.source([post(),post('FAKEA1002')]);a=ingest(p,self.store,max_records=1)
        stage=self.store/'pending'/a['batch_id'];(stage/'chunk_00000001.json.tmp').write_text('{')
        b=ingest(p,self.store);self.assertEqual(len(self.catalog(b)),2)
    def test_changed_input_during_resume_refused(self):
        p=self.source([post(),post('FAKEA1002')]);ingest(p,self.store,batch_id='resume',max_records=1)
        p.write_text('{}\n')
        with self.assertRaises(ValueError):ingest(p,self.store,batch_id='resume')
    def test_corrupt_committed_file_blocks_replay(self):
        p=self.source([post()]);a=ingest(p,self.store)
        (self.store/'batches'/a['batch_id']/'catalog.jsonl').write_text('{}\n')
        with self.assertRaisesRegex(ValueError,'Checksum'):ingest(p,self.store)
    def test_triage_and_llm_contract_preserve_provenance(self):
        r=self.batch([post(),post(profile='perfil_b')]);base=self.store/'batches'/r['batch_id']
        dest=self.root/'triage';dest.mkdir()
        subprocess.run([sys.executable,str(ROOT/'etl/triagem_avancada.py'),'--input',str(base/'delta.jsonl'),'--outdir',str(dest)],check=True,capture_output=True)
        with (dest/'dia1_posts_limpos.jsonl').open() as handle: rows=[json.loads(x) for x in handle]
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['source_profiles_all'],'perfil_a,perfil_b')
        self.assertEqual(rows[0]['media_owner_username'],'autor_real');self.assertTrue(messages_for(rows[0]))
        path=self.root/'simple.jsonl';triage(base/'delta.jsonl',path)
        self.assertEqual(json.loads(path.read_text())['source_profiles'],['perfil_a','perfil_b'])
    def test_a2_new_source_keeps_pinned_identity_across_orders(self):
        initial=resolve([place('ZZZZA1001')],now=NOW)
        rows=[place('AAAAA1002'),place('ZZZZA1001'),place('BRANCHA10',address='Rua Bahia, 999')]
        a=resolve(rows,registry=initial['registry'],now=NOW)
        b=resolve(list(reversed(rows)),registry=initial['registry'],now=NOW)
        self.assertEqual(a,b);self.assertEqual(len(a['catalog']),2)
        self.assertIn(initial['catalog'][0]['id'],[x['id'] for x in a['catalog']])
    def test_a2_ambiguities_and_temporal_gates(self):
        a=place('FAKEA1001',address='');b=place('FAKEA1002',address='')
        c=place('FAKEA1003','Café Horizonte Novo');d=place('FAKEA1004',status='review')
        promo=place('FAKEA1005');promo['type']='promotion'
        expired=event('FAKEA1006',start='2020-01-01T10:00:00-03:00',end='2020-01-01T11:00:00-03:00')
        recurring=event('FAKEA1007');recurring['starts_at']=None
        result=resolve([a,b,c,d,promo,expired,recurring,event('FAKEA1008'),event('FAKEA1009',start='2026-10-26T19:00:00-03:00',end='2026-10-26T23:00:00-03:00')],now=NOW)
        self.assertEqual(len(result['catalog']),5);self.assertGreaterEqual(len(result['candidates']),1)
        self.assertEqual(sum(result['report']['withheld'].values()),4)

    def test_failed_acquisition_cannot_be_imported_as_complete(self):
        p=self.source([post()]);p.with_suffix('.jsonl.acquisition.json').write_text('{"status":"failed"}')
        with self.assertRaisesRegex(ValueError,'Aquisição'):ingest(p,self.store)

    def test_paused_batch_detects_parent_advance(self):
        p=self.source([post(),post('FAKEA1002')]);ingest(p,self.store,max_records=1)
        self.batch([post('FAKEA1003')])
        with self.assertRaisesRegex(ValueError,'Base avançou'):ingest(p,self.store)

    def test_exception_between_chunks_resumes_from_disk(self):
        p=self.source([post(),post('FAKEA1002'),post('FAKEA1003')])
        def interrupted(path,value):
            if path.name=='chunk_00000001.json': raise OSError('simulated interrupted write')
            return atomic_json(path,value)
        with patch('lotes_incrementais.atomic_json',side_effect=interrupted):
            with self.assertRaises(OSError):ingest(p,self.store,chunk_size=1)
        result=ingest(p,self.store,chunk_size=1)
        self.assertEqual(result['metrics']['new'],3);self.assertEqual(len(self.catalog(result)),3)

    def test_optional_collector_preview_never_imports_network_client(self):
        from instagram_collect import main
        with patch('sys.argv',['instagram_collect.py','--profiles','example_public']):
            with patch.dict(sys.modules,{'instagrapi':None}):main()

    def test_optional_collector_resume_with_fake_client_only(self):
        from instagram_collect import collect_profiles
        calls=[]
        class Media:
            def model_dump(self,mode):return post()
        class Client:
            fail=True
            def user_id_from_username(self,profile):return profile
            def user_medias(self,profile,limit):
                calls.append(profile)
                if profile=='perfil_b' and self.fail:raise RuntimeError('synthetic source failure')
                return [Media()]
        client=Client();output=self.root/'acquired.jsonl'
        with self.assertRaises(RuntimeError):
            collect_profiles(client,['perfil_a','perfil_b'],output,delay_seconds=0,authorization='SYNTHETIC_TEST_ONLY')
        self.assertEqual(load(output.with_suffix('.jsonl.acquisition.json'))['status'],'failed')
        with self.assertRaises(ValueError):ingest(output,self.store)
        client.fail=False
        result=collect_profiles(client,['perfil_a','perfil_b'],output,delay_seconds=0,resume=True,authorization='SYNTHETIC_TEST_ONLY')
        self.assertEqual(result['status'],'complete');self.assertEqual(calls,['perfil_a','perfil_b','perfil_b'])
        batch=ingest(output,self.store)
        self.assertEqual(batch['metrics']['new'],1);self.assertEqual(batch['metrics']['duplicates'],1)
        self.assertEqual(self.catalog(batch)[0]['_source_profiles'],['perfil_a','perfil_b'])

if __name__=='__main__':unittest.main()
