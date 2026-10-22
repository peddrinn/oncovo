"""Coleta manual LEGADA via instagrapi. Não contorna bloqueios/autenticação; sem execução por padrão.

Use somente com autorização e em conformidade com os termos da plataforma e a legislação
aplicável. A API oficial é preferível quando adequada ao caso de uso.
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def serialize(media):
    if hasattr(media, 'model_dump'):
        return media.model_dump(mode='json')
    if hasattr(media, 'json'):
        return json.loads(media.json())
    if hasattr(media, 'dict'):
        return json.loads(json.dumps(media.dict(), default=str))
    raise TypeError('Objeto não possui serialização segura')


def main():
    p=argparse.ArgumentParser(description='Coleta manual por perfis; padrão é apenas prévia.')
    p.add_argument('--profiles', nargs='+', required=True, help='Perfis públicos que você tem autorização para consultar')
    p.add_argument('--max-per-profile', type=int, default=20)
    p.add_argument('--delay-seconds', type=float, default=10.0)
    p.add_argument('--output', type=Path, default=Path('etl/raw/coleta_instagram.jsonl'))
    p.add_argument('--execute', action='store_true', help='Efetua login e chamadas reais; use com cuidado')
    args=p.parse_args()
    if not 1<=args.max_per_profile<=100: p.error('--max-per-profile deve estar entre 1 e 100')
    if not 0<=args.delay_seconds<=3600: p.error('Aguardo inválido')
    profiles=list(dict.fromkeys(pf.lstrip('@').strip().lower() for pf in args.profiles))
    if len(profiles)>25 or not all(re.fullmatch(r'[a-z0-9._]{1,30}',pf) for pf in profiles):
        p.error('Até 25 nomes de perfis válidos por execução')
    if not args.execute:
        print(f'PRÉVIA: perfis={profiles} máximo={args.max_per_profile} por perfil; nenhuma chamada executada')
        return
    user=os.environ.get('INSTAGRAM_USERNAME')
    password=os.environ.get('INSTAGRAM_PASSWORD')
    if not user or not password: p.error('Defina INSTAGRAM_USERNAME e INSTAGRAM_PASSWORD fora do código')
    try:
        from instagrapi import Client
    except ImportError as exc:
        raise SystemExit('Instale o grupo opcional instagrapi (imagem Docker collector).') from exc
    client=Client()
    try:
        code=os.environ.get('INSTAGRAM_VERIFICATION_CODE') or None
        if code: client.login(user,password,verification_code=code)
        else: client.login(user,password)
    except Exception as exc:
        raise RuntimeError('Falha de autenticação. Verifique autorização/login manualmente; sem tentativas de contorno.') from exc
    args.output.parent.mkdir(parents=True, exist_ok=True)
    existing=set()
    if args.output.exists():
        for line in args.output.read_text(encoding='utf-8').splitlines():
            if line.strip():
                try:
                    post=json.loads(line)
                    existing.add((str(post.get('code')),str(post.get('_profile_username'))))
                except json.JSONDecodeError:
                    raise RuntimeError('Arquivo anterior contém JSON inválido; não acrescentar registros')
    count=0
    with args.output.open('a',encoding='utf-8') as out:
        for index,profile in enumerate(profiles):
            if index: time.sleep(args.delay_seconds)
            try:
                profile_id=client.user_id_from_username(profile)
                medias=client.user_medias(profile_id,args.max_per_profile)
                for media in medias:
                    row=serialize(media)
                    key=(str(row.get('code')),profile)
                    if not row.get('code') or key in existing: continue
                    row['_profile_username']=profile
                    row['_scraped_at']=datetime.now(timezone.utc).isoformat()
                    out.write(json.dumps(row,ensure_ascii=False,default=str)+'\n')
                    out.flush()
                    existing.add(key);count+=1
                print(f'Perfil {index+1}/{len(profiles)}: {profile}; {len(medias)} posts retornados')
            except Exception as exc:
                print(f'Erro de coleta no perfil {profile}: {type(exc).__name__}. Interrompa e revise a autorização.',file=sys.stderr)
                raise
    print(f'Novos registros coletados: {count}; saída local: {args.output}')

if __name__=='__main__':main()
