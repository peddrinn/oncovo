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
from common import read_jsonl
from lotes_incrementais import ingest, atomic_json, load, locked


def serialize(media):
    if hasattr(media, 'model_dump'):
        return media.model_dump(mode='json')
    if hasattr(media, 'json'):
        return json.loads(media.json())
    if hasattr(media, 'dict'):
        return json.loads(json.dumps(media.dict(), default=str))
    raise TypeError('Objeto não possui serialização segura')



def collect_profiles(client, profiles, output, *, max_per_profile=20, delay_seconds=10,
                     resume=False, authorization=''):
    """Adaptador opcional; testes injetam client falso. Sem retry de bloqueios/login."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with locked(output.parent / '.collector-locks' / output.name):
        path=output.with_suffix(output.suffix+'.acquisition.json')
        config=dict(profiles=profiles,max_per_profile=max_per_profile,authorization=authorization)
        if output.exists():
            if not resume or not path.exists(): raise ValueError('Raw existente: requer --resume e manifesto de aquisição')
            acquisition=load(path)
            if acquisition['config']!=config: raise ValueError('Configuração mudou na retomada')
            existing=list(read_jsonl(output))
            if output.stat().st_size and not output.read_bytes().endswith(b'\n'):
                raise ValueError('Raw interrompido sem newline final; não acrescentar')
            if acquisition['status']=='complete': return acquisition
            count=len(existing)
            mode='a'
        else:
            if resume: raise ValueError('Não há aquisição para retomar')
            count=0;mode='x'
            acquisition=dict(status='partial',started_at=datetime.now(timezone.utc).isoformat(),
                             finished_at=None,profiles={pf:'pending' for pf in profiles},received=0,config=config)
        acquisition.update(status='partial',finished_at=None)
        atomic_json(path,acquisition)
        with output.open(mode,encoding='utf-8') as out:
            for index,profile in enumerate(profiles):
                if acquisition['profiles'][profile]=='complete': continue
                if index: time.sleep(delay_seconds)
                try:
                    profile_id=client.user_id_from_username(profile)
                    medias=client.user_medias(profile_id,max_per_profile)
                    for media in medias:
                        row=serialize(media)
                        row['_profile_username']=profile
                        row['_scraped_at']=datetime.now(timezone.utc).isoformat()
                        out.write(json.dumps(row,ensure_ascii=False,default=str)+'\n')
                        out.flush();os.fsync(out.fileno());count+=1
                    acquisition['profiles'][profile]='complete'
                    acquisition['received']=count
                    atomic_json(path,acquisition)
                except Exception as exc:
                    acquisition.update(status='failed',received=count,finished_at=datetime.now(timezone.utc).isoformat())
                    acquisition['profiles'][profile]='failed'
                    atomic_json(path,acquisition)
                    print(f'Erro no perfil {profile}: {type(exc).__name__}; revisão de autorização necessária.',file=sys.stderr)
                    raise
        acquisition.update(status='complete',finished_at=datetime.now(timezone.utc).isoformat())
        atomic_json(path,acquisition)
        return acquisition


def main():
    p=argparse.ArgumentParser(description='Coleta manual por perfis; padrão é apenas prévia.')
    p.add_argument('--profiles', nargs='+', required=True, help='Perfis públicos que você tem autorização para consultar')
    p.add_argument('--max-per-profile', type=int, default=20)
    p.add_argument('--delay-seconds', type=float, default=10.0)
    p.add_argument('--output', type=Path, default=Path('etl/raw/coleta_instagram.jsonl'))
    p.add_argument('--execute', action='store_true', help='Efetua login e chamadas reais; use com cuidado')
    p.add_argument('--store', type=Path, default=Path('etl/raw/incremental'))
    p.add_argument('--batch-id', help='Referência única para uma aquisição autorizada')
    p.add_argument('--resume', action='store_true')
    p.add_argument('--authorization-reference', help='Referência da autorização de fonte e método')
    args=p.parse_args()
    if not 1<=args.max_per_profile<=100: p.error('--max-per-profile deve estar entre 1 e 100')
    if not 0<=args.delay_seconds<=3600: p.error('Aguardo inválido')
    profiles=list(dict.fromkeys(pf.lstrip('@').strip().lower() for pf in args.profiles))
    if len(profiles)>25 or not all(re.fullmatch(r'[a-z0-9._]{1,30}',pf) for pf in profiles):
        p.error('Até 25 nomes de perfis válidos por execução')
    if not args.execute:
        print(f'PRÉVIA: perfis={profiles} máximo={args.max_per_profile} por perfil; nenhuma chamada executada')
        return
    if not args.authorization_reference: p.error('--execute exige --authorization-reference')
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
    acquisition=collect_profiles(client,profiles,args.output,max_per_profile=args.max_per_profile,
                                 delay_seconds=args.delay_seconds,resume=args.resume,
                                 authorization=args.authorization_reference)
    result=ingest(args.output,args.store,batch_id=args.batch_id,
                  source_name='instagram',method='instagrapi-authorized',
                  authorization=args.authorization_reference,consulted_profiles=profiles)
    if result['status']!='complete': raise RuntimeError('Aquisição inválida; lote não promovido')
    print(f'Observações recebidas: {acquisition["received"]}; lote: {result["batch_id"]}; saída: {args.output}')

if __name__=='__main__':main()
