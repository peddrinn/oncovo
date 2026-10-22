# A3 — protocolo de qualidade

Diferenciar quatro coisas: JSON/esquema válidos; contradições determinísticas; comparação contra gabarito humano; decisão editorial/atualidade. Confiança declarada pelo modelo não é precisão medida.

## Validação automática

O caminho legado `validate()` continua compatível. A3 usa `validate_versioned()`: campos internos/tipos/enumerações obrigatórios, booleanos tri-state, confiança finita [0,1], datas/horários válidos, datas invertidas e cidade/nome críticos. Campos faltantes, recorrência/data ambígua e gratuidade+ingresso contraditórios vão para `partial`/revisão.

Citações são conferidas contra o Post efetivamente enviado, nunca contra os exemplos do prompt. Citações `metadata.campo: valor` devem corresponder ao metadado enviado. Nome, endereço/unidade, bairro, local e preço recebem teste conservador de suporte literal normalizado; cidade reconhece BH/Belo Horizonte. Booleanos precisam de evidência e pistas explícitas de gratuidade, ingresso ou reserva. Falha marca risco e impede status ok reutilizável/publicação.

Isso detecta erros verificáveis, mas não prova vínculo semântico: uma citação pode existir e não justificar a classificação/data. Sinônimos, abreviações e paráfrases legítimas podem gerar falsos positivos de revisão. Tags, inferências temporais, unidade física e atualidade precisam de humano. Não afrouxar o validador apenas para aumentar rendimento.

## Amostra e rótulos

`avaliar_extracoes.py prepare` seleciona deterministicamente em rodízio entre content_types, até 20 registros, com IDs exatos. Para um piloto real, buscar aproximadamente 8 lugares, 6 eventos, 2 promoções e 4 ambiguidades; se um estrato não existir, registrar a lacuna, sem fabricar dados. Variar fontes, bairros, endereço com/sem unidade, eventos antigos/futuros, gratuidade/ingresso e recorrências.

Cada referência começa com `labels={}`, status pending, revisor/data/referência vazios. Não preencher por inferência da confiança ou do antigo `publish_status`. O avaliador deve consultar legenda/metadados originais e a resposta congelada. Preferir dois avaliadores para campos críticos, registrar divergências e adjudicação antes de declarar gabarito.

Campos: tipo; nome; cidade/bairro/endereço/unidade; datas e horários; preço/gratuidade/ingresso/reserva; categoria/subcategorias/tags; evidências; confiança/riscos; contradição, alucinação, publicabilidade e correção geral. Chave ausente significa sem gabarito. `null` em labels é valor humano explícito de desconhecido, não campo ainda vazio.

Uma referência utilizável exige `human_review_status=reviewed`, `reviewed_by`, data ISO e `evidence_reference`, além do `extraction_id` exato. Resultados de teste rotulados `SYNTHETIC_REFERENCE_ONLY` não são gabarito humano real.

## Métricas e comandos

```bash
docker compose run --rm etl etl/avaliar_extracoes.py prepare \
  --input etl/processed/LOTE/extractions.jsonl \
  --output etl/processed/LOTE/quality_reference_pending.jsonl --limit 20
# Após anotação humana, em outro arquivo preservado:
docker compose run --rm etl etl/avaliar_extracoes.py score \
  --input etl/processed/LOTE/extractions.jsonl \
  --references etl/processed/LOTE/quality_reference_reviewed.jsonl \
  --output etl/output/LOTE_quality_report_novo.json
```

O score produz acerto exato e denominador por campo, tipo e fonte; listas de tags/subcategorias/riscos são comparadas sem depender da ordem. Não rotular todos os casos desconhecidos como negativos. Julgamentos de alucinação/contradição/publicabilidade são resumidos como observações humanas, sem fingir que o LLM os previu corretamente. Quando `overall_correct` humano existe, Brier compara correção e confiança. Não há precision/recall ou acurácia sem gabarito; métricas ficam vazias/null. Resultados automáticos aparecem em seção própria.

A evidência atual inclui 7 respostas sintéticas, não 7 respostas Maritaca: 6 ok e 1 partial, todas estruturalmente verificadas. A fila histórica com 20 dos 100 registros editoriais tem campos de rótulo vazios e não possui as extrações/raw correspondentes. Ela organiza trabalho futuro, mas **não permite medir precisão, recall, alucinação real, publicabilidade atual ou superioridade de um modelo**.

Antes de comparar modelos, usar exatamente as mesmas entradas/prompt/contrato e referências, registrar parâmetros e preço vigente, separar duplicatas/versões e estratos. Examinar erros críticos por campo e custo por registro aprovado/entidade nova, não só JSON válido ou confiança média. Propostas de melhoria no prompt ficam em documento separado com exemplos anotados e regressões; o prompt original não foi alterado neste ciclo e não há proposta empiricamente validada sem dados humanos.
