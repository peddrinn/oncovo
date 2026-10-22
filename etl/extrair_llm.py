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

def messages_for(row:dict, *, prompt_path:Path|None=None)->list[dict]:
    prompt=(prompt_path or PROMPT).read_text(encoding='utf-8')
    marker='Transforme o post abaixo no schema JSON obrigatório.'
    if marker not in prompt or '{post_json}' not in prompt:raise RuntimeError('Template de prompt inválido')
    system,user=prompt.split(marker,1)
    trimmed={
        'taken_at':row.get('taken_at'),
        'caption_text_clean':str(row.get('caption_text_clean') or row.get('caption_text') or '')[:4500],
        'media_owner_username':row.get('media_owner_username'),
        'location_name':row.get('location_name'),
        'location_address':row.get('location_address'),
        'mentions':row.get('mentions') or [],
        'coauthors':row.get('coauthors') or [],
    }
    rendered=marker+user.replace('{post_json}',json.dumps(trimmed,ensure_ascii=False,separators=(',',':')))
    return [{'role':'system','content':system.strip()},{'role':'user','content':rendered}]

def parse_text(raw:str)->dict:
    text=raw.strip()
    if text.startswith('```'):
        text=text.split('\n',1)[1].rsplit('```',1)[0].strip()
    return validate(json.loads(text))

def extract(row:dict,api_key:str,model:str,max_tokens:int)->dict:
    raise RuntimeError('Inferência direta desativada: use plano A3 aprovado e limites de orçamento')

def run(args):
    """CLI legado encaminhado ao planejador A3; não usa mais cache só por post_code."""
    from extracao_versionada import main as versioned_main
    argv=['--input',str(args.input),'--model',args.model,'--max-items',str(args.max_items),
          '--max-tokens',str(args.max_tokens),'--report',str(getattr(args,'report',Path('etl/output/a3_plan.json')))]
    for name in ('batch','store','pricing','token_bounds','triage_report','approved_plan_id','authorization_reference','budget','retry_reference'):
        value=getattr(args,name,None)
        if value is not None:argv+=['--'+name.replace('_','-'),str(value)]
    if args.execute:argv+=['--execute']
    # Export é explícito; uma prévia nunca cria fila vazia sobre arquivo histórico.
    if getattr(args,'export',False):argv+=['--output',str(args.output)]
    return versioned_main(argv)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--input',type=Path,default=Path('etl/processed/dia1/dia1_fila_llm_100.jsonl'))
    p.add_argument('--output',type=Path,default=Path('etl/processed/extracoes.jsonl'))
    p.add_argument('--model',default=os.environ.get('MARITACA_MODEL','sabia-4'))
    p.add_argument('--max-items',type=int,default=10)
    p.add_argument('--max-tokens',type=int,default=2500)
    p.add_argument('--execute',action='store_true')
    p.add_argument('--export',action='store_true')
    p.add_argument('--report',type=Path,default=Path('etl/output/a3_plan.json'))
    p.add_argument('--batch',type=Path);p.add_argument('--store',type=Path)
    p.add_argument('--pricing',type=Path);p.add_argument('--token-bounds',type=Path)
    p.add_argument('--triage-report',type=Path)
    p.add_argument('--approved-plan-id');p.add_argument('--authorization-reference')
    p.add_argument('--budget');p.add_argument('--retry-reference')
    a=p.parse_args()
    if not 1<=a.max_items<=1000 or not 500<=a.max_tokens<=5000: p.error('Limites inválidos')
    run(a)
