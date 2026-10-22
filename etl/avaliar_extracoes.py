"""Protocolo A3: amostra estratificada e métricas somente contra gabarito identificado."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import date
import json
from pathlib import Path
from common import read_jsonl, write_jsonl
from lotes_incrementais import atomic_json

FIELDS=('content_type','main_entity.name','location.city','location.neighborhood','location.address',
        'event.date_start','event.date_end','event.time_start','event.time_end','commercial_info.price_text',
        'commercial_info.is_free','commercial_info.ticket_required','commercial_info.reservation_required',
        'classification.category','classification.subcategories','classification.tags','quality.evidence',
        'quality.confidence_overall','quality.risk_flags','contradictions_present','hallucination_present',
        'publishable_after_review','overall_correct')


def value_at(row,path):
    value=row
    for part in path.split('.'):
        if not isinstance(value,dict):return None
        value=value.get(part)
    return value


def prepare(rows,target,limit=20):
    if target.exists():raise ValueError('Não sobrescrever referências/avaliações humanas')
    buckets=defaultdict(list)
    for row in rows:
        key=row.get('extraction_id') or 'legacy-editorial:'+str(row.get('post_code'))
        buckets[str(row.get('content_type','unknown'))].append((key,row))
    selected=[]
    for entries in buckets.values():entries.sort(key=lambda x:x[0])
    while buckets and len(selected)<limit:
        for kind in sorted(list(buckets)):
            if len(selected)>=limit:break
            key,row=buckets[kind].pop(0)
            selected.append(dict(reference_id=key,extraction_id=row.get('extraction_id'),post_code=row.get('post_code'),
                                 content_type=row.get('content_type'),source_profile=row.get('source_profile'),
                                 reference_origin='pending_human_annotation',human_review_status='pending',
                                 reviewed_by='',reviewed_at='',evidence_reference='',labels={},
                                 fields_to_label=list(FIELDS),notes='Não inferir gabarito de confiança/status editorial. Rotular só campos verificados; null é valor explícito, chave ausente é sem gabarito.'))
            if not buckets[kind]:del buckets[kind]
    write_jsonl(target,selected);return len(selected)


def score(predictions,references):
    by_id={r.get('extraction_id'):r for r in predictions if r.get('extraction_id')}
    if len(by_id)!=sum(bool(r.get('extraction_id')) for r in predictions):raise ValueError('IDs de predição repetidos')
    groups=defaultdict(lambda:defaultdict(lambda:dict(evaluated=0,correct=0)))
    labeled_refs=0;ignored=0;calibration=[]
    for ref in references:
        if ref.get('human_review_status')!='reviewed':ignored+=1;continue
        if not ref.get('reviewed_by') or not ref.get('evidence_reference'):raise ValueError('Gabarito exige revisor e referência de evidência')
        date.fromisoformat(ref.get('reviewed_at',''))
        row=by_id.get(ref.get('extraction_id'))
        if row is None:raise ValueError('Gabarito não corresponde à versão exata da predição')
        labels=ref.get('labels')
        if not isinstance(labels,dict) or any(k not in FIELDS for k in labels):raise ValueError('Campos de gabarito inválidos')
        labeled_refs+=1
        for field,expected in labels.items():
            actual=value_at(row,field)
            # Julgamentos humanos não são autoavaliados pelo LLM.
            if field in ('contradictions_present','hallucination_present','publishable_after_review','overall_correct'):continue
            if field in ('classification.subcategories','classification.tags','quality.risk_flags'):
                equal=isinstance(actual,list) and isinstance(expected,list) and sorted(actual)==sorted(expected)
            else:equal=actual==expected
            for group in ('all','type:'+str(row.get('content_type')),'source:'+str(row.get('source_profile'))):
                metric=groups[group][field];metric['evaluated']+=1;metric['correct']+=int(equal)
        if isinstance(labels.get('overall_correct'),bool):
            confidence=value_at(row,'quality.confidence_overall')
            if isinstance(confidence,(int,float)):calibration.append((confidence-float(labels['overall_correct']))**2)
    output={}
    for group,fields in groups.items():
        output[group]={field:dict(**metric,accuracy=metric['correct']/metric['evaluated']) for field,metric in fields.items()}
    judgments={field:dict(labeled=sum(field in r.get('labels',{}) and r.get('human_review_status')=='reviewed' for r in references),
                         true_count=sum(r.get('labels',{}).get(field) is True and r.get('human_review_status')=='reviewed' for r in references))
               for field in ('contradictions_present','hallucination_present','publishable_after_review','overall_correct')}
    return dict(predictions=len(predictions),human_references=labeled_refs,pending_or_unreviewed=ignored,
                metrics=output,accuracy=None if not output else 'see per-field denominators',
                brier_overall_correct=sum(calibration)/len(calibration) if calibration else None,human_judgments=judgments,
                automatic=dict(by_type=dict(Counter(r.get('content_type') for r in predictions)),
                               by_extraction_status=dict(Counter(r.get('extraction_status') for r in predictions)),
                               structural_checked=sum(bool(r.get('validation',{}).get('structural_valid')) for r in predictions),
                               literal_evidence_checked=sum(bool(r.get('validation',{}).get('literal_evidence_valid')) for r in predictions)),
                note='Evidência literal não prova vínculo semântico nem atualidade. Sem gabarito não há precisão/recall ou aprovação automática.')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['prepare','score'])
    p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--references',type=Path);p.add_argument('--limit',type=int,default=20)
    args=p.parse_args();rows=list(read_jsonl(args.input))
    if args.command=='prepare':
        if not 1<=args.limit<=1000:raise ValueError('Limite inválido')
        print(prepare(rows,args.output,args.limit))
    else:
        if not args.references:raise ValueError('--references é obrigatório')
        if args.output.exists():raise ValueError('Não sobrescrever relatório anterior')
        atomic_json(args.output,score(rows,list(read_jsonl(args.references))))

if __name__=='__main__':main()
