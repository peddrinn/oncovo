"""Une aprovação editorial + extração validada e aplica contratos do runtime.

Nunca promove 'review' para 'published'. Não infere ano ou datas relativas.
"""
import argparse
import csv
import json
from pathlib import Path
from common import (NOW,canonical_id,event_dates,get_dict,list_strings,read_jsonl,
                    safe_source_url,search_index,write_jsonl)

BLOCKED_RISKS={
    'multiple_events_in_post','free_and_ticket_required_conflict','location_conflict',
    'relative_date_ambiguous','recurring_event_no_single_date',
}

def transform(item:dict, ext:dict|None, now=None)->tuple[dict|None,str,str]:
    code=str(item.get('post_code') or '').strip()
    if not safe_source_url(code):return None,'review','post_code inválido'
    if ext is None:return None,'review','extração ausente'
    kind=str(ext.get('content_type') or item.get('content_type') or '')
    if kind not in ('place','event','promotion'):return None,'review','tipo inválido'
    main=get_dict(ext.get('main_entity'))
    ev=get_dict(ext.get('event'))
    loc=get_dict(ext.get('location'))
    info=get_dict(ext.get('commercial_info'))
    cls=get_dict(ext.get('classification'))
    qual=get_dict(ext.get('quality'))
    tags=list_strings(cls.get('tags'))
    subcategories=list_strings(cls.get('subcategories'))
    category=str(cls.get('category') or '')[:90]
    title=str(item.get('display_title') or (ev.get('name') if kind=='event' else main.get('name')) or '').strip()[:140]
    subtitle=str(item.get('display_subtitle') or category).strip()[:120]
    neighborhood=str(loc.get('neighborhood') or '').strip()[:90]
    city=str(loc.get('city') or 'Belo Horizonte').strip()[:90]
    address=str(loc.get('address') or '').strip()[:230]
    venue=str(loc.get('venue_name') or main.get('name') or '').strip()[:120]
    try:
        confidence=float(qual.get('confidence_overall') or 0)
        if not 0 <= confidence <= 1: confidence=0.0
    except (ValueError,TypeError):
        confidence=0.0
    risks=set(list_strings(qual.get('risk_flags')))
    manual=str(item.get('publish_status') or 'review')
    status=manual if manual in ('published','review','expired','hidden') else 'review'
    reason='aprovado editorialmente' if status=='published' else f'estado editorial: {status}'
    if ext.get('extraction_status') != 'ok':status,reason='hidden','extração descartada'
    elif item.get('content_type') and item.get('content_type') != kind and status=='published':
        status,reason='review','divergência de tipo entre editorial e extração'
    elif kind=='promotion':status,reason='hidden','promoção excluída do MVP'
    elif confidence < .75 and status=='published':status,reason='review','confiança inferior a 0.75'
    elif not title and status=='published':status,reason='review','título ausente'
    elif kind=='event' and not category and status=='published':
        status,reason='review','categoria de evento ausente'
    elif city.casefold() not in ('belo horizonte','bh') and status=='published':
        status,reason='review','fora de Belo Horizonte; revisar escopo'
    elif not (neighborhood or address or venue) and status=='published':
        status,reason='review','localização insuficiente'
    elif risks & BLOCKED_RISKS and status=='published':
        status,reason='review','risco crítico: '+','.join(sorted(risks & BLOCKED_RISKS))

    starts_at,ends_at=(None,None)
    is_recurring=bool('recurring_event_no_single_date' in risks)
    if kind=='event':
        starts_at,ends_at=event_dates(ev)
        if not starts_at:
            if status=='published':status,reason='review','data ISO não comprovada'
        else:
            # Vale até a hora de término do evento; eventos antigos não reaparecem.
            reference=now or NOW()
            from datetime import datetime
            if datetime.fromisoformat(ends_at) < reference:
                status,reason='expired','evento finalizado'
    else:
        # Nunca expor abertura de estabelecimento como data de evento.
        starts_at,ends_at=None,None

    if status!='published':
        return None,status,reason
    is_free = info.get('is_free') is True
    price_type='free' if is_free else 'paid' if info.get('ticket_required') is True else 'unknown'
    price_text=str(info.get('price_text') or '').strip()[:100]
    price_label = 'Gratuito' if is_free else price_text or ('Ingresso necessário' if price_type=='paid' else '')
    desc_parts = [category.title() if category else '',
                  ', '.join(subcategories[:3]),
                  f'Em {neighborhood}' if neighborhood else '',
                  f'Local: {venue}' if kind=='event' and venue else '']
    description='. '.join(v.strip(' .') for v in desc_parts if v.strip(' .'))[:280]
    source=str(item.get('source_profile') or ext.get('source_profile') or 'Instagram').strip()[:70]
    normalized=search_index(title,subtitle,description,neighborhood,address,venue,
                            category,subcategories,tags,item.get('search_text'))
    return {
        'id':canonical_id('instagram',code),
        'source_id':code,'source_url':safe_source_url(code),
        'type':kind,'status':'published','title':title,'subtitle':subtitle,
        'description':description,'city':city,'neighborhood':neighborhood,'address':address,
        'starts_at':starts_at,'ends_at':ends_at,'is_recurring':int(is_recurring),
        'recurrence_text':None,
        'price_label':price_label,'price_type':price_type,
        'categories':json.dumps([category]+subcategories if category else subcategories,ensure_ascii=False),
        'tags':json.dumps(tags,ensure_ascii=False),
        'search_text':normalized,
        'rank_score_base':round(confidence*100+(4 if address else 0)+(2 if price_label else 0),2),
        'source_label':source if source!='Instagram' else 'Instagram',
    },'published',reason

def build(approved:Path,extractions:Path,output:Path,report:Path,now=None,raw:Path|None=None)->dict:
    extracted={}
    for x in read_jsonl(extractions):
        code=str(x.get('post_code') or '')
        if code:extracted[code]=x
    owners={}
    if raw is not None:
        for post in read_jsonl(raw):
            code=str(post.get('code') or '')
            if code and code not in owners:
                owners[code]=str(get_dict(post.get('user')).get('username') or post.get('_profile_username') or '').strip()
    rows=[];audit=[];seen=set();stats={}
    for row in read_jsonl(approved):
        code=str(row.get('post_code') or '')
        if code in seen:
            audit.append({'post_code':code,'status':'review','reason':'duplicado no editorial'})
            continue
        seen.add(code)
        enriched=dict(row)
        if code in owners and not enriched.get('source_profile'):
            enriched['source_profile']='@'+owners[code].lstrip('@')
        item,status,reason=transform(enriched,extracted.get(code),now)
        stats[status]=stats.get(status,0)+1
        audit.append({'post_code':code,'status':status,'reason':reason})
        if item:rows.append(item)
    write_jsonl(output,rows)
    report.parent.mkdir(parents=True,exist_ok=True)
    with report.open('w',encoding='utf-8',newline='') as out:
        w=csv.DictWriter(out,fieldnames=['post_code','status','reason'])
        w.writeheader();w.writerows(audit)
    print('Resumo de qualidade:',json.dumps(stats,ensure_ascii=False))
    print(f'Gerados {len(rows)} itens, {len(audit)} itens auditados; saídas: {output}, {report}')
    return stats

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--approved',type=Path,default=Path('etl/items_publicaveis.jsonl'))
    p.add_argument('--extractions',type=Path,required=True)
    p.add_argument('--raw',type=Path,default=None,help='Opcional: posts brutos para identificar a conta autora da publicação')
    p.add_argument('--output',type=Path,default=Path('etl/output/search_items.jsonl'))
    p.add_argument('--report',type=Path,default=Path('etl/output/revisao.csv'))
    args=p.parse_args()
    build(args.approved,args.extractions,args.output,args.report,raw=args.raw)
