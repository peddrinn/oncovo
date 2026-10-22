"""Validação pós-LLM preserva as verificações do teste histórico da Maritaca."""
from __future__ import annotations

def validate(data: dict)->dict:
    if not isinstance(data,dict):raise ValueError('O LLM não retornou objeto')
    allowed={'event','place','promotion','tourism','ambiguous','irrelevant'}
    statuses={'ok','partial','discard','error'}
    if data.get('content_type') not in allowed or data.get('extraction_status') not in statuses:
        raise ValueError('content_type ou extraction_status fora do contrato')
    required=['main_entity','event','location','commercial_info','classification','quality']
    if not all(isinstance(data.get(k),dict) for k in required):
        raise ValueError('Objeto do schema de extração está ausente')
    quality=data['quality']; commercial=data['commercial_info']
    flags=quality.get('risk_flags')
    if not isinstance(flags,list):flags=[]
    flags=[str(f) for f in flags if isinstance(f,str)]
    if commercial.get('is_free') is True and commercial.get('ticket_required') is True:
        for f in ('free_and_ticket_required_conflict','commercial_info_unclear'):
            if f not in flags:flags.append(f)
        conf=quality.get('confidence_overall')
        quality['confidence_overall']=min(float(conf) if isinstance(conf,(int,float)) else 0.74,0.74)
        if data['extraction_status']=='ok':data['extraction_status']='partial'
    if data['content_type'] in ('tourism','ambiguous','irrelevant') and data['extraction_status']=='ok':
        data['extraction_status']='partial' if data['content_type']!='irrelevant' else 'discard'
    quality['risk_flags']=flags
    return data


def validate_versioned(data: dict, messages: list[dict]) -> tuple[dict, dict]:
    """Contrato A3 estrito. Evidência literal é verificável; verdade semântica exige humano."""
    import copy
    from datetime import date, time
    import json
    import math
    result=copy.deepcopy(data)
    validate(result)
    schema={
        'main_entity':('name','entity_type','instagram_handle'),
        'event':('name','date_text','date_start','date_end','time_text','time_start','time_end','date_confidence'),
        'location':('venue_name','neighborhood','address','city','opening_hours_text','opening_time_start','opening_time_end','location_confidence'),
        'commercial_info':('price_text','is_free','reservation_required','ticket_required'),
        'classification':('category','subcategories','tags'),
        'quality':('confidence_overall','missing_critical_fields','risk_flags','evidence'),
    }
    for group,fields in schema.items():
        if not all(k in data[group] for k in fields):raise ValueError('Campos ausentes no schema: '+group)
    for group,fields in schema.items():
        for field in fields:
            value=data[group][field]
            if group=='quality' or field in ('subcategories','tags'):continue
            if field in ('is_free','reservation_required','ticket_required'):
                if value is not None and not isinstance(value,bool):raise ValueError('Booleano inválido: '+field)
            elif value is not None and not isinstance(value,str):raise ValueError('Texto inválido: '+field)
    confidence=data['quality']['confidence_overall']
    if isinstance(confidence,bool) or not isinstance(confidence,(float,int)) or not math.isfinite(confidence) or not 0<=confidence<=1:
        raise ValueError('Confiança deve estar entre 0 e 1')
    for group,field in [('quality','risk_flags'),('quality','missing_critical_fields'),('classification','tags'),('classification','subcategories')]:
        value=data[group][field]
        if not isinstance(value,list) or not all(isinstance(x,str) for x in value):raise ValueError('Lista inválida: '+field)
    if data['main_entity']['entity_type'] not in ('venue','event','attraction','organizer','unknown'):raise ValueError('entity_type inválido')
    for group,field in [('event','date_confidence'),('location','location_confidence')]:
        if data[group][field] not in ('high','medium','low','none'):raise ValueError('Confiança categórica inválida')
    if data['classification']['category'] not in ('gastronomia','musica','cultura','festa','esporte','familia','turismo','bar','restaurante','cafe','outro'):
        raise ValueError('Categoria inválida')
    for field in ('date_start','date_end'):
        if data['event'][field] is not None:
            try:
                value=data['event'][field]
                if len(value)!=10 or date.fromisoformat(value).isoformat()!=value:raise ValueError()
            except ValueError as exc:raise ValueError('Data inválida: '+field) from exc
    for group,fields in [('event',('time_start','time_end')),('location',('opening_time_start','opening_time_end'))]:
        for field in fields:
            if data[group][field] is not None:
                value=data[group][field]
                if len(value)!=5:raise ValueError('Horário inválido')
                time.fromisoformat(value)
    # Só o Post renderizado, nunca o schema/exemplos do system prompt, pode provar uma citação.
    try: actual=json.loads(messages[1]['content'].rsplit('Post:\n',1)[1])
    except (IndexError,ValueError,KeyError) as exc:raise ValueError('Mensagens sem Post JSON rastreável') from exc
    caption=actual.get('caption_text_clean') or ''
    evidence=data['quality']['evidence']
    if not isinstance(evidence,list):raise ValueError('evidence deve ser lista')
    covered=set();issues=[]
    for ev in evidence:
        if not isinstance(ev,dict) or not isinstance(ev.get('field'),str) or not isinstance(ev.get('quote'),str):
            raise ValueError('Evidência inválida')
        quote=ev['quote'];verified=bool(quote) and quote in caption
        if quote.startswith('metadata.') and ': ' in quote:
            key,value=quote[len('metadata.'):].split(': ',1)
            actual_value=actual.get(key)
            verified=actual_value is not None and value== (actual_value if isinstance(actual_value,str) else json.dumps(actual_value,ensure_ascii=False))
        if not verified:issues.append('unsupported_evidence:'+ev['field'])
        else:covered.add(ev['field'])
    required=['classification.category']
    for field in ('main_entity.name','location.venue_name','location.neighborhood','location.address','location.city',
                  'commercial_info.price_text','commercial_info.is_free','commercial_info.reservation_required','commercial_info.ticket_required',
                  'event.date_start','event.date_text','event.time_text'):
        group,key=field.split('.')
        if data[group].get(key) is not None:required.append(field)
    issues += ['missing_evidence:'+field for field in required if field not in covered]
    import re
    import unicodedata
    def normalized(value):
        text=unicodedata.normalize('NFKD',str(value or '').casefold())
        return re.sub(r'[^a-z0-9]+',' ',''.join(c for c in text if not unicodedata.combining(c))).strip()
    available=normalized(' '.join(str(actual.get(k) or '') for k in ('caption_text_clean','location_name','location_address')))
    for field in ('main_entity.name','location.venue_name','location.neighborhood','location.address','commercial_info.price_text'):
        group,key=field.split('.');value=data[group][key]
        if value and normalized(value) not in available:issues.append('unsupported_value:'+field)
    city=normalized(data['location']['city'])
    if city and city not in available and not (city in ('bh','belo horizonte') and re.search(r'\bbh\b|belo horizonte',available)):
        issues.append('unsupported_value:location.city')
    # Heurísticas conservadoras de suporte para booleanos; não substituem interpretação humana.
    cues={
        ('ticket_required',False):r'sem (?:ingresso|ticket|retirada)|nao (?:precisa|necessita).*?(?:ingresso|ticket)',
        ('ticket_required',True):r'ingresso|ticket|bilheteria|sympla|venda de entradas|lote',
        ('reservation_required',False):r'sem reserva|nao (?:precisa|necessita).*?reserv',
        ('reservation_required',True):r'reserva obrigatoria|somente com reserva|mediante reserva',
        ('is_free',True):r'gratuit|gratis|0800|entrada livre|nao paga',
        ('is_free',False):r'preco|pago|cobranca|r \d|reais|ingresso.*?\d',
    }
    for (field,boolean),pattern in cues.items():
        if data['commercial_info'][field] is boolean:
            quotes=' '.join(normalized(e['quote']) for e in evidence if e['field']=='commercial_info.'+field)
            if not re.search(pattern,quotes):issues.append('unsupported_boolean:'+field)
    if data['content_type']=='place' and not data['main_entity']['name']:issues.append('missing_place_name')
    if data['content_type']=='event':
        if not data['event']['date_start']:issues.append('event_without_date')
        if data['event']['date_end'] and data['event']['date_start'] and data['event']['date_end']<data['event']['date_start']:issues.append('inverted_event_dates')
        if not data['event']['date_start'] and data['event']['date_text']:issues.append('recurring_or_ambiguous_date')
    if data['content_type'] in ('event','place') and not data['location']['city']:issues.append('missing_city')
    if data['quality']['missing_critical_fields']:issues.append('declared_missing_critical_fields')
    flags=result['quality']['risk_flags']
    for issue in issues:
        if issue not in flags:flags.append(issue)
    if issues and result['extraction_status']=='ok':result['extraction_status']='partial'
    if result['extraction_status']=='partial':result['quality']['confidence_overall']=min(result['quality']['confidence_overall'],.74)
    return result,dict(structural_valid=True,literal_evidence_valid=not any('evidence:' in x for x in issues),
                       issues=issues,semantic_human_review_required=True)
