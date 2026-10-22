"""Ensaio exclusivamente sintético A1/A2/A5. D1 opcional, sempre isolado e local.

Não coleta, não chama LLM, não promove registry real. Saída nova obrigatória.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import resource
import shutil
import sqlite3
import subprocess
import tempfile
import time
import tracemalloc

from lotes_incrementais import ingest, sha, atomic_json
from resolver_entidades import resolve, read_jsonl, jsonl_write, json_write, csv_write
from preparar_publicacao import transform
from gerar_seed import make_seed
from reconciliar_d1_local import snapshot, proposal_plan, sql_update, sql_verify, verify_snapshot
from auditar_reconciliacao import audit
from extrair_llm import messages_for

ROOT=Path(__file__).resolve().parents[1]
STAMP=datetime(2026,10,22,12,tzinfo=timezone.utc)


def raw(code,profile='test_profile',caption=None):
    return dict(code=code,_profile_username=profile,user={'username':'synthetic_owner'},
                taken_at='2026-10-22T10:00:00-03:00',caption_text=caption or
                ('Restaurante Café Sintético em BH. Rua Teste, 1, Centro. Cardápio e reservas. '*2))


def prepared(rows):
    items=[]
    for row in rows:
        code=row['code'];number=1 if code in ('SYNTHA1001','SYNTHA1002') else 2 if code=='SYNTHA1003' else 3
        ext=dict(post_code=code,extraction_status='ok',content_type='place',
                 main_entity={'name':'Café Sintético'},event={},
                 location={'city':'BH','address':f'Rua Teste, {number}','neighborhood':'Centro'},
                 classification={'category':'café','tags':['café']},commercial_info={},
                 quality={'confidence_overall':.99 if code=='SYNTHA1002' else .9,'risk_flags':[]})
        # Aprovação somente de fixture, sem qualquer ligação com os registros reais.
        editorial=dict(post_code=code,publish_status='published',display_title='Café Sintético',
                       review_notes='SYNTHETIC_TEST_ONLY')
        item,status,_=transform(editorial,ext,STAMP);assert status=='published';items.append(item)
    return items


def scale(out):
    measurements=[]
    for size in (100,500,1000,5000):
        folder=out/f'scale_{size}';folder.mkdir()
        rows=[raw(f'SCALE{i:06d}') for i in range(size)]
        # 20% de observações repetidas, nunca taxa de duplicação de dados reais.
        rows+=rows[:size//5];source=folder/'input.jsonl';jsonl_write(source,rows)
        tracemalloc.start();start=time.perf_counter();m=ingest(source,folder/'store')
        dedupe_seconds=time.perf_counter()-start;_,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
        places=[]
        for i in range(size):
            places.append(dict(id=f'scale_{i:06d}',source_id=f'SCALE{i:06d}',source_url=f'https://www.instagram.com/p/SCALE{i:06d}/',
                               type='place',status='published',title=f'Lugar {i}',city='BH',address=f'Rua Teste, {i+1}',
                               neighborhood=f'Bairro {i//25}',search_text='cafe'))
        start=time.perf_counter();r=resolve(places,now=STAMP);a2_seconds=time.perf_counter()-start
        reverse=resolve(list(reversed(places)),now=STAMP);assert r==reverse
        json_write(folder/'entity_report.json',r['report'])
        measurements.append(dict(unique_posts=size,received=len(rows),duplicates=m['metrics']['duplicates'],
            duplication_ratio=m['metrics']['duplicates']/len(rows),dedupe_seconds=dedupe_seconds,a2_seconds=a2_seconds,
            python_peak_mb=peak/1024**2,process_maxrss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            entities=r['report']['entity_count'],candidates=r['report']['merge_candidates'],ids_stable=True,
            files=sum(p.is_file() for p in folder.rglob('*')),errors=0))
    json_write(out/'scale.json',measurements)


def integration(out, use_d1):
    logs=[]
    def command(args):
        p=subprocess.run(args,capture_output=True,text=True,encoding='utf-8')
        logs.append(dict(args=args,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr));json_write(out/'commands.json',logs)
        if p.returncode:raise RuntimeError(p.stdout+p.stderr)
        return p.stdout
    store=out/'store';first=out/'batch1.jsonl';second=out/'batch2.jsonl'
    jsonl_write(first,[raw('SYNTHA1001'),raw('SYNTHA1003')])
    jsonl_write(second,[raw('SYNTHA1001','second_profile'),raw('SYNTHA1002'),raw('SYNTHA1004'),
                       raw('SYNTHA1002','second_profile')])
    a=ingest(first,store,batch_id='synthetic_initial');b=ingest(second,store,batch_id='synthetic_increment')
    assert ingest(second,store,batch_id='synthetic_increment')==b
    catalog1=read_jsonl(store/'batches'/a['batch_id']/'catalog.jsonl')
    catalog2=read_jsonl(store/'batches'/b['batch_id']/'catalog.jsonl')
    items1=prepared(catalog1);items2=prepared(catalog2)
    initial=resolve(items1,now=STAMP);resolved=resolve(items2,registry=initial['registry'],now=STAMP)
    assert resolved==resolve(list(reversed(items2)),registry=initial['registry'],now=STAMP)
    keep=next(x['id'] for x in initial['catalog'] if x['source_id']=='SYNTHA1001')
    assert keep in [x['id'] for x in resolved['catalog']]
    partial=resolve([x for x in items2 if x['source_id']=='SYNTHA1002'],registry=resolved['registry'],now=STAMP)
    assert partial['catalog'][0]['id']==keep and len(partial['registry']['sources'])==4
    entitydir=out/'entities';entitydir.mkdir()
    jsonl_write(entitydir/'search_items_canonical.jsonl',resolved['catalog'])
    csv_write(entitydir/'source_entity_map.csv',list(resolved['source_map'][0]),resolved['source_map'])
    json_write(entitydir/'entity_registry.proposed.json',resolved['registry']);json_write(entitydir/'entity_report.json',resolved['report'])
    triage=out/'triage'
    command(['python3' if shutil.which('python3') else 'python',str(ROOT/'etl/triagem_avancada.py'),
             '--input',str(store/'batches'/b['batch_id']/'delta.jsonl'),'--outdir',str(triage)])
    queue=read_jsonl(triage/'dia1_fila_llm_100.jsonl');assert len(queue)==2
    for row in queue:assert len(messages_for(row))==2
    json_write(out/'triage_contract.json',dict(queue_count=len(queue),prompt_unchanged=True,paid_calls=0))
    if not use_d1:
        json_write(out/'integration.json',dict(a1=[a['metrics'],b['metrics']],a2=resolved['report'],ids_stable=True,d1='not requested'));return
    # --wrangler só aceita saída sob db/reconciliation; único mount gravável da API é .wrangler.
    relative=out.relative_to(ROOT);assert relative.parts[:2]==('db','reconciliation')
    persist='.wrangler/a1_'+out.name+'/state';assert not (ROOT/persist).exists()
    def d1(name,sql=None,file=None):
        args=['docker','compose','run','--rm','--no-deps','-T','api','npx','wrangler','d1','execute','oncovo-db',
              '--local','--persist-to',persist,'--json']
        args+=['--file',str(file.relative_to(ROOT))] if file else ['--command='+sql]
        raw_result=command(args);data=json.loads(raw_result);json_write(out/(name+'.json'),data);return data
    def apply(name,sql):
        file=out/(name+'.sql');file.write_text(sql,encoding='utf-8');return d1(name,file=file)
    select='SELECT id,source_id,status,type,title,address,updated_at FROM search_items ORDER BY id'
    # Schema e seed somente na nova persistência sintética.
    jsonl_write(out/'initial.jsonl',initial['catalog']);make_seed(out/'initial.jsonl',out/'initial_seed.sql')
    apply('init',(ROOT/'db/schema.sql').read_text()+(out/'initial_seed.sql').read_text())
    # Cópia offline: nenhum serviço usa esta persistência, todos os one-offs encerraram.
    shutil.copytree(ROOT/persist,out/'backup')
    backup={str(p.relative_to(out/'backup')):sha(p) for p in (out/'backup').rglob('*') if p.is_file()}
    json_write(out/'backup_manifest.json',backup)
    assert all(sha(out/'backup'/p)==digest for p,digest in backup.items())
    jsonl_write(out/'legacy_new.jsonl',[x for x in items2 if x['source_id'] in ('SYNTHA1002','SYNTHA1004')])
    make_seed(out/'legacy_new.jsonl',out/'legacy_new.sql');d1('legacy_new',file=out/'legacy_new.sql')
    make_seed(entitydir/'search_items_canonical.jsonl',out/'canonical_seed.sql')
    d1('canonical_seed',file=out/'canonical_seed.sql');d1('canonical_repeat',file=out/'canonical_seed.sql')
    d1('before',sql=select);before=snapshot(out/'before.json')
    review=audit(before,resolved['catalog'],resolved['source_map'])['actions'];assert len(review)==1
    try:proposal_plan(before,resolved['catalog'],resolved['source_map'],review)
    except ValueError as exc:assert 'Nenhuma despublicação aprovada' in str(exc)
    else:raise AssertionError('Gate editorial falhou')
    for row in review:row.update(editorial_decision='approved_hide_duplicate',reviewed_by='SYNTHETIC_TEST_ONLY',reviewed_at='2026-10-22',
                                approval_reason='Fixture sintética de mesma unidade, não autorização real',approval_evidence_url='https://example.test/a1')
    plan=proposal_plan(before,resolved['catalog'],resolved['source_map'],review);json_write(out/'plan.json',plan)
    action=plan['actions'][0]
    apply('make_stale',"UPDATE search_items SET updated_at='STALE_TEST' WHERE id='"+action['old_id']+"';")
    apply('stale_apply',sql_update(plan,'apply'));d1('stale_snapshot',sql=select)
    assert not verify_snapshot(plan,snapshot(out/'stale_snapshot.json'))['passed']
    apply('reset_fixture',"UPDATE search_items SET updated_at='"+action['old_updated']+"' WHERE id='"+action['old_id']+"';")
    apply('apply',sql_update(plan,'apply'));check=apply('verify',sql_verify(plan,'hidden'))
    assert check[0]['results'][0]['reconciliation_check']=='PASS'
    d1('after',sql=select);after=snapshot(out/'after.json');assert verify_snapshot(plan,after)['passed']
    apply('apply_repeat',sql_update(plan,'apply'));d1('repeat',sql=select);assert snapshot(out/'repeat.json')==after
    affected={action['old_id']}
    assert {x['id']:x for x in before if x['id'] not in affected}=={x['id']:x for x in after if x['id'] not in affected}
    apply('rollback',sql_update(plan,'rollback',post_snapshot=after));d1('rolled_back',sql=select)
    rolled_back=snapshot(out/'rolled_back.json')
    assert verify_snapshot(plan,rolled_back,rolled_back=True)['passed']
    # Novo plano após rollback; nunca reutilizar timestamp anterior.
    fresh_plan=proposal_plan(rolled_back,resolved['catalog'],resolved['source_map'],review)
    apply('reapply_after_rollback',sql_update(fresh_plan,'apply'))
    d1('seed_after_a5',file=out/'canonical_seed.sql');d1('after_reseed',sql=select)
    reseeded=snapshot(out/'after_reseed.json')
    assert {r['id']:r['status'] for r in reseeded}=={r['id']:r['status'] for r in after}
    restored=persist.replace('/state','_restored/state');shutil.copytree(out/'backup',ROOT/restored)
    # Provar leitura da restauração pelo próprio D1 CLI.
    raw_restore=command(['docker','compose','run','--rm','--no-deps','-T','api','npx','wrangler','d1','execute','oncovo-db','--local',
                         '--persist-to',restored,'--json','--command='+select]);json_write(out/'restored.json',json.loads(raw_restore))
    restored_rows=snapshot(out/'restored.json');assert {x['id'] for x in restored_rows}=={x['id'] for x in initial['catalog']}
    # Comparar todas as colunas e metadados em cópias, incluindo o UPSERT desfeito.
    def tables(base):
        for p in base.rglob('*.sqlite'):
            db=sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True)
            try:
                names={x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if 'search_items' in names:return {name:db.execute(f'SELECT * FROM {name} ORDER BY 1').fetchall() for name in ('search_items','publication_meta')}
            finally:db.close()
    assert tables(out/'backup')==tables(ROOT/restored)
    json_write(out/'integration.json',dict(a1=[a['metrics'],b['metrics']],a2=resolved['report'],
        sql_check='PASS',snapshot_verify=True,ids_stable=True,repeat_unchanged=True,rollback=True,full_restore=True,
        stale_guard=True,editorial_gate=True,unrelated_preserved=True,reseed_keeps_hidden=True,initial_rows=2,after_rows=len(after),
        after_published=sum(x['status']=='published' for x in after),synthetic_only=True,persistence=persist))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--outdir',type=Path,required=True)
    p.add_argument('--wrangler',action='store_true');p.add_argument('--scale',action='store_true')
    args=p.parse_args();out=args.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
    integration(out,args.wrangler)
    if args.scale:scale(out)
    print('Evidências sintéticas:',out)

if __name__=='__main__':main()
