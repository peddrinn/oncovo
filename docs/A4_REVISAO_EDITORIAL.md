# A4 — fila editorial vinculada à evidência

A4 técnica local, sem painel e sem aprovação real nesta entrega. `criar_revisao.py` gera JSONL + CSV novos; cada linha tem extraction_id/request_id/versão/batch_id, post_code, tipo/nome, bairro/endereço/data, campos ausentes, riscos/evidências e dados editoriais. Todas começam em `review`. Históricos de decisão não são sobrescritos.

```bash
docker compose run --rm etl etl/criar_revisao.py \
  --input etl/processed/LOTE/extractions.jsonl \
  --output etl/processed/LOTE/review_pending.jsonl
```

A pessoa confere a versão exata da fonte/evidência, unidade física, funcionamento atual, preço/datas e riscos. No CSV, campos editoriais editáveis: `publish_status`, `reviewed_by`, `reviewed_at`, `approval_reason`, `currentness_recheck_required`, título/subtítulo de exibição e notas. Os demais campos ficam congelados. Status permitidos: published/review/expired/hidden. Confiança ≥0,75 é necessária, insuficiente e não substitui o responsável humano.

Para aprovar, preencher revisor, data YYYY-MM-DD, justificativa e definir `currentness_recheck_required=false` somente após rechecagem efetiva. A fila de teste usa aprovadores fictícios exclusivamente identificados como SYNTHETIC_TEST_ONLY; nunca copiar para dados reais.

Converter CSV revisado para **novo** JSONL:

```bash
docker compose run --rm etl etl/criar_revisao.py \
  --input etl/processed/LOTE/review_pending.jsonl \
  --decisions-csv etl/processed/LOTE/review_human.csv \
  --output etl/processed/LOTE/editorial_reviewed.jsonl
```

O importador recusa alteração de IDs/evidências, linhas desconhecidas/repetidas/removidas, booleano de rechecagem inválido e aprovação incompleta. Não modifica o template/CSV original. O JSONL resultante alimenta `preparar_publicacao.py` com as extrações exportadas do plano vigente.

O publicador exige extraction_id/evidence_digest iguais ao hash íntegro da extração, além dos campos de aprovação. Evidência nova gera nova fila `review`; a aprovação anterior continua arquivada para a versão antiga. Históricos com várias versões do mesmo post não são resolvidos por “última linha”: o build recusa ambiguidade e exige export do plano vigente. Extrações incompletas, promoções, recorrência ambígua e eventos sem data/expirados continuam sujeitos aos filtros anteriores. Uma fusão A2/A5 não aprova operação atual.

Dados legados sem versão continuam legíveis, sem inventar hashes/modelos. Essa compatibilidade não os transforma em aprovação versionada, extração reutilizável ou prova de atualidade. Não promover os 100 registros históricos ao fluxo público por causa deste suporte.

Quando uma informação extraída estiver errada, registrar o erro na avaliação e criar uma revisão explícita da extração/evidência antes de aprovar. Não editar endereço/data congelados no CSV para mascarar erro do extrator. A autorização A5 de ocultação permanece separada, com seu próprio gate.
