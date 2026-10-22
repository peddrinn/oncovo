# A3 — extração versionada, cache e custo

Implementação local/offline homologada em 22/10/2026. Nenhuma inferência Maritaca foi executada. O prompt `etl/prompts/maritaca_legacy_v2.txt` permanece byte a byte igual ao HEAD, SHA-256 `e60949bfb5bc4e2dc529d8318ee456892b27e44006e0f05504dba613e86ffeda`.

## Identidade e reaproveitamento

`request_id` é SHA-256 canônico de plataforma/post_code, hash da mensagem de usuário efetivamente renderizada, hash dos bytes do prompt, modelo solicitado, temperatura/max_tokens, versão `a3-v1` e provedor. O hash não usa batch_id, horário de aquisição, curtidas ou perfis adicionais de descoberta. O corpo efetivamente enviado conserva legenda (até 4.500 caracteres), taken_at, autor, localização, mentions e coautores.

Pontuação/classe da triagem e perfil de descoberta foram retirados **do JSON enviado ao modelo**, pois não constituem evidência factual e variam com ranking/lote. Continuam na entrada/auditoria e métricas por fonte. Isso corrige um defeito observado: um segundo post com legenda igual mudava a penalização de dedupe da triagem e provocava inferência redundante para o primeiro. Não foi alterado o prompt nem o contrato de saída do extrator.

`extraction_id` é outro digest: congela resposta original, payload validado, metadados, tentativa/uso e proveniência. A aprovação editorial refere-se a esse resultado exato, não apenas ao post ou à solicitação. O modelo solicitado e, quando informados pelo provedor, modelo efetivo/id da resposta são registrados. Aliases de modelo não garantem uma versão interna imutável; preferir identificador fixado quando o provedor o disponibilizar.

Cache reutilizável: resposta completa (`finish_reason=stop`), hash íntegro, identidade compatível, esquema/evidência revalidados, status `ok` ou `discard` e nenhuma pendência determinística. `partial`, `error`, resposta truncada/inválida ou evidência sem suporte não viram cache válido. Isso não significa que `ok` esteja publicado: todo resultado entra em revisão. Um descarte final estruturalmente válido pode ser reaproveitado sem gastar novamente.

Fixtures usam provedor `synthetic-fixture` e modelo `fixture-model`; não podem satisfazer o cache `maritaca`. Reencontro em outro perfil com o mesmo conteúdo factual não exige inferência nova. Alterar uma parte de legenda que não foi enviada por truncamento também não altera o request: a decisão segue vinculada à evidência efetivamente enviada, e a limitação de 4.500 caracteres deve ser considerada na revisão.

## Histórico e recuperação

Store padrão ignorado: `etl/processed/a3/`:

```text
requests/<request_id>.json
attempts/<attempt_id>.json       # reserva ANTES da chamada
responses/<attempt_id>.json      # resposta/usage recebidos
outcomes/<attempt_id>.json       # sucesso, partial ou erro
results/<request_id>/<extraction_id>.json
legacy/<digest>.json
runs/<run_id>.json
budget_breaches/<plan_id>
```

Lock de store e arquivos atômicos/fsync evitam leitores sobre escrita incompleta. Uma falha de disco propaga o erro e preserva a reserva; se a resposta já foi gravada, a próxima execução a recupera sem chamar o provedor novamente. Se o processo caiu após envio e antes de persistir a resposta, não se sabe se houve cobrança: não liberar reserva nem repetir automaticamente. Retentativa exige `--retry-reference` e continua sujeita a quantidade/orçamento.

Uma tentativa normal tem retry automático desativado (`max-attempts=1`). Pode-se aprovar explicitamente até 3 tentativas para timeout/429/5xx transitórios, cada qual com nova reserva. JSON/esquema inválido não recebe retry cego. Falhas ficam em outcomes/runs; mensagens de erro não incluem segredos ou conteúdo do corpo. Ausência de usage não é interpretada como gratuidade. Não há limpeza automática de resultados antigos.

Importação legada preserva objeto original, hash do arquivo e linha, classificando `legacy_unverified` ou `legacy_invalid`. Não atribui modelo/prompt/hash de entrada desconhecidos e não abastece cache compatível. O importador lê o arquivo inteiro antes de gravar: JSONL interrompido bloqueia a importação sem descartar linhas.

```bash
docker compose run --rm etl etl/extracao_versionada.py \
  --import-legacy --input etl/processed/extracoes_historicas.jsonl \
  --store etl/processed/a3 --report etl/output/a3_import_novo.json
```

Os caminhos acima são exemplos; as extrações históricas completas não estavam disponíveis nesta homologação.

## Prévia offline

Primeiro concluir A1 e executar triagem. O resumo de triagem agora inclui SHA-256 da entrada. O planejador confere o manifesto/checksums A1, a legenda/data de cada item contra o catálogo e o hash do resumo contra delta/catalog do mesmo lote.

```bash
docker compose run --rm etl etl/extracao_versionada.py \
  --input etl/processed/LOTE/dia1_fila_llm_100.jsonl \
  --batch etl/raw/incremental/batches/LOTE \
  --triage-report etl/processed/LOTE/dia1_resumo.json \
  --store etl/processed/a3 --model MODELO_A_REVISAR \
  --max-tokens 2500 --report etl/output/a3_plano_novo.json
```

A prévia não usa rede, não exige chave e não gera respostas fictícias. Produz recebidos/novos/alterados da A1, descarte da triagem quando seu resumo está disponível, elegíveis, hits, novas inferências candidatas, mudanças que exigem revisão e legendas com menos de 40 caracteres. Sem resumo verificável, descarte da triagem é desconhecido (`null`), não zero. `new_inferences` inclui resultados parciais sem cache: a execução pode bloqueá-los para revisão/retry em vez de gastar automaticamente.

`plan_id` congela entrada, configuração, preços/bounds e hashes dos manifestos. Alterar dados, prompt, modelo ou orçamento técnico exige nova prévia/caminho. Hits de cache não mudam a identidade do plano. Mesmo post com duas revisões diferentes na mesma fila é rejeitado: usar export da revisão vigente, não juntar históricos arbitrariamente.

O CLI legado `extrair_llm.py` encaminha para esse planejador. `extract()` direto sem plano foi desativado para não manter um caminho pago sem limite. `--export --output ...` no CLI legado solicita export; no novo CLI, `--output` exporta somente resultados existentes. Nenhum desses flags aprova publicação. Exports e filas existentes não são sobrescritos.

## Tokens, preços e orçamento

Nenhum preço real foi consultado/confirmado. Sem arquivo explícito de preços, custo previsto é `null`. Os testes usam moeda `TEST` e valores fictícios, sem relação com a tabela Maritaca.

A estimativa exploratória é caracteres das mensagens reais / 3 (arredondado para cima). Tokens de saída previstos usam o limite de saída configurado. Esses números **não são tokens faturados, nem um bound confiável**. O plano também registra bytes UTF-8 para inspeção.

Para permitir execução futura, fornecer preços por milhão de entrada/saída, moeda e referência da cotação aprovada; registrar junto modelo, data e fonte oficial da cotação. Não misturar moedas nem aplicar câmbio implícito. A execução também exige arquivo de bounds por request_id:

```json
{
  "REQUEST_ID_DO_PLANO": {
    "max_input_tokens": 12345,
    "verified": true,
    "reference": "referência da verificação do tokenizer/overhead e responsável"
  }
}
```

`12345` é somente exemplo de formato, não limite recomendado ou validado. A marca `verified` é uma declaração rastreável do operador, que deve verificar tokenizer/overhead/contexto apropriados ao modelo/provedor; não deve ser preenchida a partir da própria heurística /3. Sem verificação confiável, a implementação bloqueia novas chamadas. Obter essa verificação continua sendo gate do piloto; a tarefa não fingiu dispor de tokenizer oficial validado.

A reserva conservadora por tentativa é `bound_entrada × preço_entrada + max_tokens × preço_saída`. Quantidade inclui retries, não só posts. Reservas são acumuladas por **referência de autorização** mesmo entre planos; mudar plan_id não zera a conta. Erros/timeouts não liberam dinheiro automaticamente. Usage efetivamente devolvido pelo provedor é guardado separadamente; `actual_cost`/`usage_priced_cost` são cálculos desse usage pela cotação fornecida, não faturas. Sem usage confiável, custo efetivo é desconhecido. O ledger inclui respostas recuperadas depois de crash.

Se o provedor informar tokens acima do bound, a autorização fica bloqueada para novas chamadas até revisão. Uma reserva local não garante o faturamento absoluto de um provedor externo. Não continuar após usage ausente na rodada; manter o custo como desconhecido e revisar o journal.

Execução futura exige simultaneamente: prévia já gravada e revisada, `--execute`, `--approved-plan-id`, `--authorization-reference`, `--budget`, limites de quantidade/tentativas, preços/bounds e lote A1 completo. A primeira tentativa de `--execute` sem prévia anterior grava a prévia e interrompe antes da rede. Isso é uma proteção técnica; nenhum desses passos foi executado live nesta entrega.

## Limitações e estado

A3 está tecnicamente homologada offline, incluindo recuperação, cache e limites. Qualidade real, tokenizer/bound operacional, cotação, desempenho live/uso real da API e comparação entre modelos continuam pendentes. O resultado é preparo para um piloto autorizado, não certificação de que um modelo barato já atende o produto. Ver [protocolo de qualidade](A3_AVALIACAO_QUALIDADE.md), [A4](A4_REVISAO_EDITORIAL.md) e [plano do piloto](PILOTO_DADOS_RECENTES.md).
