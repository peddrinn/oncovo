"""Auditoria offline do delta entre catálogo antigo e canônico.

Somente gera relatórios; nunca escreve SQL ou modifica o D1. Ausência de item
em snapshot parcial NÃO é evidência de exclusão. Propostas exigem aprovação
editorial e comparação com o estado efetivo do D1 antes de aplicação.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from resolver_entidades import csv_write, json_write, read_jsonl

FIELDS=['original_card_id','post_code','original_source_id','original_status','new_card_id',
        'entity_id','action','reason','editorial_decision','reviewed_by',
        'reviewed_at','evidence_url']


def _indexed(rows: list[dict], name: str) -> dict[str,dict]:
    mapping={}
    for row in rows:
        pk=row.get('id')
        if not isinstance(pk,str) or not pk:
            raise ValueError(f'{name}: id inválido')
        if pk in mapping:
            raise ValueError(f'{name}: id duplicado: {pk}')
        mapping[pk]=row
    return mapping


def _mapping(path: Path) -> list[dict]:
    with path.open(encoding='utf-8',newline='') as handle:
        mapping=list(csv.DictReader(handle))
    required={'post_code','card_id','original_card_id','entity_id','source_url'}
    if not mapping or not required.issubset(mapping[0]):
        raise ValueError('Mapa de fontes ausente ou sem colunas obrigatórias')
    seen=set()
    for row in mapping:
        code=row.get('post_code','')
        if not code or code in seen:
            raise ValueError(f'post_code ausente/duplicado no mapa: {code}')
        seen.add(code)
    return mapping


def audit(previous: list[dict], canonical: list[dict], source_map: list[dict]) -> dict:
    prev=_indexed(previous,'snapshot anterior')
    next_rows=_indexed(canonical,'catálogo canônico')
    mapped={}
    actions=[]
    counts=Counter()
    for link in source_map:
        code=link['post_code'];old=link['original_card_id'];new=link['card_id']
        if old in mapped:
            raise ValueError('original_card_id repetido no mapa')
        mapped[old]=code
        if new not in next_rows:
            raise ValueError(f'card_id canônico não encontrado: {new}')
        if link.get('entity_id') is None or not link['entity_id']:
            raise ValueError('entity_id ausente no mapa')
        if old==new:
            counts['unchanged_id']+=1
            continue
        if old in next_rows:
            raise ValueError(f'ID de origem reaproveitado por outro card: {old}')
        existing=prev.get(old)
        if existing is None:
            counts['source_not_in_snapshot']+=1
            continue
        if str(existing.get('source_id'))!=code:
            raise ValueError(f'snapshot e source_map divergentes para {old}')
        if existing.get('type')!=next_rows[new].get('type'):
            raise ValueError(f'tipo divergente na reconciliação de {old}')
        if existing.get('status')!='published':
            counts['already_not_published']+=1
            continue
        # A única hipótese automática para uma proposta de remoção é a
        # identidade já consolidada neste mesmo mapa; não interpretar ausências.
        action=dict(original_card_id=old,post_code=code,
            original_source_id=existing['source_id'],original_status='published',
            new_card_id=new,entity_id=link['entity_id'],action='propose_hide_duplicate',
            reason='Fusão de fontes mapeadas para a mesma entidade; revisão obrigatória',
            editorial_decision='pending_review',reviewed_by='',reviewed_at='',
            evidence_url=link['source_url'])
        actions.append(action)
        counts['proposed_hide_duplicate']+=1
    if len({a['original_card_id'] for a in actions})!=len(actions):
        raise ValueError('Ações repetidas')
    # Os itens não referenciados no lote continuam intocados, sem despublicação.
    untouched=[id_ for id_,row in prev.items() if id_ not in next_rows
               and id_ not in mapped and row.get('status')=='published']
    counts['unmapped_published_untouched']=len(untouched)
    report={'previous_count':len(prev),'canonical_count':len(next_rows),
            'source_map_count':len(source_map),'counts':dict(sorted(counts.items())),
            'unmapped_published_ids':sorted(untouched),
            'publish_ready':False,
            'note':'Comparação offline; exige snapshot D1 confiável e aprovação humana. '
                   'Não executar ação com base em amostra parcial.'}
    return {'actions':sorted(actions,key=lambda x:x['original_card_id']), 'report':report}


def main(argv: list[str] | None = None) -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--previous',type=Path,required=True,
                   help='JSONL do snapshot anterior; amostra local não comprova estado do D1')
    p.add_argument('--canonical',type=Path,required=True)
    p.add_argument('--source-map',dest='source_map',type=Path,required=True)
    p.add_argument('--outdir',type=Path,default=Path('etl/output/reconciliation'))
    args=p.parse_args(argv)
    previous=read_jsonl(args.previous)
    canonical=read_jsonl(args.canonical)
    source_map=_mapping(args.source_map)
    result=audit(previous,canonical,source_map)
    csv_write(args.outdir/'reconciliation_review.csv',FIELDS,result['actions'])
    # Snapshot fingerprint = guarda contra comparação de lotes diferentes.
    def file_sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
    json_write(args.outdir/'reconciliation_report.json',{
        **result['report'],
        'inputs_sha256':{
            'previous':file_sha(args.previous),'canonical':file_sha(args.canonical),
            'source_map':file_sha(args.source_map)},
    })
    print(json.dumps(result['report'],indent=2,ensure_ascii=False))
    return 0

if __name__=='__main__':raise SystemExit(main())
