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
