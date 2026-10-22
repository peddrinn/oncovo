"""Gera fila editorial a partir de extrações. NUNCA marca published automaticamente."""
from __future__ import annotations
import argparse
from pathlib import Path
from common import get_dict, read_jsonl, safe_source_url, write_jsonl


def make_review(source:Path, target:Path)->int:
    rows=[];seen=set()
    for ext in read_jsonl(source):
        code=str(ext.get('post_code') or '').strip()
        if not safe_source_url(code) or code in seen:continue
        seen.add(code)
        kind=str(ext.get('content_type') or '')
        entity=get_dict(ext.get('main_entity'))
        ev=get_dict(ext.get('event'))
        place=get_dict(ext.get('location'))
        cat=get_dict(ext.get('classification'))
        title=str((ev.get('name') if kind=='event' else place.get('venue_name')) or entity.get('name') or '').strip()
        flags=get_dict(ext.get('quality')).get('risk_flags') or []
        rows.append({
          'post_code':code,'post_url':safe_source_url(code),'content_type':kind,
          'publish_status':'review',
          'display_title':title[:140],
          'display_subtitle':str(cat.get('category') or '')[:120],
          'source_profile':ext.get('source_profile') or 'Instagram',
          'review_notes':'Conferir evidências, endereço, categoria, horários, status real do lugar/evento, e riscos: '+', '.join(map(str,flags)),
        })
    write_jsonl(target,rows)
    return len(rows)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--input',required=True,type=Path)
    p.add_argument('--output',type=Path,default=Path('etl/processed/para_revisao.jsonl'))
    a=p.parse_args()
    print(f'{make_review(a.input,a.output)} itens aguardando revisão manual em {a.output}')
