# Homologação A3/A4 — 22/10/2026

## A. Estado inicial e diagnóstico

Branch `main`, HEAD inicial `0ce6dbf58aa0ddf16cda66addc865f051972ead2`, worktree limpo. Baseline: 98 testes Python aprovados em Docker. Não houve reset/checkout/pull, commit, push ou merge.

Problemas encontrados: cache legado por post_code; ausência de identidade de entrada/prompt/modelo/parâmetros; descarte de usage do provedor; retries sem reserva financeira durável; gravação append sem recuperação de resultado; validação apenas superficial dos objetos; decisões editoriais sem vínculo com versão da extração. Um segundo problema foi descoberto no ensaio: ranking/classe de triagem e perfil de descoberta enviados ao LLM variavam entre lotes, causando inferência desnecessária de conteúdo intacto.

Raw e extrações históricas completas continuam ausentes. Há 100 registros editoriais históricos; seus estados não constituem gabarito de campos nem prova de atualidade. Os arquivos novos de extração existentes sob output/reconciliation são fixtures desta homologação, não dados Maritaca reais.

## B. Implementações

| Arquivo | Resultado |
|---|---|
| `etl/extracao_versionada.py` | Plano offline, request/result IDs, cache, importação legacy, reservas, tentativas/respostas/outcomes duráveis, usage e exports |
| `etl/extrair_llm.py` | CLI legado encaminhado ao plano seguro; inferência direta sem orçamento desativada; mensagens excluem ranking/classe/perfil de descoberta |
| `etl/validacao_extracao.py` | Validador novo estrito de esquema/tipos/valores/evidência/contradições, mantendo função legada compatível |
| `etl/criar_revisao.py` | JSONL+CSV versionados, defaults review, importação CSV com evidência congelada e sem sobrescrever decisões |
| `etl/preparar_publicacao.py` | Guarda de versão/digest e campos humanos; recusa múltiplas revisões ambíguas por post |
| `etl/triagem_avancada.py` | SHA-256 da entrada no resumo para vincular métricas ao lote A1 |
| `etl/avaliar_extracoes.py` | Referência estratificada vazia, métricas por campo/tipo/fonte somente com gabarito identificado |
| `etl/a3_fixtures.py`, `etl/homologar_a3.py` | Respostas explicitamente sintéticas e ensaio completo reproduzível, SQLite ou D1 isolado |
| `tests/test_a3_versioned.py`, `tests/test_a4_editorial.py` | Regressões offline, orçamento/recuperação e revisão |

Sem mudança de frontend, Worker, schema D1, seed versionado, resolver A2, SQL A5, registry/overrides reais ou prompt. Prompt SHA-256: `e60949bfb5bc4e2dc529d8318ee456892b27e44006e0f05504dba613e86ffeda`, comparado byte a byte com HEAD.

## C. Versionamento e cache

Request_id inclui plataforma/post_code, entrada efetivamente renderizada, bytes do prompt, modelo solicitado, parâmetros, contrato e provedor. Extraction_id congela a resposta/evidência validada e sua proveniência. Lote, perfil de descoberta, ranking, curtidas e horários de aquisição não provocam nova inferência. Alteração de legenda ou metadado factual efetivamente enviado gera nova solicitação. O resultado também registra modelo efetivo/id do provedor quando disponíveis; valores desconhecidos não são inventados.

Resultado completo, íntegro, revalidado e ok/discard sem pendências determinísticas pode ser reutilizado. Partial, JSON inválido, truncamento e evidência sem suporte não são cache válido; tentativa anterior não resolvida exige revisão/retry explícito em vez de repetir gasto silenciosamente. Resposta persistida antes de falha de disco é recuperada sem nova chamada. Legacy sem hashes suficientes é preservado como legacy_unverified, sem atribuir modelo/prompt desconhecidos.

Cada export contém a revisão selecionada pelo plano. Uma aprovação da versão antiga não publica a nova; históricos de várias versões por post exigem seleção explícita, não “última linha vence”. Os quatro estados editoriais permanecem.

## D. Custo e controle de execução

**Chamadas reais: zero. Gasto de inferência nesta tarefa: zero.** Nenhum preço Maritaca foi consultado ou presumido. A prévia pode rodar sem preços e retorna custo null. Os cenários automatizados usam moeda TEST, taxas fictícias e usage gerado pela fixture; não medem tokens faturados ou custo do modelo real.

Estimativa exploratória: caracteres das mensagens reais / 3; saída prevista usa max_tokens. O planejador registra bytes e distingue estimativa de usage recebido. Essa heurística não é bound confiável e não permite execução sozinha. Para futuro opt-in são exigidos preços/moeda/referência, limite de tokens verificado com origem apropriada, plan_id aprovado, referência de autorização, teto e limites de tentativas. Sem isso, bloqueia antes de chamar o provedor.

A reserva ocorre antes da rede; é acumulada por autorização, inclusive entre planos. Erros/timeout mantêm custo incerto e não liberam reserva. Máximo de retries explícito (padrão 1 tentativa total, até 3 aprovadas), cada um reservado. Usage acima do bound bloqueia a autorização. Accounting distingue rodada atual e ledger, incluindo recuperação de resposta após crash. Custo por usage é cálculo pela cotação fornecida, não garantia/fatura externa.

No ensaio final, 8 inferências **sintéticas** processaram 7 posts lógicos e uma revisão de legenda. Primeiras execuções reaproveitaram 7 resultados; as três reexecuções fizeram zero inferências, com 14 hits de cache no total. A ambiguidade partial permaneceu bloqueada para retry/revisão; não foi disfarçada de hit válido. Cache sintético não pode satisfazer plano Maritaca.

## E. Qualidade e referências

Resultados mensuráveis da fixture final: 7 predições vigentes, 6 ok e 1 partial; todas passaram pelas verificações estruturais e de citações literais. O validador também detecta endereço sem suporte textual, booleano sem evidência explícita, evento sem data e conflito gratuidade/ingresso. Esses são testes de engenharia, não precisão real de extração.

Foi gerada fila estratificada de 20 registros editoriais históricos, rótulos vazios, com origem explicitamente histórica e sem extração correspondente. A referência sintética tem 7 casos também pending. Gabaritos humanos reais: **zero**. Acurácia, recall, erro real de alucinação, custo por entidade real aprovada e comparação de modelos não puderam ser medidos. Os relatórios deixam métricas vazias/null; testes de cálculo usam rótulo SYNTHETIC_REFERENCE_ONLY, não os apresentam como anotação humana.

Comparação literal não prova que o trecho justifica semanticamente data/endereço/classificação. Heurísticas conservadoras podem gerar falsos positivos. Unidade, atualidade, inferências temporais, categorias e tags continuam sujeitos à revisão humana. Confiança ≥0,75 permanece necessária e insuficiente. Sem dados anotados, não há recomendação comprovada de modelo barato nem proposta empiricamente validada para mudar o prompt original.

## F. Testes e evidências

| Camada | Resultado |
|---|---|
| Baseline Docker | 98/98 aprovados |
| Suíte final Docker | **140/140 aprovados**, zero falhas, zero skips |
| A3 | **38/38 aprovados** |
| A4 específica | **4/4 aprovados**; outros casos editoriais também exercitados em A3/legado |
| Ensaio completo offline | Aprovado em SQLite em memória |
| Ensaio completo Wrangler | Aprovado em D1 persistente **local isolado** |
| Prompt e diff | Bytes preservados; git diff --check aprovado |

Cobertura: hit/miss; legenda/prompt/modelo/parâmetros; metadado irrelevante; legado desconhecido; arquivo interrompido; JSON/esquema inválidos; partial/discard; truncamento; 429/timeout/retry limitado; orçamento insuficiente; opt-in/prévia ausentes; resposta recuperada; usage e excesso de bound; revisão/digest/CSV forjados; evento sem data; gratuidade/ingresso; evidência inventada; gabarito ausente/versionado; A1/A2/A5.

Evidências ignoradas pelo Git:

- `etl/output/a3_validation/`: baseline, docker_final.log, a3_final.log, a4_final.log, inventário e fila histórica pending.
- `etl/output/a3_ensaio_verificado/`: fluxo offline final, três manifestos A1, planos A3, requests/results/attempts, filas editoriais e relatórios de qualidade.
- `db/reconciliation/a3_20261022_v2/`: ensaio D1 após corrigir o payload/cache, logs completos, snapshots, SQL, plano A5 e backup sintético com hashes.
- `a3_ensaio_inicial`, `a3_ensaio_final` e D1 v1 foram preservados como evidência incremental, não confundidos com medição final do cache corrigido.

Os unittest e ensaio sem flag Wrangler usam SQLite em memória; o ensaio com flag usa Docker/Wrangler/Miniflare e arquivos persistentes reais. Não somar 38/4 aos 140 como se fossem testes únicos adicionais. TypeScript/build frontend não foram repetidos: nenhum desses componentes mudou.

## G. Integração completa

| Etapa sintética | Recebidos A1 | Novos | Repetidos | Alterados | Inferências fake | Hits na primeira execução | Inferências na repetição | Entidades |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 2 | 2 | 0 | 0 | 2 | 0 | 0 | 2 |
| 2 | 7 | 5 | 2 | 0 | 5 | 2 | 0 | 3 |
| 3 | 1 | 0 | 0 | 1 | 1 | 5 | 0 | 3 |

Cenário: lugar novo, repetição, segunda fonte da mesma unidade, filial separada, evento futuro, evento vencido, promoção, ambiguidade e legenda alterada. As filas recém-geradas não publicaram nada. Somente decisões SYNTHETIC_TEST_ONLY da fixture permitiram preparar os itens elegíveis. A mudança de legenda gerou novo extraction_id e bloqueou a aprovação antiga antes da nova decisão sintética.

A2 fixou o ID do primeiro lugar mesmo quando outra publicação virou fonte primária; a filial permaneceu separada. Evento vencido foi expired, promoção hidden e ambiguidade review. Catálogo canônico final: 3 entidades (2 lugares e 1 evento futuro).

D1: inicial canônico com 2 linhas; incremento/seed deixa 4 linhas por causa do card legado duplicado. Sem aprovação A5, plano recusado. Com aprovação exclusiva de fixture: 4 linhas, 3 published e 1 hidden; SQL PASS e verify true. Segunda aplicação manteve snapshot inteiro idêntico. Rollback SQL passou e nova aplicação seguida de seed canônico manteve o legado hidden. Backup sintético foi criado com one-offs encerrados, antes do seed de incremento, e conferido por hashes. A restauração integral já tinha evidência suficiente na A5/A1 anterior e não foi repetida desnecessariamente neste ciclo.

Persistência nova: `.wrangler/a3_a3_20261022_v2/state`. Nenhuma operação do ensaio apontou para `.wrangler/state` principal. A base principal não recebeu consultas mutáveis nem fixtures; último estado confirmado na A1: 13 publicados. Registry/overrides reais continuam sem promoção e decisões Pescados/SPACE FRIENDS permanecem pendentes.

## H. Estado da Frente A

| Frente | Estado |
|---|---|
| A0 | Contratos auditados; complementados para A3/A4 |
| A1 | Técnica offline homologada, regressões mantidas; aquisição real ainda não validada/autorizada |
| A2 | Técnica sintética homologada, IDs estáveis; registry/unidades/fusões reais dependem de humano |
| A3 | Implementada e homologada offline; qualidade, usage/custo real, tokenizer/bound e operação live pendentes de dados/autorização |
| A4 | Fluxo técnico CSV/JSONL e guards homologados; nenhuma aprovação real ou referência humana de campos criada |
| A5 | Técnica no D1 local isolado validada; aplicação editorial real continua pendente |
| A6 | Não homologada neste ciclo; o checkout só a menciona sob gates, sem escopo operacional detalhado suficiente para declarar conclusão |

Nenhuma classificação técnica equivale à prontidão de publicação pública ou autorização para gastar.

## I. Próximos gates

**Aquisição:** aprovar nominalmente fontes/URLs/perfis, método e direito de acesso/reutilização, limites/janela/cadência, manifesto e responsável editorial. Proposta: 160 em 2×80, diversidade 60 gastronomia/40 lazer/40 agendas/20 cultura ou espaços públicos, sem prometer cobertura que o método não suporta. Não foi executada.

**Maritaca paga (autorização separada):** após ingestão/triagem, aprovar plan_id, modelo/prompt/contrato e destino dos dados, cotação com data/moeda/origem, bound de tokens verificado, até 20 tentativas iniciais (inclui retries) e teto monetário. Proposta política: R$20 se cotação e autorização forem em BRL; não é preço Maritaca nem promessa de rendimento. Para outra moeda, aprovar teto nessa moeda. Sem cotação/bound confiável, não executar, mesmo com dados coletados. Reavaliar 10–20 itens e gabarito humano antes de ampliar gasto.

**Editorial/publicação:** confirmar unidade/fonte e registry de Pescados, investigar SPACE FRIENDS mantendo separado enquanto incerto, revisar evidência e atualidade e aprovar eventual ocultação real A5 separadamente. Aquisição/inferência não autorizam publicação.

Plano detalhado: `docs/PILOTO_DADOS_RECENTES.md`. Operação: `docs/A3_EXTRACAO_VERSIONADA.md`. Qualidade: `docs/A3_AVALIACAO_QUALIDADE.md`. Revisão: `docs/A4_REVISAO_EDITORIAL.md`.

## J. Arquivos, Git e reprodução

Prontos para revisão e eventual commit: módulos novos `etl/extracao_versionada.py`, `etl/avaliar_extracoes.py`, `etl/a3_fixtures.py`, `etl/homologar_a3.py`; modificações em `extrair_llm.py`, `validacao_extracao.py`, `criar_revisao.py`, `preparar_publicacao.py`, `triagem_avancada.py`; testes A3/A4; quatro documentos operacionais novos e este relatório; adendos a ETL_OPERACAO, CONTRATOS_DADOS, A1_COLETA_INCREMENTAL, LANCAMENTO e decisions (D-037 a D-040).

Continuam ignorados: raw/processed/output, db/reconciliation, .wrangler, credenciais/cookies/sessões, caches e referências/anotações humanas com conteúdo privado. O código de fixtures é sintético e explicitamente rotulado; arquivos gerados não entram no commit. Não houve commit/push/merge.

Comandos mínimos, na raiz:

```bash
docker compose run --rm etl -m unittest discover -s tests -v
docker compose run --rm etl -m unittest discover -s tests -p 'test_a3*.py' -v
docker compose run --rm etl -m unittest discover -s tests -p 'test_a4*.py' -v
# Saída NOVA; nenhum provedor externo:
docker compose run --rm etl etl/homologar_a3.py --outdir etl/output/a3_repro_novo
# Host Linux/WSL, Docker necessário; D1 novo isolado:
python3 etl/homologar_a3.py --outdir db/reconciliation/a3_repro_novo --wrangler
```

Nenhum scraping, login, chamada paga, deploy, D1 remoto, limpeza de catálogo ou aprovação real inventada ocorreu. Alterações finais apenas no accounting/erros/metadados foram cobertas pela suíte final e ensaio offline; não alteraram A2/SQL A5 nem exigiram repetir novamente o ensaio Wrangler já aprovado.

Prévia adicional sem rede: `etl/output/a3_validation/maritaca_preview_no_price.json` usa namespace Maritaca sobre as 7 entradas **sintéticas** para comprovar isolamento do cache. Hits=0; estimativa exploratória=36.528 tokens de entrada e até 17.500 de saída; tokens reais e custos continuam null. Isso não é custo ou consumo de uma execução Maritaca. Integridade do prompt e resumo final também estão em `a3_validation/`.
