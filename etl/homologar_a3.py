"""Ensaio A1→A3→A4→A2→A5 com respostas sintéticas, sem rede paga.

--wrangler usa exclusivamente D1 novo isolado. Não promove decisões reais.
"""
import argparse
import copy
from datetime import datetime
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from zoneinfo import ZoneInfo
from a3_fixtures import fixture,fixture_plan,response
from common import read_jsonl,write_jsonl
from lotes_incrementais import ingest,load,sha,atomic_json
from extracao_versionada import execute,export_results,cached
from criar_revisao import make_review
from preparar_publicacao import transform
from resolver_entidades import resolve,json_write,jsonl_write,csv_write
from gerar_seed import make_seed
from reconciliar_d1_local import proposal_plan,sql_update,sql_verify,verify_snapshot
from auditar_reconciliacao import audit
from avaliar_extracoes import prepare,score

ROOT=Path(__file__).resolve().parents[1]
NOW=datetime(2026,10,22,12,tzinfo=ZoneInfo('America/Sao_Paulo'))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--outdir',type=Path,required=True)
    parser.add_argument('--wrangler',action='store_true');args=parser.parse_args()
    out=args.outdir.resolve();out.mkdir(parents=True,exist_ok=False);logs=[]
    def command(argv):
        p=subprocess.run(argv,capture_output=True,text=True,encoding='utf-8')
        logs.append(dict(args=argv,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr));json_write(out/'commands.json',logs)
        if p.returncode:raise RuntimeError(p.stdout+p.stderr)
        return p.stdout
    codes=['A3FLOW0001','A3FLOW0002','A3FLOW0003','A3FLOW0004','A3FLOW0005','A3FLOW0006','A3FLOW0007']
    pairs=[fixture(codes[0]),fixture(codes[1]),fixture(codes[2],address='Rua Teste, 2'),
           fixture(codes[3],kind='event',name='Show Sintético'),fixture(codes[4],kind='event',name='Show Antigo',date='2020-01-01'),
           fixture(codes[5],kind='promotion'),fixture(codes[6],kind='ambiguous')]
    fixtures={r['post_code']:(r,p) for r,p in pairs};fixtures[codes[1]][1]['quality']['confidence_overall']=.99
    store=out/'a3';a1=out/'a1';reports=[];prior_approvals={};registry=None;initial_items=None;final_items=None;plans=[]
    def raw(code,changed=False):
        row=copy.deepcopy(fixtures[code][0])
        if changed:row['caption_text_clean']+=' Legenda alterada nesta revisão sintética.'
        return dict(code=code,caption_text=row['caption_text_clean'],taken_at=row['taken_at'],
                    _profile_username='synthetic_profile',user=dict(username='synthetic_owner'))
    for number,records in enumerate(([raw(codes[0]),raw(codes[2])],
                                     [raw(codes[0]),raw(codes[0]),raw(codes[1]),raw(codes[3]),raw(codes[4]),raw(codes[5]),raw(codes[6])],
                                     [raw(codes[0],True)]),1):
        folder=out/f'batch{number}';folder.mkdir();file=folder/'raw.jsonl';write_jsonl(file,records)
        manifest=ingest(file,a1,batch_id=f'a3_synthetic_{number}');batch=a1/'batches'/manifest['batch_id']
        command([sys.executable,str(ROOT/'etl/triagem_avancada.py'),'--input',str(batch/'catalog.jsonl'),'--outdir',str(folder/'triage')])
        queue=list(read_jsonl(folder/'triage/dia1_posts_limpos.jsonl'))
        p=fixture_plan(queue,store,batch,triage_report=folder/'triage/dia1_resumo.json');plans.append(p);atomic_json(folder/'plan.json',p)
        def fake(req):
            payload=copy.deepcopy(fixtures[req['row']['post_code']][1])
            caption=req['row']['caption_text_clean']
            for ev in payload['quality']['evidence']:ev['quote']=caption
            return response(payload)
        options=dict(execute_authorized=True,approved_plan_id=p['plan_id'],authorization_reference='SYNTHETIC_TEST_ONLY',
                     budget='10',max_requests=30,transport=fake,synthetic=True)
        run=execute(p,store,**options);repeat=execute(p,store,**options);assert repeat['calls']==0
        export=folder/'extractions.jsonl';export_results(p,store,export);extractions=list(read_jsonl(export))
        make_review(export,folder/'review_pending.jsonl');editorial=list(read_jsonl(folder/'review_pending.jsonl'))
        by_code={ext['post_code']:ext for ext in extractions}
        assert all(transform(row,by_code[row['post_code']],NOW)[1]!='published' for row in editorial)
        if number==3:
            old=prior_approvals[codes[0]]
            assert old['extraction_id']!=by_code[codes[0]]['extraction_id']
            assert transform(old,by_code[codes[0]],NOW)[1]=='review'
        for row in editorial:
            if row['content_type']=='ambiguous':continue
            if row['post_code'] in prior_approvals and prior_approvals[row['post_code']]['extraction_id']==row['extraction_id']:
                row.update(prior_approvals[row['post_code']])
            else:row.update(publish_status='published',reviewed_by='SYNTHETIC_TEST_ONLY',reviewed_at='2026-10-22',
                            approval_reason='Aprovação exclusivamente de fixture, sem aprovação real',currentness_recheck_required=False)
        items=[];statuses={}
        for row in editorial:
            item,status,_=transform(row,by_code[row['post_code']],NOW);statuses[row['post_code']]=status
            if item:items.append(item)
        prior_approvals={row['post_code']:row for row in editorial}
        resolved=resolve(items,registry=registry,now=NOW)
        if registry:
            keep=registry['sources']['instagram:'+codes[0]]['card_id']
            assert resolved['registry']['sources']['instagram:'+codes[1]]['card_id']==keep
        registry=resolved['registry']
        if number==1:initial_items=resolved['catalog']
        final_items=items;canonical=resolved
        write_jsonl(folder/'approved_FIXTURE_ONLY.jsonl',editorial);write_jsonl(folder/'prepared.jsonl',items)
        json_write(folder/'entity_report.json',resolved['report'])
        reports.append(dict(batch=number,a1=manifest['metrics'],a3=p['metrics'],run=run,repeat=repeat,statuses=statuses,a2=resolved['report']))
    assert len(canonical['catalog'])==3
    assert reports[1]['statuses'][codes[4]]=='expired' and reports[1]['statuses'][codes[5]]=='hidden'
    assert reports[1]['statuses'][codes[6]]=='review'
    jsonl_write(out/'canonical.jsonl',canonical['catalog']);csv_write(out/'source_entity_map.csv',list(canonical['source_map'][0]),canonical['source_map'])
    json_write(out/'entity_registry.proposed.json',canonical['registry'])
    final_ext=list(read_jsonl(out/'batch3/extractions.jsonl'));prepare(final_ext,out/'quality_reference_pending.jsonl',20)
    json_write(out/'quality_report.json',score(final_ext,list(read_jsonl(out/'quality_reference_pending.jsonl'))))
    # SQLite em memória ou Wrangler real com a mesma sequência SQL, sempre fixture.
    if args.wrangler:
        relative=out.relative_to(ROOT)
        if relative.parts[:2]!=('db','reconciliation'):raise ValueError('Saída D1 deve estar sob db/reconciliation')
        persist='.wrangler/a3_'+out.name+'/state'
        if (ROOT/persist).exists():raise ValueError('Persistência já existe')
    else:
        db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
    def sql(name,statement):
        file=out/(name+'.sql');file.write_text(statement,encoding='utf-8')
        if args.wrangler:
            raw_result=command(['docker','compose','run','--rm','--no-deps','-T','api','npx','wrangler','d1','execute','oncovo-db',
                               '--local','--persist-to',persist,'--json','--file',str(file.relative_to(ROOT))])
            data=json.loads(raw_result)
        else:
            # SELECT único retorna rows; demais scripts aplicados pelo SQLite.
            if statement.lstrip().startswith('SELECT'):data=[dict(row) for row in db.execute(statement)]
            else:db.executescript(statement);data=[]
        json_write(out/(name+'.json'),data);return data
    select='SELECT id,source_id,status,type,title,address,updated_at FROM search_items ORDER BY id'
    def snap(name):
        result=sql(name,select);return result[0]['results'] if args.wrangler else result
    jsonl_write(out/'initial.jsonl',initial_items);make_seed(out/'initial.jsonl',out/'initial_seed.sql')
    sql('init',(ROOT/'db/schema.sql').read_text()+(out/'initial_seed.sql').read_text())
    if args.wrangler:
        shutil.copytree(ROOT/persist,out/'backup')
        hashes={str(p.relative_to(out/'backup')):sha(p) for p in (out/'backup').rglob('*') if p.is_file()}
        assert all(sha(out/'backup'/p)==h for p,h in hashes.items());json_write(out/'backup_manifest.json',hashes)
    jsonl_write(out/'legacy_increment.jsonl',[r for r in final_items if r['source_id'] not in (codes[0],codes[2])])
    make_seed(out/'legacy_increment.jsonl',out/'legacy_increment.sql');sql('legacy_increment',(out/'legacy_increment.sql').read_text())
    make_seed(out/'canonical.jsonl',out/'canonical_seed.sql');seed=(out/'canonical_seed.sql').read_text();sql('seed',seed)
    before=snap('before');review=audit(before,canonical['catalog'],canonical['source_map'])['actions'];assert len(review)==1
    try:proposal_plan(before,canonical['catalog'],canonical['source_map'],review)
    except ValueError as exc:assert 'Nenhuma despublicação aprovada' in str(exc)
    else:raise AssertionError('A5 deveria bloquear ausência de aprovação')
    for row in review:row.update(editorial_decision='approved_hide_duplicate',reviewed_by='SYNTHETIC_TEST_ONLY',reviewed_at='2026-10-22',
                                approval_reason='Somente fixture A3 de mesma unidade física',approval_evidence_url='https://example.test/a3')
    a5=proposal_plan(before,canonical['catalog'],canonical['source_map'],review);json_write(out/'a5_plan.json',a5)
    sql('a5_apply',sql_update(a5,'apply'));checks=sql('a5_verify',sql_verify(a5,'hidden'))
    if args.wrangler:assert checks[0]['results'][0]['reconciliation_check']=='PASS'
    else:assert db.execute(sql_verify(a5,'hidden').split(';')[0]).fetchone()[0]=='PASS'
    after=snap('after');assert verify_snapshot(a5,after)['passed']
    sql('a5_repeat',sql_update(a5,'apply'));assert snap('after_repeat')==after
    sql('rollback',sql_update(a5,'rollback',post_snapshot=after));rolled=snap('rolled_back');assert verify_snapshot(a5,rolled,rolled_back=True)['passed']
    fresh=proposal_plan(rolled,canonical['catalog'],canonical['source_map'],review)
    sql('reapply',sql_update(fresh,'apply'));sql('seed_after_a5',seed)
    reseeded=snap('after_reseed');assert {r['id']:r['status'] for r in reseeded}=={r['id']:r['status'] for r in after}
    summary=dict(synthetic_only=True,provider_calls_real=0,batches=reports,prompt_sha256=sha(ROOT/'etl/prompts/maritaca_legacy_v2.txt'),
                 a5=dict(sql='PASS',verify=True,idempotent=True,rollback=True,reseed_keeps_hidden=True,
                         total=len(after),published=sum(r['status']=='published' for r in after)),
                 d1='Wrangler LOCAL isolated' if args.wrangler else 'SQLite in-memory',human_ground_truth_real=0)
    json_write(out/'integration.json',summary);print('Homologação sintética A3/A4:',out)

if __name__=='__main__':main()
