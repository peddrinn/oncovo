"""A3: plano offline, cache por solicitação/evidência e execução opt-in limitada.

Histórico em arquivos atômicos, sem banco novo. Synthetic nunca compartilha cache live.
"""
from __future__ import annotations
import argparse
import copy
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import os
from pathlib import Path
import time
import urllib.error
import urllib.request
import uuid

from common import read_jsonl, safe_source_url
from lotes_incrementais import atomic_json, locked, load, check_files, sha, now
from validacao_extracao import validate_versioned

CONTRACT='a3-v1'


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def request_for(row, *, model='sabia-4', max_tokens=2500, temperature=0, prompt=None, provider='maritaca'):
    from extrair_llm import messages_for, PROMPT
    if not safe_source_url(str(row.get('post_code') or '')):raise ValueError('post_code inválido')
    if row.get('platform','instagram')!='instagram':raise ValueError('Plataforma incompatível')
    if not model or not isinstance(max_tokens,int) or isinstance(max_tokens,bool) or not 1<=max_tokens<=5000:
        raise ValueError('Modelo/limite inválido')
    if not isinstance(temperature,(int,float)) or not math.isfinite(temperature) or not 0<=temperature<=2:raise ValueError('temperature inválida')
    prompt_path=prompt or PROMPT
    messages=messages_for(row,prompt_path=prompt_path)
    identity=dict(platform='instagram',post_code=row['post_code'],input_hash=digest(messages[1]['content']),
                  prompt_hash=sha(prompt_path),model=model,parameters=dict(max_tokens=max_tokens,temperature=temperature),
                  contract_version=CONTRACT,provider=provider)
    return dict(request_id=digest(identity),identity=identity,messages=messages)


def result_digest(ext):
    return digest({k:v for k,v in ext.items() if k not in ('extraction_id',)})


def cached(store, request):
    folder=store/'results'/request['request_id']
    for path in sorted(folder.glob('*.json')):
        ext=load(path)
        if ext.get('extraction_id')!=result_digest(ext) or ext.get('request_identity')!=request['identity']:
            raise ValueError('Resultado com hash/identidade divergente: '+path.name)
        if ext.get('finish_reason')!='stop':continue
        validated,checks=validate_versioned(ext['raw_response'],request['messages'])
        if validated!=ext['validated_payload'] or any(ext.get(k)!=v for k,v in validated.items()):raise ValueError('Resultado normalizado divergente')
        if validated['extraction_status'] in ('ok','discard') and not checks['issues'] and ext['finish_reason']=='stop':return ext
    return None


def rate(value):
    if value is None:return None
    try:result=Decimal(str(value))
    except InvalidOperation as exc:raise ValueError('Preço/orçamento inválido') from exc
    if not result.is_finite() or result<0:raise ValueError('Preço/orçamento inválido')
    return result


def cost(input_tokens,output_tokens,pricing):
    if not pricing or rate(pricing.get('input_per_million')) is None or rate(pricing.get('output_per_million')) is None:return None
    return str((Decimal(input_tokens)*rate(pricing['input_per_million'])+Decimal(output_tokens)*rate(pricing['output_per_million']))/Decimal(1000000))


def plan(rows,store, *, batch=None, model='sabia-4', max_tokens=2500, temperature=0,
         prompt=None, provider='maritaca',pricing=None,bounds=None,triage_report=None):
    rows=list(rows);batch_id=None;batch_metrics={};catalog=None
    if batch:
        manifest=load(batch/'manifest.json')
        if manifest.get('status')!='complete':raise ValueError('A1 deve estar completa')
        check_files(batch,manifest);batch_id=manifest['batch_id'];batch_metrics=manifest['metrics']
        catalog={r['code']:r for r in read_jsonl(batch/'catalog.jsonl')}
    triage=load(triage_report) if triage_report else None
    if triage is not None:
        if not batch or triage.get('input_sha256') not in (sha(batch/'catalog.jsonl'),sha(batch/'delta.jsonl')):
            raise ValueError('Relatório de triagem não corresponde ao lote A1')
    requests=[];seen={};insufficient=[];discarded=0;reusable=0;changed=[]
    for row in rows:
        if row.get('triage_queue')=='descartar':discarded+=1;continue
        if catalog is not None:
            from triagem_avancada import normalize_text
            raw=catalog.get(row.get('post_code'))
            if not raw or (row.get('caption_text_clean') or row.get('caption_text') or '')!=normalize_text(raw.get('caption_text')) or row.get('taken_at')!=raw.get('taken_at'):
                raise ValueError('Entrada de triagem não corresponde ao lote A1')
        request=request_for(row,model=model,max_tokens=max_tokens,temperature=temperature,prompt=prompt,provider=provider)
        code=row['post_code']
        if code in seen:
            if seen[code]!=request['request_id']:raise ValueError('Duas revisões do mesmo post na fila; selecionar explicitamente a vigente')
            continue
        seen[code]=request['request_id']
        if len(str(row.get('caption_text_clean') or row.get('caption_text') or '').strip())<40:
            insufficient.append(code);continue
        hit=cached(store,request);reusable+=bool(hit)
        previous=[]
        for file in (store/'requests').glob('*.json'):
            old=load(file)
            if old['identity']['post_code']==code and old['identity']['input_hash']!=request['identity']['input_hash']:previous.append(old['request_id'])
        if previous:changed.append(code)
        encoded=json.dumps(request['messages'],ensure_ascii=False).encode('utf-8')
        estimate=math.ceil(len(encoded.decode('utf-8'))/3)
        bound=(bounds or {}).get(request['request_id'],{})
        ceiling=bound.get('max_input_tokens')
        trusted=(isinstance(ceiling,int) and not isinstance(ceiling,bool) and ceiling>=estimate
                 and bound.get('verified') is True and bool(bound.get('reference')))
        requests.append(dict(**request,row=copy.deepcopy(row),batch_id=batch_id,cached_extraction_id=hit['extraction_id'] if hit else None,
                             estimated_input_tokens=estimate,estimated_output_tokens=max_tokens,input_utf8_bytes=len(encoded),
                             token_bound=bound,execution_estimate_verified=trusted,
                             predicted_cost=cost(estimate,max_tokens,pricing),
                             reserved_cost=cost(ceiling,max_tokens,pricing) if trusted else None,
                             requires_content_review=bool(previous)))
    if pricing:
        rate(pricing.get('input_per_million'));rate(pricing.get('output_per_million'))
        if not pricing.get('currency') or not pricing.get('reference'):raise ValueError('Preço exige moeda e referência explícitas')
    base=dict(contract_version=CONTRACT,batch_id=batch_id,batch_manifest_sha256=sha(batch/'manifest.json') if batch else None,
              requests=[{k:v for k,v in r.items() if k!='cached_extraction_id'} for r in requests],pricing=pricing,
              triage_report_sha256=sha(triage_report) if triage_report else None)
    return dict({**base,'plan_id':digest(base),'requests':requests},
                metrics=dict(received=batch_metrics.get('received',len(rows)),new=batch_metrics.get('new'),changed=batch_metrics.get('changed'),
                             input_queue=len(rows),discarded_by_triage=triage['discarded_posts'] if triage else (discarded or None),eligible=len(requests),cache_hits=reusable,
                             new_inferences=len(requests)-reusable,content_review=len(changed),insufficient_caption=len(insufficient)),
                insufficient_post_codes=insufficient,
                estimates=dict(method='characters/3; approximate, not billed tokens',
                               input_tokens=sum(r['estimated_input_tokens'] for r in requests if not r['cached_extraction_id']),
                               output_tokens=sum(max_tokens for r in requests if not r['cached_extraction_id']),
                               predicted_cost=cost(sum(r['estimated_input_tokens'] for r in requests if not r['cached_extraction_id']),
                                                   sum(max_tokens for r in requests if not r['cached_extraction_id']),pricing),
                               actual_tokens=None,actual_cost=None))


def plan_identity(p):
    return digest(dict(contract_version=p['contract_version'],batch_id=p['batch_id'],batch_manifest_sha256=p['batch_manifest_sha256'],
                       requests=[{k:v for k,v in r.items() if k!='cached_extraction_id'} for r in p['requests']],pricing=p['pricing'],
                       triage_report_sha256=p.get('triage_report_sha256')))


def provider_call(request,api_key):
    from extrair_llm import ENDPOINT
    identity=request['identity'];payload=dict(model=identity['model'],messages=request['messages'],**identity['parameters'])
    req=urllib.request.Request(ENDPOINT,data=json.dumps(payload,ensure_ascii=False).encode(),method='POST',
                               headers={'Authorization':'Key '+api_key,'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=90) as response:
        data=json.load(response)
    choice=data['choices'][0]
    return dict(content=choice['message']['content'],finish_reason=choice.get('finish_reason'),usage=data.get('usage'),
                provider_model=data.get('model'),provider_request_id=data.get('id'))


def save_response(store,request,response,attempt_id):
    # Validação estrita usa a resposta original, não uma versão previamente reparada.
    content=response['content']
    if isinstance(content,str):
        text=content.strip()
        if text.startswith('```'):text=text.split('\n',1)[1].rsplit('```',1)[0].strip()
        raw=json.loads(text)
    else:raw=content
    normalized,checks=validate_versioned(raw,request['messages'])
    if response.get('finish_reason')!='stop':
        normalized['extraction_status']='partial';checks['issues'].append('incomplete_response')
    metadata=dict(request_id=request['request_id'],request_identity=request['identity'],batch_id=request.get('batch_id'),
                  provider=request['identity']['provider'],model=request['identity']['model'],contract_version=CONTRACT,
                  prompt_hash=request['identity']['prompt_hash'],input_hash=request['identity']['input_hash'],
                  raw_response=raw,validated_payload=normalized,validation=checks,finish_reason=response.get('finish_reason'),
                  usage=response.get('usage'),attempt_id=attempt_id,extracted_at=response.get('received_at'),
                  provider_model=response.get('provider_model'),provider_request_id=response.get('provider_request_id'))
    # Flatten para leitores históricos; a revisão versionada confere o digest integral.
    ext=dict(**copy.deepcopy(normalized),**metadata,post_code=request['identity']['post_code'],
             post_url=safe_source_url(request['identity']['post_code']),source_profile=request['row'].get('source_profile') or request['row'].get('source_profiles'))
    ext['extraction_id']=result_digest(ext)
    path=store/'results'/request['request_id']/(ext['extraction_id']+'.json')
    if not path.exists():atomic_json(path,ext)
    return ext


def execute(p,store, *, execute_authorized=False,approved_plan_id=None,authorization_reference=None,
            max_requests=10,budget=None,max_attempts=1,transport=None,synthetic=False,retry_reference=None,sleep=time.sleep):
    if plan_identity(p)!=p.get('plan_id'):raise ValueError('Plano alterado')
    if not execute_authorized or approved_plan_id!=p['plan_id'] or not authorization_reference:
        raise ValueError('Execução requer opt-in, aprovação do plan_id e referência de autorização')
    if not p['batch_id'] or not 1<=max_requests<=1000 or not 1<=max_attempts<=3:
        raise ValueError('Lote A1 completo e limites explícitos são obrigatórios')
    if not synthetic and any(r['identity']['provider']!='maritaca' for r in p['requests']):raise ValueError('Cache sintético não pode executar live')
    if synthetic and (transport is None or any(r['identity']['provider']!='synthetic-fixture' for r in p['requests'])):
        raise ValueError('Fixture exige transport injetado e provider sintético')
    cap=rate(budget)
    if cap is None or not p['pricing']:raise ValueError('Orçamento e preços explícitos obrigatórios')
    for request in p['requests']:
        if not request['execution_estimate_verified'] or request['reserved_cost'] is None:
            raise ValueError('Estimativa não verificada: obtenha limite de tokens com referência antes de executar')
    if not synthetic and transport is None and not os.environ.get('MARITACA_API_KEY'):raise ValueError('API key ausente')
    report=dict(plan_id=p['plan_id'],batch_id=p['batch_id'],started_at=now(),provider='synthetic-fixture' if synthetic else 'maritaca',calls=0,cache_hits=0,
                results=[],errors=[],reserved_cost='0',actual_cost=None,usage_input_tokens=0,usage_output_tokens=0,
                unknown_usage_attempts=0,authorization_reference=authorization_reference,approved_budget=str(cap),
                currency=p['pricing']['currency'],max_requests=max_requests,max_attempts=max_attempts)
    with locked(store):
        if any(load(f).get('authorization_reference')==authorization_reference for f in (store/'budget_breaches').glob('*')):
            raise ValueError('Limite de tokens excedido anteriormente; revisar plano e autorização')
        # Reserva durável ANTES da rede: timeout/crash continua consumindo orçamento conservador.
        reservations=[load(f) for f in (store/'attempts').glob('*.json')]
        own=[x for x in reservations if x['authorization_reference']==authorization_reference]
        if any(x['currency']!=p['pricing']['currency'] for x in own):raise ValueError('Moeda mudou na mesma autorização')
        spent=sum((rate(x['reserved_cost']) for x in own),Decimal(0));count=len(own)
        for request in p['requests']:
            request_id=request['request_id'];req_path=store/'requests'/(request_id+'.json')
            if req_path.exists():
                old=load(req_path)
                if old['identity']!=request['identity'] or old['messages']!=request['messages']:raise ValueError('Solicitação armazenada divergente')
            else:atomic_json(req_path,request)
            # Recupera resposta já recebida sem repetir inferência após falha de gravação final.
            for reservation in [x for x in reservations if x['request_id']==request_id]:
                response_path=store/'responses'/(reservation['attempt_id']+'.json')
                outcome=store/'outcomes'/(reservation['attempt_id']+'.json')
                if response_path.exists() and not outcome.exists():
                    try:
                        ext=save_response(store,request,load(response_path),reservation['attempt_id'])
                        atomic_json(outcome,dict(status='recovered',extraction_id=ext['extraction_id']))
                    except (ValueError,KeyError,TypeError,IndexError):atomic_json(outcome,dict(status='invalid_response'))
            hit=cached(store,request)
            if hit:
                report['cache_hits']+=1;report['results'].append(hit['extraction_id']);continue
            previous=[x for x in reservations if x['request_id']==request_id]
            if previous and not retry_reference:
                report['errors'].append(dict(request_id=request_id,error='previous_attempt_requires_explicit_retry'));continue
            for attempt in range(max_attempts):
                reserve=rate(request['reserved_cost'])
                if count>=max_requests or spent+reserve>cap:
                    report['errors'].append(dict(request_id=request_id,error='quantity_or_budget_limit'));break
                aid=uuid.uuid4().hex
                reservation=dict(attempt_id=aid,plan_id=p['plan_id'],request_id=request_id,reserved_cost=str(reserve),
                                 started_at=now(),currency=p['pricing']['currency'],pricing=p['pricing'],authorization_reference=authorization_reference,retry_reference=retry_reference)
                atomic_json(store/'attempts'/(aid+'.json'),reservation)
                reservations.append(reservation);spent+=reserve;count+=1;report['calls']+=1
                response=None
                try:
                    if transport is None:
                        key=os.environ.get('MARITACA_API_KEY')
                        if not key:raise ValueError('API key ausente')
                        response=provider_call(request,key)
                    else:response=transport(request)
                    if isinstance(response,dict):response.setdefault('received_at',now())
                    atomic_json(store/'responses'/(aid+'.json'),response)
                    ext=save_response(store,request,response,aid)
                    atomic_json(store/'outcomes'/(aid+'.json'),dict(status=ext['extraction_status'],extraction_id=ext['extraction_id']))
                    report['results'].append(ext['extraction_id'])
                    if ext['extraction_status'] in ('partial','error'):
                        report['errors'].append(dict(request_id=request_id,error=ext['extraction_status']+'_requires_review'))
                    break
                except (urllib.error.URLError,TimeoutError,ValueError,KeyError,TypeError,IndexError) as exc:
                    code=getattr(exc,'code',None)
                    atomic_json(store/'outcomes'/(aid+'.json'),dict(status='error',error_type=type(exc).__name__,http_status=code,billing='unknown'))
                    report['errors'].append(dict(request_id=request_id,error=type(exc).__name__,http_status=code))
                    transient=(isinstance(exc,(TimeoutError,urllib.error.URLError)) and (code is None or code in (429,500,502,503,504)))
                    if not transient or attempt+1>=max_attempts:break
                    sleep(2**attempt)
                finally:
                    usage=response.get('usage') if isinstance(response,dict) else None
                    if isinstance(usage,dict) and all(isinstance(usage.get(k),int) and not isinstance(usage[k],bool) and usage[k]>=0 for k in ('prompt_tokens','completion_tokens')):
                        report['usage_input_tokens']+=usage['prompt_tokens'];report['usage_output_tokens']+=usage['completion_tokens']
                        if usage['prompt_tokens']>request['token_bound']['max_input_tokens'] or usage['completion_tokens']>request['identity']['parameters']['max_tokens']:
                            atomic_json(store/'budget_breaches'/p['plan_id'],dict(attempt_id=aid,usage=usage,authorization_reference=authorization_reference))
                    else:report['unknown_usage_attempts']+=1
                if (store/'budget_breaches'/p['plan_id']).exists():break
            if (store/'budget_breaches'/p['plan_id']).exists():break
            if report['unknown_usage_attempts']:break
        report['reserved_cost']=str(spent)
        report['actual_cost']=cost(report['usage_input_tokens'],report['usage_output_tokens'],p['pricing']) if not report['unknown_usage_attempts'] else None
        report['actual_cost_basis']='provider-reported usage * supplied prices; not an invoice; synthetic usage is fixture only'
        ledger=dict(attempts=0,input_tokens=0,output_tokens=0,unknown_usage_attempts=0,usage_priced_cost='0')
        known_cost=Decimal(0)
        for reservation in [x for x in reservations if x['authorization_reference']==authorization_reference]:
            ledger['attempts']+=1
            file=store/'responses'/(reservation['attempt_id']+'.json')
            usage=load(file).get('usage') if file.exists() else None
            if isinstance(usage,dict) and all(isinstance(usage.get(k),int) and not isinstance(usage[k],bool) and usage[k]>=0 for k in ('prompt_tokens','completion_tokens')):
                ledger['input_tokens']+=usage['prompt_tokens'];ledger['output_tokens']+=usage['completion_tokens']
                amount=cost(usage['prompt_tokens'],usage['completion_tokens'],reservation.get('pricing'))
                if amount is None:ledger['unknown_usage_attempts']+=1
                else:known_cost+=rate(amount)
            else:ledger['unknown_usage_attempts']+=1
        ledger['usage_priced_cost']=None if ledger['unknown_usage_attempts'] else str(known_cost)
        report['authorization_ledger']=ledger
        report['finished_at']=now()
        atomic_json(store/'runs'/(uuid.uuid4().hex+'.json'),report)
    return report


def export_results(p,store,target):
    from common import write_jsonl
    if target.exists():raise ValueError('Não sobrescrever export/histórico existente')
    rows=[]
    for request in p['requests']:
        hit=cached(store,request)
        if hit:rows.append(hit)
        else:
            # Partial também alimenta revisão, nunca cache válido/publicação automática.
            candidates=sorted((store/'results'/request['request_id']).glob('*.json'))
            if len(candidates)>1:raise ValueError('Múltiplas respostas parciais: selecionar versão explicitamente para revisão')
            if candidates:
                ext=load(candidates[-1])
                if ext['extraction_id']!=result_digest(ext):raise ValueError('Extração corrompida')
                rows.append(ext)
    write_jsonl(target,rows)
    return len(rows)


def import_legacy(source,store):
    from validacao_extracao import validate
    rows=list(read_jsonl(source))  # lê integralmente antes de qualquer escrita
    source_sha=sha(source);imported=[]
    with locked(store):
        for index,row in enumerate(rows):
            try:validate(copy.deepcopy(row));status='legacy_unverified'
            except ValueError:status='legacy_invalid'
            record=dict(provenance=status,original=row,source_sha256=source_sha,source_line=index+1,
                        prompt_model_identity_verified=False)
            pk=digest(record);path=store/'legacy'/(pk+'.json')
            if not path.exists():atomic_json(path,record)
            imported.append(pk)
    return imported


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True);p.add_argument('--batch',type=Path)
    p.add_argument('--store',type=Path,default=Path('etl/processed/a3'));p.add_argument('--report',type=Path,required=True)
    p.add_argument('--model',default='sabia-4');p.add_argument('--max-tokens',type=int,default=2500)
    p.add_argument('--max-items',type=int,default=10);p.add_argument('--max-attempts',type=int,default=1)
    p.add_argument('--pricing',type=Path);p.add_argument('--token-bounds',type=Path)
    p.add_argument('--triage-report',type=Path)
    p.add_argument('--execute',action='store_true');p.add_argument('--approved-plan-id');p.add_argument('--authorization-reference')
    p.add_argument('--budget');p.add_argument('--retry-reference');p.add_argument('--output',type=Path)
    p.add_argument('--import-legacy',action='store_true')
    args=p.parse_args(argv)
    if args.import_legacy:
        imported=import_legacy(args.input,args.store);atomic_json(args.report,dict(imported=len(imported),classification='legacy_unverified_or_invalid'));return 0
    planned=plan(read_jsonl(args.input),args.store,batch=args.batch,model=args.model,max_tokens=args.max_tokens,
                 pricing=load(args.pricing) if args.pricing else None,bounds=load(args.token_bounds) if args.token_bounds else None,
                 triage_report=args.triage_report)
    existed=args.report.exists()
    if existed:
        old=load(args.report)
        if old.get('plan_id')!=planned['plan_id']:raise ValueError('Relatório existente pertence a outro plano; usar caminho novo')
    else:atomic_json(args.report,planned)
    if args.execute:
        if not existed:raise ValueError('Prévia gravada; revisar e aprovar este plano antes de executar')
        result=execute(planned,args.store,execute_authorized=True,approved_plan_id=args.approved_plan_id,
                       authorization_reference=args.authorization_reference,max_requests=args.max_items,
                       max_attempts=args.max_attempts,budget=args.budget,retry_reference=args.retry_reference)
        print(json.dumps(result,ensure_ascii=False,indent=2))
    else:print(json.dumps(dict(plan_id=planned['plan_id'],metrics=planned['metrics'],estimates=planned['estimates'],execution='NOT executed'),ensure_ascii=False,indent=2))
    if args.output:export_results(planned,args.store,args.output)
    return 0

if __name__=='__main__':raise SystemExit(main())
