"""A0: pré-verificação estrita de JSONL e chaves; nunca repara dados automaticamente.

Sem API, sem scraping, sem leitura de segredos; relatório agregado, sem legendas.
Exit code 2 para JSONL inválido, 3 para chave ausente ou duplicata pós-triagem.
Duplicatas no raw são apenas relatadas, pois a triagem existente já as elimina.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

KEYS={'raw':'code','triage':'post_code','extraction':'post_code','editorial':'post_code','catalog':'source_id'}


def audit(path: Path, kind: str) -> dict:
    if kind not in KEYS:raise ValueError(f'Tipo inválido: {kind}')
    digest=hashlib.sha256()
    errors=Counter();rows=0;valid=0;dupes=0;missing=0
    seen=set();bad_lines=[]
    with path.open('rb') as stream:
        for idx,raw in enumerate(stream,1):
            rows+=1;digest.update(raw)
            try:
                obj=json.loads(raw.decode('utf-8'))
                if not isinstance(obj,dict):raise ValueError('Registro não é objeto JSON')
            except (ValueError,UnicodeDecodeError) as err:
                errors[getattr(err,'msg',type(err).__name__)]+=1
                if len(bad_lines)<12:bad_lines.append(idx)
                continue
            valid+=1
            code=obj.get(KEYS[kind])
            if code is None or not str(code).strip():
                missing+=1
            elif str(code) in seen:
                dupes+=1
            else:seen.add(str(code))
    report={
      'contract_version':1,'kind':kind,'sha256':digest.hexdigest(),
      'checked_at_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),
      'physical_lines':rows,'valid_json_objects':valid,
      'invalid_physical_lines':rows-valid,
      'json_error_kinds':dict(sorted(errors.items())),
      'first_invalid_line_numbers':bad_lines,
      'key_field':KEYS[kind],'distinct_valid_keys':len(seen),
      'duplicate_valid_keys':dupes,'missing_keys':missing,
      'status':'invalid' if errors or missing or (dupes and kind!='raw') else
               'ok_with_duplicates' if dupes else 'ok',
      'note':'Contagem de LINHAS físicas; fragmentos de legendas não são posts independentes',
    }
    return report


def main(argv=None)->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--kind',required=True,choices=sorted(KEYS))
    p.add_argument('--report',type=Path,help='Salvar somente métricas, sem conteúdos nem IDs')
    args=p.parse_args(argv)
    summary=audit(args.input,args.kind)
    body=json.dumps(summary,ensure_ascii=False,indent=2)+'\n'
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(body,encoding='utf-8')
    print(body,end='')
    return 2 if summary['invalid_physical_lines'] else 3 if (summary['missing_keys'] or
        (summary['duplicate_valid_keys'] and args.kind!='raw')) else 0

if __name__=='__main__':
    raise SystemExit(main())
