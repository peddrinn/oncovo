"""A5: plano offline e UPDATE único/atômico para D1 LOCAL, com revisão humana.

Nunca conecta ao banco, não executa Wrangler, não modifica produção. Não interpreta
omissão de um lote parcial como retirada. Reversão requer snapshot pós-aplicação.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

from auditar_reconciliacao import audit, FIELDS as AUDIT_FIELDS
from resolver_entidades import read_jsonl

APPROVAL = 'approved_hide_duplicate'
PLAN_VERSION = 'a5-local-v1'
FIELDS = ('id', 'source_id', 'status', 'type', 'title', 'address', 'updated_at')


def _sha(data: object) -> str:
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True,
                         separators=(',', ':')).encode('utf-8')).hexdigest()


def snapshot(path: Path) -> list[dict]:
    """Aceita JSONL de SELECT D1 ou export --json da consulta Wrangler.

    Não aceita dumps SQL nem snapshots sem updated_at e colunas de comparação.
    """
    content = path.read_text(encoding='utf-8').strip()
    if not content:
        raise ValueError('Snapshot vazio')
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        rows = read_jsonl(path)
    else:
        if isinstance(parsed, dict) and isinstance(parsed.get('results'), list):
            rows = parsed['results']
        elif isinstance(parsed, list) and len(parsed) == 1 and isinstance(parsed[0], dict) and 'results' in parsed[0]:
            rows = parsed[0]['results']
        elif isinstance(parsed, list) and all(isinstance(x,dict) and 'id' in x for x in parsed):
            rows = parsed
        else:
            raise ValueError('Snapshot JSON deve conter results[] ou linhas com id')
    if not isinstance(rows,list) or not all(isinstance(r,dict) for r in rows):
        raise ValueError('Linhas inválidas no snapshot')
    ids=set()
    for row in rows:
        if not all(key in row for key in FIELDS):
            raise ValueError('Snapshot D1 precisa de id,source_id,status,type,title,address,updated_at; '
                             'obtenha-o com SELECT completo e --json')
        if not isinstance(row['id'],str) or not row['id'] or row['id'] in ids:
            raise ValueError('Snapshot com ID vazio/repetido')
        ids.add(row['id'])
        if not isinstance(row['updated_at'],str) or not row['updated_at']:
            raise ValueError('updated_at é obrigatório para proteção contra estado desatualizado')
    return rows


def csv_rows(path: Path) -> list[dict]:
    with path.open(encoding='utf-8',newline='') as handle:
        records = list(csv.DictReader(handle))
    if not records:
        raise ValueError('CSV vazio')
    return records


def proposal_plan(previous: list[dict], canonical: list[dict], mappings: list[dict],
                  decisions: list[dict], *, filename: str = '') -> dict:
    """Confere cada aprovação contra a proposta A2.1 recalculada, não aceita IDs arbitrários."""
    before={r['id']:r for r in previous}
    after={r['id']:r for r in canonical}
    proposal=audit(previous,canonical,mappings)
    allowed={r['original_card_id']:r for r in proposal['actions']}
    accepted=[];seen=set();pending=[]
    for row in decisions:
        old_id=(row.get('original_card_id') or '').strip()
        if not old_id or old_id in seen:
            raise ValueError(f'ID ausente/repetido no CSV editorial: {old_id}')
        seen.add(old_id)
        decision=(row.get('editorial_decision') or '').strip()
        if decision not in ('pending_review','rejected', APPROVAL):
            raise ValueError(f'Decisão desconhecida para {old_id}: {decision}')
        if old_id not in allowed:
            raise ValueError(f'CSV contém ID sem proposta auditável: {old_id}')
        expected=allowed[old_id]
        for field in ('post_code','new_card_id','entity_id','original_source_id','action'):
            if (row.get(field) or '') != str(expected[field]):
                raise ValueError(f'CSV alterou evidência de {old_id}: {field}')
        if decision != APPROVAL:
            pending.append(old_id)
            continue
        reviewer=(row.get('reviewed_by') or '').strip()
        reviewed=(row.get('reviewed_at') or '').strip()
        evidence=(row.get('evidence_url') or '').strip()
        if not reviewer or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',reviewed):
            raise ValueError(f'Aprovação requer revisor e data ISO: {old_id}')
        try: date.fromisoformat(reviewed)
        except ValueError as exc: raise ValueError(f'Data editorial inválida: {old_id}') from exc
        approval_reason=(row.get('approval_reason') or '').strip()
        approval_evidence=(row.get('approval_evidence_url') or '').strip()
        if (not evidence.startswith('https://') or not approval_evidence.startswith('https://')
            or len(approval_reason)<12):
            raise ValueError(f'Aprovação requer justificativa editorial e link de evidência HTTPS: {old_id}')
        old=before[old_id];new=after[expected['new_card_id']]
        if old.get('status') != 'published' or new.get('status') != 'published':
            raise ValueError('Ambos os registros devem estar publicados no snapshot/catálogo')
        if old.get('type') != new.get('type'):
            raise ValueError('Tipos incompatíveis')
        if not old.get('updated_at') or not old.get('title'):
            raise ValueError('Snapshot antigo não possui updated_at/título')
        live_target=before.get(new['id'])
        if (not live_target or live_target.get('status')!='published'
            or live_target.get('source_id')!=new['source_id']
            or live_target.get('type')!=new['type']
            or live_target.get('title')!=new.get('title')
            or live_target.get('address')!=new.get('address')):
            raise ValueError('Canônico deve estar publicado no D1 local ANTES do snapshot; aplique seed local e exporte novamente')
        accepted.append({
            'old_id':old_id,'old_source':old['source_id'],'kind':old['type'],
            'old_title':old['title'],'old_address':old.get('address'),
            'old_updated':old['updated_at'],
            'new_id':new['id'],'new_source':new['source_id'],'new_kind':new['type'],
            'new_title':live_target['title'],'new_address':live_target.get('address'),
            'new_updated':live_target['updated_at'],
            'entity_id':expected['entity_id'],
            'reviewed_by':reviewer,'reviewed_at':reviewed,'evidence_url':evidence,
            'reason':approval_reason, 'approval_evidence_url':approval_evidence,
        })
    if seen != set(allowed):
        raise ValueError('CSV editorial incompleto: propostas foram removidas; gere nova fila e revise todas')
    if not accepted:
        raise ValueError('Nenhuma despublicação aprovada. Edite editorial_decision e revisor; não há SQL a executar.')
    if len({r['old_id'] for r in accepted})!=len(accepted):
        raise ValueError('IDs duplicados no plano')
    accepted.sort(key=lambda x:x['old_id'])
    identity={'version':PLAN_VERSION,'actions':accepted}
    plan_id=_sha(identity)[:16]
    return {**identity,'plan_id':plan_id,'snapshot_digest':_sha(sorted(previous,key=lambda r:r['id'])),
            'canonical_digest':_sha(sorted(canonical,key=lambda r:r['id'])),
            'pending_or_rejected_ids':sorted(pending),'proposals_total':len(allowed),
            'snapshot_source':filename,
            'created_at':datetime.now(timezone.utc).isoformat(),
            'scope':'D1 LOCAL; nunca aplicar remotamente; não prova lugar aberto'}


def _sql(value: object) -> str:
    if value is None: return 'NULL'
    return "'"+str(value).replace("'","''")+"'"


def sql_update(plan: dict, mode: str, *, post_snapshot: list[dict] | None = None) -> str:
    """Um único UPDATE atômico com conjunto de guardas: nada de BEGIN/COMMIT em D1."""
    if plan.get('version')!=PLAN_VERSION or not plan.get('actions'):
        raise ValueError('Plano inválido')
    if plan.get('plan_id') != _sha({'version':PLAN_VERSION,'actions':plan['actions']})[:16]:
        raise ValueError('Plano modificado após revisão; gere novamente')
    actions=plan['actions']
    if mode not in ('apply','rollback'):
        raise ValueError('mode inválido')
    if mode=='rollback':
        if post_snapshot is None:
            raise ValueError('Reversão exige snapshot pós-aplicação fresco')
        by_id={r['id']:r for r in post_snapshot}
        for item in actions:
            before=by_id.get(item['old_id'])
            if not before or before.get('status')!='hidden':
                raise ValueError('Reversão recusada: ID não está oculto')
            for col,key in [('source_id','old_source'),('type','kind'),('title','old_title'),('address','old_address')]:
                if before.get(col)!=item[key]:
                    raise ValueError('Reversão recusada: registro oculto foi alterado')
    else:
        post_snapshot=None
    # A última coluna é o timestamp efetivamente observado no banco em cada etapa.
    cols=('old_id','old_source','kind','old_title','old_address','expected_updated',
          'new_id','new_source','new_kind','new_title','new_address','new_updated')
    tuples=[]
    for row in actions:
        observed=(next(r['updated_at'] for r in post_snapshot if r['id']==row['old_id'])
                  if post_snapshot is not None else row['old_updated'])
        tuples.append('('+', '.join(_sql(v) for v in (
            row['old_id'],row['old_source'],row['kind'],row['old_title'],row['old_address'],
            observed,row['new_id'],row['new_source'],row['new_kind'],
            row['new_title'],row['new_address'],row['new_updated']))+')')
    from_status,to_status=('published','hidden') if mode=='apply' else ('hidden','published')
    comment=f'-- A5 {mode} LOCAL SOMENTE / plano {plan["plan_id"]} / N={len(actions)}\n'
    comment+='-- Uma instrução UPDATE indivisível; guardas tornam alterações totais ou nulas.\n'
    sql=(f'WITH expected({", ".join(cols)}) AS (VALUES\n  '+',\n  '.join(tuples)+')\n'
         f"UPDATE search_items SET status='{to_status}', updated_at=CURRENT_TIMESTAMP\n"
         'WHERE id IN (SELECT old_id FROM expected)\n'
         f"  AND status='{from_status}'\n"
         '  AND (SELECT COUNT(*) FROM expected) = (\n'
         '    SELECT COUNT(*) FROM expected e JOIN search_items old ON old.id=e.old_id\n'
         f"    WHERE old.status='{from_status}' AND old.source_id=e.old_source AND old.type=e.kind\n"
         '      AND old.title IS e.old_title AND old.address IS e.old_address\n'
         '      AND old.updated_at=e.expected_updated\n'
         '  )\n'
         '  AND (SELECT COUNT(*) FROM expected) = (\n'
         '    SELECT COUNT(*) FROM expected e JOIN search_items new ON new.id=e.new_id\n'
         "    WHERE new.status='published' AND new.source_id=e.new_source AND new.type=e.new_kind\n"
         "      AND new.title IS e.new_title AND new.address IS e.new_address\n"
         "      AND new.updated_at=e.new_updated\n"
         '  )\n'
         'RETURNING id,status;\n')
    return comment+sql


def sql_verify(plan:dict, expected_status:str) -> str:
    count=len(plan['actions'])
    checks=[]
    for row in plan['actions']:
        for prefix, status, fields in (
            ('old', expected_status, [('source_id','old_source'),('type','kind'),
             ('title','old_title'),('address','old_address')]),
            ('new', 'published', [('source_id','new_source'),('type','new_kind'),
             ('title','new_title'),('address','new_address'),('updated_at','new_updated')]),
        ):
            conditions=[f'id={_sql(row[prefix+"_id"])}',f'status={_sql(status)}']
            conditions.extend(f'{field} IS {_sql(row[key])}' for field,key in fields)
            checks.append('EXISTS (SELECT 1 FROM search_items WHERE '+' AND '.join(conditions)+')')
    ids=','.join(_sql(row['old_id']) for row in plan['actions'])
    return (f"-- Verificar após A5 {plan['plan_id']} no D1 LOCAL.\n"
            f"SELECT CASE WHEN {' AND '.join(checks)} THEN 'PASS' ELSE 'FAIL' END AS reconciliation_check,"
            f" COUNT(*) AS status_count, {count} AS expected_count FROM search_items "
            f"WHERE id IN ({ids}) AND status={_sql(expected_status)};\n"
            "SELECT COUNT(*) AS published_cards FROM search_items WHERE status='published';\n")


def verify_snapshot(plan:dict, state: list[dict], *, rolled_back=False) -> dict:
    if plan.get('plan_id') != _sha({'version':PLAN_VERSION,'actions':plan['actions']})[:16]:
        raise ValueError('Plano modificado após revisão')
    by_id={r['id']:r for r in state}
    target='published' if rolled_back else 'hidden'
    issues=[]
    for row in plan['actions']:
        old=by_id.get(row['old_id']);new=by_id.get(row['new_id'])
        if not old or old['status']!=target:
            issues.append('status de origem incorreto: '+row['old_id'])
        elif any(old.get(field)!=row[key] for field,key in [
              ('source_id','old_source'),('type','kind'),('title','old_title'),('address','old_address')]):
            issues.append('campos de origem alterados: '+row['old_id'])
        if (not new or new['status']!='published' or new['source_id']!=row['new_source']
            or new.get('title')!=row['new_title'] or new.get('address')!=row['new_address']
            or new.get('type')!=row['new_kind'] or new.get('updated_at')!=row['new_updated']):
            issues.append('canônico ausente ou alterado: '+row['new_id'])
    return {'plan_id':plan['plan_id'],'expected_status':target,'passed':not issues,
            'actions':len(plan['actions']),'issues':issues}


def main(argv: list[str]|None=None) -> int:
    p=argparse.ArgumentParser(description=__doc__)
    commands=p.add_subparsers(dest='command',required=True)
    template=commands.add_parser('prepare-review',help='Criar CSV editorial com colunas adicionais, SEM aprovar')
    template.add_argument('--snapshot',required=True,type=Path)
    template.add_argument('--canonical',required=True,type=Path)
    template.add_argument('--source-map',required=True,type=Path)
    template.add_argument('--output',required=True,type=Path)
    plan=commands.add_parser('plan',help='Gerar SQL para revisão, SEM executar')
    for name in ('snapshot','canonical','source-map','decisions','outdir'):
        plan.add_argument('--'+name,required=True,type=Path)
    undo=commands.add_parser('rollback',help='Gerar SQL de reversão a partir de snapshot pós-aplicação')
    undo.add_argument('--plan',required=True,type=Path)
    undo.add_argument('--snapshot',required=True,type=Path)
    undo.add_argument('--outdir',required=True,type=Path)
    check=commands.add_parser('verify',help='Conferir snapshot pós-operação')
    check.add_argument('--plan',required=True,type=Path)
    check.add_argument('--snapshot',required=True,type=Path)
    check.add_argument('--rolled-back',action='store_true')
    args=p.parse_args(argv)
    if args.command=='prepare-review':
        previous=snapshot(args.snapshot)
        canonical=read_jsonl(args.canonical)
        proposals=audit(previous,canonical,csv_rows(args.source_map))
        rows=proposals['actions']
        cols=list(AUDIT_FIELDS)
        for key in ('approval_reason','approval_evidence_url'):
            if key not in cols:cols.append(key)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        if args.output.exists():raise ValueError('CSV de revisão já existe; não sobrescrever decisões humanas')
        with args.output.open('w',encoding='utf-8',newline='') as handle:
            writer=csv.DictWriter(handle,fieldnames=cols);writer.writeheader();writer.writerows(rows)
        print(f'CSV editorial preparado com {len(rows)} propostas, sem aprovações automáticas:',args.output)
        return 0
    if args.command=='plan':
        old=snapshot(args.snapshot);canonical=read_jsonl(args.canonical)
        plan_data=proposal_plan(old,canonical,csv_rows(args.source_map),csv_rows(args.decisions),filename=args.snapshot.name)
        outdir=args.outdir;outdir.mkdir(parents=True,exist_ok=True)
        (outdir/'a5_plan.json').write_text(json.dumps(plan_data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        (outdir/'a5_apply.sql').write_text(sql_update(plan_data,'apply'),encoding='utf-8')
        (outdir/'a5_verify.sql').write_text(sql_verify(plan_data,'hidden'),encoding='utf-8')
        print(json.dumps({'plan_id':plan_data['plan_id'],'approved':len(plan_data['actions']),
            'pending_or_rejected':len(plan_data['pending_or_rejected_ids']),'execution':'NOT executed'},ensure_ascii=False))
    else:
        plan_data=json.loads(args.plan.read_text(encoding='utf-8'))
        state=snapshot(args.snapshot)
        if args.command=='rollback':
            outdir=args.outdir;outdir.mkdir(parents=True,exist_ok=True)
            (outdir/'a5_rollback.sql').write_text(sql_update(plan_data,'rollback',post_snapshot=state),encoding='utf-8')
            (outdir/'a5_verify_rollback.sql').write_text(sql_verify(plan_data,'published'),encoding='utf-8')
            print('Plano de reversão gerado, NÃO executado; use apenas no D1 local.')
        else:
            report=verify_snapshot(plan_data,state,rolled_back=args.rolled_back)
            print(json.dumps(report,ensure_ascii=False,indent=2))
            return 0 if report['passed'] else 2
    return 0


if __name__=='__main__':
    raise SystemExit(main())
