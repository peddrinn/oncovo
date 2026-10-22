"""Triagem offline e determinística de posts brutos sem OCR/transcrição."""
import argparse
from pathlib import Path
from common import get_dict, read_jsonl, write_jsonl


def triage(source: Path, dest: Path, limit: int = 100):
    by_code = {}
    for row in read_jsonl(source):
        code = str(row.get('code') or '').strip()
        if not code:
            continue
        # O mesmo post pode aparecer em vários perfis; preserva rastreabilidade.
        if code not in by_code:
            by_code[code] = {
                'post_code': code,
                'post_url': f'https://www.instagram.com/p/{code}/',
                'taken_at': row.get('taken_at'),
                'source_profiles': [],
                'media_owner_username': get_dict(row.get('user')).get('username'),
                'location_name': get_dict(row.get('location')).get('name'),
                'caption_text': str(row.get('caption_text') or ''),
            }
        item = by_code[code]
        profiles = row.get('_source_profiles', []) + [row.get('_profile_username')]
        item['source_profiles'] = sorted(set(item['source_profiles'] + [p for p in profiles if p]))
        if len(str(row.get('caption_text') or '')) > len(item['caption_text']):
            item['caption_text'] = row['caption_text']
    rows = list(by_code.values())
    rows = [x for x in rows if len(x['caption_text'].strip()) >= 80]
    rows.sort(key=lambda r: (str(r.get('taken_at') or ''), len(r['caption_text'])), reverse=True)
    write_jsonl(dest, rows[:limit])
    return len(by_code), len(rows), min(len(rows),limit)

if __name__ == '__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--input',type=Path,required=True)
    ap.add_argument('--output',type=Path,default=Path('etl/processed/fila_100.jsonl'))
    ap.add_argument('--limit',type=int,default=100)
    opt=ap.parse_args()
    if not 1<=opt.limit<=10000: ap.error('--limit deve ser de 1 a 10000')
    total,with_caption,saved=triage(opt.input,opt.output,opt.limit)
    print(f'Únicos: {total}; com legenda suficiente: {with_caption}; fila: {saved}')
