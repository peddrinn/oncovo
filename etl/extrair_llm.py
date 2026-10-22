"""Extração Maritaca (offline, aprovação humana). Sem gasto por padrão.

Prompt rigoroso histórico versionado em etl/prompts/maritaca_legacy_v2.txt.
IDs/URLs não são solicitados ao LLM (economia de tokens); Python injeta pela chave local.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from common import read_jsonl, safe_source_url
from validacao_extracao import validate

PROMPT_VERSION='maritaca-legacy-v2'
PROMPT=Path(__file__).resolve().parent/'prompts/maritaca_legacy_v2.txt'
ENDPOINT='https://chat.maritaca.ai/api/chat/completions'

def messages_for(row:dict)->list[dict]:
    prompt=PROMPT.read_text(encoding='utf-8')
    marker='Transforme o post abaixo no schema JSON obrigatório.'
    if marker not in prompt or '{post_json}' not in prompt:raise RuntimeError('Template de prompt inválido')
    system,user=prompt.split(marker,1)
    trimmed={
        'taken_at':row.get('taken_at'),
        'caption_text_clean':str(row.get('caption_text_clean') or row.get('caption_text') or '')[:4500],
        'source_profile':row.get('source_profile') or row.get('source_profiles'),
        'media_owner_username':row.get('media_owner_username'),
        'location_name':row.get('location_name'),
        'location_address':row.get('location_address'),
        'mentions':row.get('mentions') or [],
        'coauthors':row.get('coauthors') or [],
        'triage_class':row.get('triage_class'),
        'triage_score':row.get('triage_score'),
    }
    rendered=marker+user.replace('{post_json}',json.dumps(trimmed,ensure_ascii=False,separators=(',',':')))
    return [{'role':'system','content':system.strip()},{'role':'user','content':rendered}]

def parse_text(raw:str)->dict:
    text=raw.strip()
    if text.startswith('```'):
        text=text.split('\n',1)[1].rsplit('```',1)[0].strip()
    return validate(json.loads(text))

def extract(row:dict,api_key:str,model:str,max_tokens:int)->dict:
    payload={'model':model,'messages':messages_for(row),'temperature':0,'max_tokens':max_tokens}
    request=urllib.request.Request(ENDPOINT,data=json.dumps(payload,ensure_ascii=False).encode(),method='POST',
        headers={'Authorization':f'Key {api_key}','Content-Type':'application/json'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request,timeout=90) as r:
                resp=json.load(r)
            return parse_text(resp['choices'][0]['message']['content'])
        except urllib.error.HTTPError as ex:
            if ex.code not in (429,500,502,503,504) or attempt==2:raise RuntimeError(f'API HTTP {ex.code}') from None
        except (urllib.error.URLError,TimeoutError):
            if attempt==2: raise
        time.sleep(2**attempt)
    raise RuntimeError('Falha repetida de API')

def run(args):
    if not args.execute:
        print(f'PRÉVIA: {args.input}; modelo {args.model}; até {args.max_items} posts. Nenhuma chamada feita.')
        return 0
    key=os.environ.get('MARITACA_API_KEY')
    if not key: raise RuntimeError('Configure MARITACA_API_KEY no ambiente (não no repositório)')
    existing={str(i.get('post_code')) for i in read_jsonl(args.output)} if args.output.exists() else set()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    count=0
    with args.output.open('a',encoding='utf-8') as out:
        for row in read_jsonl(args.input):
            code=str(row.get('post_code') or '').strip()
            if code in existing or not safe_source_url(code):continue
            if count>=args.max_items:break
            try:
                item=extract(row,key,args.model,args.max_tokens)
                item['post_code']=code
                item['post_url']=safe_source_url(code)
                item['source_profile']=row.get('source_profile') or row.get('source_profiles')
                item['prompt_version']=PROMPT_VERSION
                item['extracted_at']=datetime.now(timezone.utc).isoformat()
                out.write(json.dumps(item,ensure_ascii=False)+'\n');out.flush()
                existing.add(code);count+=1
                print(f'Validado e salvo: {code}')
            except Exception as e:
                print(f'Falha em {code}: {type(e).__name__}: {e}',file=sys.stderr)
    print(f'Novas extrações: {count} em {args.output}')
    return count

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--input',type=Path,default=Path('etl/processed/dia1/dia1_fila_llm_100.jsonl'))
    p.add_argument('--output',type=Path,default=Path('etl/processed/extracoes.jsonl'))
    p.add_argument('--model',default=os.environ.get('MARITACA_MODEL','sabia-4'))
    p.add_argument('--max-items',type=int,default=10)
    p.add_argument('--max-tokens',type=int,default=2500)
    p.add_argument('--execute',action='store_true')
    a=p.parse_args()
    if not 1<=a.max_items<=1000 or not 500<=a.max_tokens<=5000: p.error('Limites inválidos')
    run(a)
