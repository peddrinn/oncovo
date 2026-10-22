"""A2: resolução conservadora de unidades e ocorrências, *offline* e sem LLM.

Recebe APENAS o catálogo já transformado/revisado; gera *staging*, nunca seed
nem publicação automática. Um post não é uma entidade. Nenhuma similaridade
aproximada provoca fusão. Registro de identidades é proposto, não sobrescrito.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo('America/Sao_Paulo')
VERSION = 1


def norm(value: object) -> str:
    value = unicodedata.normalize('NFKD', str(value or '').casefold())
    value = ''.join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r'[^a-z0-9]+', ' ', value).strip()


def digest(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()[:24]


def source_key(item: dict) -> str:
    code = str(item.get('source_id') or '').strip()
    url = str(item.get('source_url') or '')
    if not re.fullmatch(r'[a-zA-Z0-9_-]{5,30}', code):
        raise ValueError(f'source_id inválido: {code!r}')
    if url != f'https://www.instagram.com/p/{code}/':
        raise ValueError(f'Fonte não rastreável para {code}')
    return f'instagram:{code}'


def location_details(item: dict, extraction: dict | None) -> dict:
    ext = extraction or {}
    loc = ext.get('location') if isinstance(ext.get('location'), dict) else {}
    ent = ext.get('main_entity') if isinstance(ext.get('main_entity'), dict) else {}
    city = norm(item.get('city') or loc.get('city') or '')
    address = norm(item.get('address') or loc.get('address') or '')
    neighborhood = norm(item.get('neighborhood') or loc.get('neighborhood') or '')
    venue = norm(loc.get('venue_name') or '')
    handle = norm(ent.get('instagram_handle') or '')
    name = norm(item.get('title'))
    return dict(name=name,city=city,address=address,neighborhood=neighborhood,venue=venue,handle=handle)


def has_number(address: str) -> bool:
    # CEP isolado não serve como evidência de unidade física.
    # Endereço deve conter logradouro reconhecível E número predial.
    return bool(re.search(r'\b(?:rua|r|avenida|av|praca|pca|alameda|travessa|rodovia)\b', address)
                and re.search(r'\b\d{1,5}\b', address))


def strong_signature(item: dict, details: dict) -> str | None:
    kind = item['type']
    if kind == 'place':
        if details['name'] and details['city'] and has_number(details['address']):
            return '|'.join(('place', details['name'], details['city'], details['address']))
        return None
    if kind == 'event':
        # Evita fundir edições, sessões em dias diferentes ou horários conflitantes.
        start, end = item.get('starts_at'), item.get('ends_at')
        if not (start and end and details['name'] and details['city']):
            return None
        location = (f"addr:{details['address']}" if has_number(details['address']) else
                    f"venue:{details['venue']}:{details['neighborhood']}"
                    if details['venue'] and details['neighborhood'] else '')
        if location:
            return '|'.join(('event', details['name'], details['city'], location, str(start), str(end)))
    return None


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding='utf-8') as handle:
        records = []
        for num,line in enumerate(handle, 1):
            if line.strip():
                try:
                    item = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f'{path}:{num}: JSON inválido') from exc
                if not isinstance(item,dict):
                    raise ValueError(f'{path}:{num}: objeto esperado')
                records.append(item)
        return records


def json_write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)+'\n', encoding='utf-8')


def jsonl_write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n' for r in rows),encoding='utf-8')


def csv_write(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def _config(value: object, name: str) -> dict:
    if not isinstance(value,dict) or value.get('version')!=VERSION:
        raise ValueError(f'{name}: versão/objeto inválido; esperado version=1')
    return value


def _pair(a: str, b: str) -> tuple[str,str]:
    return tuple(sorted((a,b)))


def _iso(value: object) -> datetime | None:
    try:
        if not isinstance(value,str) or not re.match(r'^\d{4}-\d\d-\d\dT',value):return None
        parsed=datetime.fromisoformat(value)
        return parsed if parsed.tzinfo is not None else None
    except ValueError:
        return None


def resolve(items: list[dict], extractions: list[dict] | None = None,
            registry: dict | None = None, overrides: dict | None = None,
            now: datetime | None = None) -> dict:
    """Retorna resultados determinísticos e auditáveis; NÃO grava nem publica."""
    now=now or datetime.now(TZ)
    if now.tzinfo is None:raise ValueError('now deve conter timezone')
    registry=_config(registry or {'version':1,'sources':{},'signatures':{}},'registry')
    overrides=_config(overrides or {'version':1,'approved_groups':[],'rejected_pairs':[]},'overrides')
    prev_sources=registry.get('sources',{})
    prev_signatures=registry.get('signatures',{})
    if not isinstance(prev_sources,dict) or not isinstance(prev_signatures,dict):
        raise ValueError('registry inválido: sources e signatures devem ser objetos')
    extracted={}
    for x in extractions or []:
        k=str(x.get('post_code') or '')
        if k and k in extracted and x != extracted[k]:
            raise ValueError(f'extrações conflitantes para {k}')
        if k:extracted[k]=x
    active={};withheld=Counter();identities={};signatures={}
    all_sources=set()
    for row in items:
        key=source_key(row)
        if key in all_sources:
            raise ValueError(f'Fonte repetida no catálogo de entrada: {key}')
        all_sources.add(key)
        status=row.get('status')
        if status!='published':
            withheld[f'status:{status}']+=1;continue
        if row.get('type') not in ('place','event'):
            withheld[f'type:{row.get("type")}']+=1;continue
        city_check=norm(row.get('city') or '')
        if city_check not in ('belo horizonte','bh'):
            withheld['outside_scope']+=1;continue
        if row['type']=='event':
            start=_iso(row.get('starts_at'));end=_iso(row.get('ends_at'))
            if not start or not end or end<start or end<now:
                withheld['event_expired_or_invalid']+=1;continue
        if not row.get('id') or not row.get('title'):
            withheld['missing_id_or_title']+=1;continue
        active[key]=row
        identities[key]=location_details(row,extracted.get(str(row['source_id'])))
        signatures[key]=strong_signature(row,identities[key])

    # Não reaproveitar um card ID para identidades incompatíveis.
    ids=[str(r['id']) for r in active.values()]
    if len(ids)!=len(set(ids)):
        raise ValueError('IDs de card duplicados na entrada')
    parent={key:key for key in active}
    members={key:{key} for key in active}

    rejected=set()
    for pair in overrides.get('rejected_pairs',[]):
        if not isinstance(pair,dict) or pair.get('type') not in ('place','event'):
            raise ValueError('rejected_pairs exige type')
        sources=pair.get('sources')
        if not isinstance(sources,list) or len(sources)!=2 or sources[0]==sources[1]:
            raise ValueError('rejected_pairs exige duas fontes distintas')
        if not pair.get('reason'):
            raise ValueError('rejected_pairs exige justificativa')
        rejected.add(_pair(*sources))

    def root(x: str) -> str:
        while parent[x]!=x:
            parent[x]=parent[parent[x]]
            x=parent[x]
        return x

    def union(a: str, b: str, *, manual=False) -> bool:
        ra,rb=root(a),root(b)
        if ra==rb:return True
        aa,bb=members[ra],members[rb]
        if active[a]['type']!=active[b]['type']:
            raise ValueError('Tentativa de fusão entre place e event')
        if active[a]['type']=='event':
            occurrences={(active[x].get('starts_at'),active[x].get('ends_at')) for x in aa|bb}
            if len(occurrences)>1:
                raise ValueError('Ocorrências de evento com datas/horários distintos não podem fundir')
        if any(_pair(x,y) in rejected for x in aa for y in bb):
            if manual:raise ValueError('Override de fusão contradiz rejeição explícita')
            return False
        # IDs fixados conflitantes só podem ser reconciliados via migração/revisão da registry.
        pinned={prev_sources[x]['entity_id'] for x in aa|bb if x in prev_sources}
        if len(pinned)>1:
            raise ValueError('Registry possui IDs diferentes para a mesma fusão; reconciliação manual necessária')
        first,second=sorted((ra,rb))
        parent[second]=first
        members[first]|=members.pop(second)
        return True

    manual_pins={}
    for group in overrides.get('approved_groups',[]):
        if not isinstance(group,dict) or group.get('type') not in ('place','event'):
            raise ValueError('approved_groups exige type')
        codes=group.get('sources')
        if (not isinstance(codes,list) or len(set(codes))<2 or not group.get('reason')
            or not group.get('reviewed_by') or not group.get('reviewed_at')):
            raise ValueError('Fusão manual exige fontes, motivo, revisor e data')
        # Um lote parcial pode conter apenas um membro de uma fusão já aprovada.
        # Nesse caso, o override herda a identidade fixada do registro histórico.
        earlier={prev_sources[c]['entity_id'] for c in codes if c in prev_sources}
        earlier_cards={prev_sources[c]['card_id'] for c in codes if c in prev_sources}
        if len(earlier)>1 or len(earlier_cards)>1:
            raise ValueError('Override contém fontes com identidades anteriores conflitantes')
        found=[c for c in codes if c in active]
        if earlier:
            for c in found:manual_pins[c]=(next(iter(earlier)),next(iter(earlier_cards)))
        if any(active[c]['type']!=group['type'] for c in found):
            raise ValueError('Fusão manual com tipo incompatível')
        for code in found[1:]:union(found[0],code,manual=True)

    by_sig=defaultdict(list)
    for key,signature in signatures.items():
        if signature:by_sig[signature].append(key)
    rejected_auto=[]
    for sig, codes in sorted(by_sig.items()):
        for i,a in enumerate(sorted(codes)):
            for b in sorted(codes)[i+1:]:
                if not union(a,b):rejected_auto.append((a,b))

    # A registry também ancora identidade para posts que no passado tinham menos dados.
    by_prev=defaultdict(list)
    for key in active:
        if key in prev_sources:by_prev[prev_sources[key]['entity_id']].append(key)
    for codes in by_prev.values():
        for key in codes[1:]:union(codes[0],key,manual=True)

    ambiguous_signatures={signatures[a] for a,b in rejected_auto if signatures[a]==signatures[b]}
    groups=defaultdict(list)
    for key in active:groups[root(key)].append(key)
    proposed={'version':1,'sources':json.loads(json.dumps(prev_sources)),
              'signatures':json.loads(json.dumps(prev_signatures))}
    canonical=[];source_map=[];merged=[]
    by_entity={}
    for group in sorted(groups.values(),key=lambda codes:min(codes)):
        codes=sorted(group)
        # Uma rejeição explícita torna aquela assinatura insegura: não a use
        # para atribuir a mesma entidade a duas unidades diferentes.
        group_signatures=sorted({signatures[k] for k in codes if signatures[k] and
                                 signatures[k] not in ambiguous_signatures})
        previous_ids={prev_sources[k]['entity_id'] for k in codes if k in prev_sources}
        cards={prev_sources[k]['card_id'] for k in codes if k in prev_sources}
        for k in codes:
            if k in manual_pins:
                previous_ids.add(manual_pins[k][0]);cards.add(manual_pins[k][1])
        for signature in group_signatures:
            old=prev_signatures.get(signature)
            if old:
                previous_ids.add(old['entity_id']);cards.add(old['card_id'])
        if len(previous_ids)>1 or len(cards)>1:
            raise ValueError('Conflito de identidade/canonical card no registro; revisão necessária')
        kind=active[codes[0]]['type']
        entity_id=next(iter(previous_ids)) if previous_ids else (
            ('pl_' if kind=='place' else 'ev_')+digest(group_signatures[0] if group_signatures else codes[0]))
        card_id=next(iter(cards)) if cards else active[codes[0]]['id']
        # Escolhe fonte principal por evidência útil. card_id não depende de sua escolha.
        ranked=sorted(codes,key=lambda k:(-float(active[k].get('rank_score_base') or 0),
                        -bool(active[k].get('address')),-len(active[k].get('description') or ''),k))
        primary=ranked[0]
        card=dict(active[primary]);card['id']=card_id
        canonical.append(card)
        if len(codes)>1:
            merged.append({'entity_id':entity_id,'type':kind,'card_id':card_id,
                           'sources':codes,'primary_source':primary,'matching':'approved_or_exact_evidence'})
        for key in codes:
            old=prev_sources.get(key)
            if old and (old.get('entity_id')!=entity_id or old.get('card_id')!=card_id):
                raise ValueError('Mudança de identidade sem migração explícita')
            proposed['sources'][key]={'entity_id':entity_id,'card_id':card_id,'type':kind}
            source_map.append({'platform':'instagram','post_code':active[key]['source_id'],
                               'entity_id':entity_id,'card_id':card_id,'original_card_id':active[key]['id'],
                               'source_url':active[key]['source_url'],'is_primary':int(key==primary),
                               'matching':'merged' if len(codes)>1 else 'single'})
            by_entity[key]=entity_id
        for signature in group_signatures:
            record={'entity_id':entity_id,'card_id':card_id,'type':kind}
            old=prev_signatures.get(signature)
            if old and old!=record:
                raise ValueError('Assinatura alterou identidade; conflito com registry')
            proposed['signatures'][signature]=record

    # Candidatos são para revisão; distância de nomes NUNCA é evidência de fusão.
    candidate_pairs={}
    blocks=defaultdict(list)
    for key,detail in identities.items():
        kind=active[key]['type']
        if detail['name'] and detail['city']:
            # Mesmo nome na cidade merece triagem, ainda que falte bairro/endereço.
            # Nunca transforma esse bloqueio em fusão automática.
            blocks[(kind,detail['city'],'name:'+detail['name'])].append(key)
            if detail['neighborhood']:
                blocks[(kind,detail['city'],detail['neighborhood'])].append(key)
            if has_number(detail['address']):
                blocks[(kind,detail['city'],'address:'+detail['address'])].append(key)
    for bucket in blocks.values():
        ordered=sorted(set(bucket))
        for i,a in enumerate(ordered):
            for b in ordered[i+1:]:
                if by_entity[a]==by_entity[b]:continue
                na,nb=identities[a]['name'],identities[b]['name']
                similarity=round(SequenceMatcher(None,na,nb).ratio(),3)
                # Endereço completo idêntico (incluindo número/unidade) pode indicar
                # renomeação ou nomes editoriais distintos, mas NUNCA autoriza merge.
                # Também pode ser um centro comercial com lojas diferentes.
                shared_address=(has_number(identities[a]['address']) and
                                identities[a]['address']==identities[b]['address'] and
                                identities[a]['city']==identities[b]['city'])
                if similarity<.84 and not shared_address:continue
                pair=_pair(a,b)
                if pair in candidate_pairs:continue
                basis=('same_full_address' if shared_address else 'similar_name')
                candidate_pairs[pair]={
                    'source_a':a,'source_b':b,'type':active[a]['type'],
                    'name_a':active[a]['title'],'name_b':active[b]['title'],
                    'neighborhood_a':active[a].get('neighborhood',''),
                    'neighborhood_b':active[b].get('neighborhood',''),
                    'address_a':active[a].get('address',''),'address_b':active[b].get('address',''),
                    'name_similarity':similarity,'candidate_basis':basis,
                    'decision':'rejected' if pair in rejected else 'pending_review',
                    'reason':('mesmo endereço informado; verificar unidade, marca e fonte'
                              if shared_address else 'nomes semelhantes; unidade física não comprovada'),
                }
    candidates=[candidate_pairs[key] for key in sorted(candidate_pairs)]
    if len({card['id'] for card in canonical})!=len(canonical):
        raise ValueError('Card ID compartilhado por entidades distintas; requer revisão')
    canonical.sort(key=lambda x:(x['type'],x['id']))
    source_map.sort(key=lambda x:(x['post_code'],x['entity_id']))
    report={
        'resolver_version':VERSION,'input_count':len(items),'eligible_sources':len(active),
        'entity_count':len(canonical),'places':sum(x['type']=='place' for x in canonical),
        'events':sum(x['type']=='event' for x in canonical),
        'sources_collapsed':len(active)-len(canonical),'merge_groups':len(merged),
        'merge_candidates':len(candidates),'rejected_auto_pairs':len(rejected_auto),
        'withheld':dict(sorted(withheld.items())),
        'ids_changed':sum(x['original_card_id']!=x['card_id'] for x in source_map),
        'registry_must_be_reviewed':True,
        'publication_requires_manual_review':True,
        'note':'Catálogo de staging; fontes históricas não provam operação atual',
    }
    return {'catalog':canonical,'source_map':source_map,'candidates':candidates,
            'merges':merged,'registry':proposed,'report':report}


def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,default=Path('etl/output/search_items.jsonl'))
    parser.add_argument('--extractions',type=Path,help='Opcional: somente leitura, dados de localização do LLM')
    parser.add_argument('--registry',type=Path,default=Path('etl/entity_registry.json'))
    parser.add_argument('--overrides',type=Path,default=Path('etl/entity_overrides.json'))
    parser.add_argument('--outdir',type=Path,default=Path('etl/output/entities'))
    args=parser.parse_args(argv)
    def config(path: Path, base: dict) -> dict:
        return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else base
    result=resolve(read_jsonl(args.input),read_jsonl(args.extractions) if args.extractions else None,
                   config(args.registry,{'version':1,'sources':{},'signatures':{}}),
                   config(args.overrides,{'version':1,'approved_groups':[],'rejected_pairs':[]}))
    out=args.outdir
    jsonl_write(out/'search_items_canonical.jsonl',result['catalog'])
    csv_write(out/'source_entity_map.csv',
              ['platform','post_code','entity_id','card_id','original_card_id','source_url','is_primary','matching'],
              result['source_map'])
    csv_write(out/'merge_candidates.csv',
              ['source_a','source_b','type','name_a','name_b','neighborhood_a','neighborhood_b',
               'address_a','address_b','name_similarity','candidate_basis','decision','reason'],result['candidates'])
    json_write(out/'entity_registry.proposed.json',result['registry'])
    json_write(out/'entity_report.json',{**result['report'],'merges':result['merges']})
    print(json.dumps(result['report'],ensure_ascii=False,indent=2))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
