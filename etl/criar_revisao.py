"""Fila A4 versionada. Nenhuma aprovação automática; decisões anteriores não sobrescritas."""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path
from common import get_dict, read_jsonl, safe_source_url, write_jsonl


def make_review(source:Path, target:Path)->int:
    from extracao_versionada import result_digest
    if target.exists() or target.with_suffix('.csv').exists():raise ValueError('Fila já existe; preservar decisões e usar saída nova')
    rows=[];seen=set()
    for ext in read_jsonl(source):
        code=str(ext.get('post_code') or '').strip()
        identity=ext.get('extraction_id') or 'legacy:'+code
        if not safe_source_url(code) or identity in seen:continue
        if ext.get('extraction_id') and ext['extraction_id']!=result_digest(ext):raise ValueError('Hash de extração inválido')
        seen.add(identity)
        kind=str(ext.get('content_type') or '')
        entity=get_dict(ext.get('main_entity'));ev=get_dict(ext.get('event'))
        place=get_dict(ext.get('location'));cat=get_dict(ext.get('classification'));quality=get_dict(ext.get('quality'))
        title=str((ev.get('name') if kind=='event' else place.get('venue_name')) or entity.get('name') or '').strip()
        flags=quality.get('risk_flags') or []
        rows.append(dict(post_code=code,post_url=safe_source_url(code),content_type=kind,publish_status='review',
                         extraction_id=ext.get('extraction_id'),request_id=ext.get('request_id'),
                         extraction_version=ext.get('contract_version','legacy_unverified'),evidence_digest=ext.get('extraction_id'),
                         batch_id=ext.get('batch_id'),display_title=title[:140],display_subtitle=str(cat.get('category') or '')[:120],
                         source_profile=ext.get('source_profile') or 'Instagram',neighborhood=place.get('neighborhood'),
                         address=place.get('address'),event_date=ev.get('date_start'),
                         missing_critical_fields=quality.get('missing_critical_fields') or [],risk_flags=flags,
                         evidence=quality.get('evidence') or [],currentness_recheck_required=True,
                         reviewed_by='',reviewed_at='',approval_reason='',
                         review_notes='Conferir versão, evidências, unidade física, datas e atualidade; não aprovar por confiança/fusão'))
    write_jsonl(target,rows)
    with target.with_suffix('.csv').open('w',encoding='utf-8',newline='') as handle:
        fields=list(rows[0]) if rows else ['post_code','extraction_id','publish_status','reviewed_by','reviewed_at','approval_reason']
        writer=csv.DictWriter(handle,fieldnames=fields);writer.writeheader()
        for row in rows:writer.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v for k,v in row.items()})
    return len(rows)


def import_decisions(template:Path, decisions:Path, target:Path)->int:
    """CSV editável só nos campos editoriais; preserva identidade/evidência da fila."""
    from datetime import date
    if target.exists():raise ValueError('Não sobrescrever decisões anteriores')
    rows=list(read_jsonl(template))
    key=lambda row:row.get('extraction_id') or 'legacy:'+row['post_code']
    indexed={key(row):row for row in rows}
    if len(indexed)!=len(rows):raise ValueError('Template com IDs repetidos')
    editable={'publish_status','reviewed_by','reviewed_at','approval_reason','currentness_recheck_required','display_title','display_subtitle','review_notes'}
    with decisions.open(encoding='utf-8',newline='') as handle:csv_rows=list(csv.DictReader(handle))
    results=[];seen=set()
    for decision in csv_rows:
        pk=key(decision)
        if pk not in indexed or pk in seen:raise ValueError('CSV com versão desconhecida/repetida')
        seen.add(pk);original=indexed[pk];result=dict(original)
        for field,value in original.items():
            if field in editable:continue
            expected=json.dumps(value,ensure_ascii=False) if isinstance(value,(list,dict)) else '' if value is None else str(value)
            if decision.get(field)!=expected:raise ValueError('CSV alterou evidência congelada: '+field)
        for field in editable:
            if field not in decision:raise ValueError('Coluna editorial ausente: '+field)
            if field=='currentness_recheck_required':
                value=decision[field].strip().lower()
                if value not in ('true','false'):raise ValueError('Rechecagem deve ser true/false')
                result[field]=value=='true'
            else:result[field]=decision[field]
        if result['publish_status'] not in ('published','review','expired','hidden'):raise ValueError('Estado editorial inválido')
        if result['publish_status']=='published':
            reviewed=result['reviewed_at']
            if len(reviewed)!=10 or date.fromisoformat(reviewed).isoformat()!=reviewed:raise ValueError('Data de revisão inválida')
            if not result['reviewed_by'].strip() or len(result['approval_reason'].strip())<12 or result['currentness_recheck_required']:
                raise ValueError('Aprovação requer revisor, motivo e rechecagem concluída')
        results.append(result)
    if seen!=set(indexed):raise ValueError('CSV incompleto; preservar todas as decisões')
    write_jsonl(target,results);return len(results)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',required=True,type=Path)
    p.add_argument('--output',type=Path,default=Path('etl/processed/para_revisao.jsonl'))
    p.add_argument('--decisions-csv',type=Path)
    a=p.parse_args()
    count=import_decisions(a.input,a.decisions_csv,a.output) if a.decisions_csv else make_review(a.input,a.output)
    print(f'{count} itens na fila {a.output}; nenhuma aprovação automática')
