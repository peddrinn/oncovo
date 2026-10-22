"""Somente fixtures sintéticas para homologação A3/A4; não são respostas Maritaca."""
import json
from extracao_versionada import plan,request_for
from lotes_incrementais import ingest
from common import write_jsonl


def fixture(code='A3TEST0001',kind='place',name='Café Sintético',address='Rua Teste, 1',date='2030-10-25'):
    caption=f'{name}: cafe em BH, Centro, {address}. Funcionamento e reservas. '
    if kind=='event':caption+=f'Evento em {date}, show das 20h às 23h. '
    if kind=='promotion':caption+='Promoção de café, oferta especial. '
    if kind=='ambiguous':caption+='Programação incerta, conferir detalhes. '
    caption+='Conteúdo fictício exclusivamente para teste local.'
    row=dict(platform='instagram',post_code=code,caption_text_clean=caption,taken_at='2026-10-22T10:00:00-03:00',
             source_profile='synthetic_profile',media_owner_username='synthetic_owner',triage_class='candidato_lugar',triage_score=90)
    payload=dict(extraction_status='ok',content_type=kind,
        main_entity=dict(name=name,entity_type='venue',instagram_handle=None),
        event=dict(name=name if kind=='event' else None,date_text=date if kind=='event' else None,
                   date_start=date if kind=='event' else None,date_end=date if kind=='event' else None,
                   time_text='show das 20h às 23h' if kind=='event' else None,time_start='20:00' if kind=='event' else None,
                   time_end='23:00' if kind=='event' else None,date_confidence='high' if kind=='event' else 'none'),
        location=dict(venue_name=name,neighborhood='Centro',address=address,city='BH',opening_hours_text=None,
                      opening_time_start=None,opening_time_end=None,location_confidence='high'),
        commercial_info=dict(price_text=None,is_free=None,reservation_required=None,ticket_required=None),
        classification=dict(category='musica' if kind=='event' else 'cafe',subcategories=[],tags=[]),
        quality=dict(confidence_overall=.95,missing_critical_fields=[],risk_flags=[],evidence=[]))
    fields=['main_entity.name','location.venue_name','location.neighborhood','location.address','location.city','classification.category']
    if kind=='event':fields+=['event.date_start','event.date_text','event.time_text']
    payload['quality']['evidence']=[dict(field=f,quote=caption) for f in fields]
    return row,payload


def batch_for(rows,folder,store):
    raw=[]
    for row in rows:
        raw.append(dict(code=row['post_code'],caption_text=row['caption_text_clean'],taken_at=row['taken_at'],
                        _profile_username=row['source_profile'],user=dict(username=row['media_owner_username'])))
    source=folder/'input.jsonl';write_jsonl(source,raw);manifest=ingest(source,store)
    return store/'batches'/manifest['batch_id']


def fixture_plan(rows,store,batch,**kwargs):
    pricing=dict(input_per_million='1',output_per_million='2',currency='TEST',reference='SYNTHETIC_SCENARIO_ONLY')
    base=plan(rows,store,batch=batch,provider='synthetic-fixture',model='fixture-model',pricing=pricing,**kwargs)
    bounds={r['request_id']:dict(max_input_tokens=30000,verified=True,reference='SYNTHETIC_TOKEN_BOUND_ONLY') for r in base['requests']}
    return plan(rows,store,batch=batch,provider='synthetic-fixture',model='fixture-model',pricing=pricing,bounds=bounds,**kwargs)


def response(payload,finish='stop'):
    return dict(content=json.dumps(payload,ensure_ascii=False),finish_reason=finish,usage=dict(prompt_tokens=100,completion_tokens=50))
