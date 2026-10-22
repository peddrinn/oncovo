# A1 — lotes incrementais locais

Implementação técnica offline, sem coleta real nesta entrega. A1 não aprova publicação, não resolve entidades e não acessa D1/LLM. A aquisição online continua opcional, exige autorização de fonte/método e não foi homologada contra Instagram real.

## Operação sem rede

```bash
# INPUT deve ser um JSONL raw já disponível/autorizado, não um arquivo editorial.
docker compose run --rm etl etl/lotes_incrementais.py \
  --input etl/raw/entrada_autorizada.jsonl \
  --store etl/raw/incremental --batch-id piloto_local_001 \
  --source arquivo_local --method jsonl-offline --authorization referencia_local \
  --profiles perfil_a perfil_b
```

Sem `--batch-id`, a referência é determinística pelo SHA-256 da entrada, versão e configuração de origem/método/autorização/perfis/janela. Uma referência explícita não pode ser reutilizada com outro conteúdo/configuração. Horário não participa da identidade de posts ou estabelecimentos. `started_at`/`finished_at` usam UTC com fuso.

`--window-start`/`--window-end` aceitam ISO com fuso e registram a janela **pretendida**; não fingem aplicar filtros de paginação que o adaptador não oferece. A ausência de janela ou de `taken_at` é explícita; quando `taken_at` existe, exige ISO com fuso. Adaptadores de outras plataformas exigem contrato próprio; esta versão aceita somente raw Instagram/export equivalente com `platform` omitido ou `instagram`.

## Arquivos e publicação do lote

```text
etl/raw/incremental/
  .lock
  pending/<batch_id>/          # nunca alimentar triagem a partir daqui
  batches/<batch_id>/          # somente lotes completos
    input.jsonl               # cópia exata, imutável durante retomada
    meta.json                 # identidade, parent e início
    chunk_00000000.json        # observações originais + offsets duráveis
    observations.jsonl        # chave, hash, perfis e novo/repetido/alterado
    catalog.jsonl             # snapshot lógico global, uma linha por post
    delta.jsonl               # novos/alterados, um registro por post
    manifest.json             # status, métricas, checkpoints e SHA-256
```

Não editar arquivos de `batches/`. Versões anteriores continuam em inputs/chunks de lotes anteriores. Um post reencontrado não apaga a observação anterior, mesmo quando sua legenda mudou. A versão lógica corrente é a última observação aceita; ordem de observação não comprova data de edição na origem nem autorização editorial.

O lock `flock` serializa escritores no mesmo store. Arquivos derivados são gravados em temporários, sincronizados e renomeados atomicamente. Chunks contíguos são o checkpoint autoritativo após interrupção; temporários incompletos são ignorados e recalculados. Ao terminar, a pasta sai de `pending/` para `batches/` por rename no mesmo filesystem. Não mover um lote em processamento entre filesystems. Ambiente suportado: Linux/WSL ou container Linux; `fcntl` não está disponível no Python Windows nativo.

`latest` é determinado pela sequência dos manifestos completos, não por mtime. Um lote pausado guarda seu parent. Se outro lote avançou a base, a retomada antiga falha: preservar pending e criar nova referência contra a nova base, sem rebase implícito. Checksums do parent e de replay completo são conferidos antes de consumo. A1 não cria banco operacional novo.

## Retomada e falhas

```bash
# Pausa controlada; não publica nada no store lógico.
docker compose run --rm etl etl/lotes_incrementais.py \
  --input etl/raw/entrada_autorizada.jsonl --batch-id ensaio_parcial --max-records 100
# Mesmos argumentos de identidade, sem limite: retoma os chunks persistidos.
docker compose run --rm etl etl/lotes_incrementais.py \
  --input etl/raw/entrada_autorizada.jsonl --batch-id ensaio_parcial
```

`partial` tem `finished_at=null`; nenhum checkpoint remoto avança. `failed` preserva a entrada inválida e não publica o catálogo, mesmo que outras linhas sejam válidas. JSON inválido, objeto inválido, code inválido, encoding inválido, timestamp sem fuso ou registro sem newline final bloqueiam promoção integral. A linha sem newline final é tratada conservadoramente como possível gravação interrompida, inclusive quando seu JSON isolado seria válido. Corrigir/reexportar para **outro arquivo/lote**, preservando a evidência; não concatenar fragmentos nem descartar linhas silenciosamente.

Checkpoints por perfil registram observações, última linha física e maior `taken_at` observado. São offsets de arquivo, **não** cursores de API nem prova de cobertura integral da fonte. Um perfil sem observações permanece com contagem zero. Aquisições com sidecar `.acquisition.json` parcial/falho não podem ser importadas como completas.

Repetir um lote completo verifica hashes e retorna o mesmo manifesto sem escrita. Não reexecute extração/publicação por esse retorno: consulte a evidência do estágio já concluído por batch_id. Novo lote contendo somente posts conhecidos gera delta vazio; descoberta de outro perfil altera proveniência, sem nova entrada LLM.

## Deduplicação, versões e contratos

- Chave lógica: `instagram:code`, global entre perfis. Não usa perfil nem horário como identidade.
- `_source_profiles`: lista cumulativa ordenada de perfis consultados; `_profile_username`: representante determinístico para compatibilidade. `user.username` continua sendo o autor; `coauthor_producers` são colaboradores.
- `_content_hash`: SHA-256 de code, legenda, taken_at, autor, coautores, localização, tipo/produto, resources e usertags. Contadores de engajamento e horário de captura não disparam extração. Mudança de campos incluídos produz revisão rastreável; não aprova o conteúdo.
- `received`: observações não vazias, incluindo inválidas; `new`, `duplicates`, `changed` contam observações válidas. Um post pode ter múltiplas revisões no lote, mas só uma linha final em delta.
- `invalid`, `blank`, `discarded` registram bloqueios de ingestão. `discarded` aqui significa inválidos, não julgamento editorial.
- `eligible_delta` conta posts novos/alterados detectados. `to_triage` conta linhas disponibilizadas no delta **completo** (zero se o lote falhar); a triagem tem relatório próprio de efetivamente mantidos/descartados/priorizados. Não chamar esse valor de número de chamadas pagas.

Triagem avançada e simples preservam a lista cumulativa. Para um lote completo:

```bash
docker compose run --rm etl etl/triagem_avancada.py \
  --input etl/raw/incremental/batches/piloto_local_001/delta.jsonl \
  --outdir etl/processed/piloto_local_001
# Somente prévia: não chamar Maritaca nesta fase.
docker compose run --rm etl etl/extrair_llm.py \
  --input etl/processed/piloto_local_001/dia1_fila_llm_100.jsonl
```

`extrair_llm.py` mantém o contrato existente (`post_code`, legenda limpa, source_profile, autor, localização e coautores). Não foi alterado. Seu cache legado é por post_code: para posts **alterados**, planejar revisão/extração por lote e hash em arquivo separado, nunca reutilizar extração antiga como se comprovasse o conteúdo novo. Retentativas pagas e cache global por versão ficam para A3, com autorização própria. Nada nesta implementação chama LLM nem substitui o prompt.

A2 recebe cards preparados/editorialmente aprovados, não raw. Reusar registry revisada fixa os IDs mesmo com fonte primária nova; filiais, nomes ambíguos e ocorrências distintas permanecem separadas. Ausência em lote parcial não retira post da base global nem estabelecimento do D1. A5 só propõe ocultação por mapeamento auditável e exige decisão humana real fora das fixtures.

## Adaptador Instagram opcional

O adaptador legado foi preservado. Prévia não importa cliente nem faz login. Execução futura exige `--execute` e `--authorization-reference`, além das credenciais externas ao código e uma autorização real específica. O texto de referência é rastreabilidade, não comprovação automática de permissão.

Cada aquisição usa novo arquivo raw e sidecar com início/fim, configuração e status por perfil. `--resume` continua aquisição parcial/falha usando os mesmos perfis/limite/autorização, sem repetir perfis completos. Perfil interrompido pode ser consultado novamente com sobreposição; as observações anteriores permanecem e A1 deduplica globalmente. Arquivo truncado bloqueia append. Aquisição completa não recebe append; novo ciclo usa outro arquivo. Só após todas as consultas previstas terminarem é feita a ingestão A1.

Não há bypass, rotação de proxies, solução de desafios ou retries de bloqueio. O método legado faz requisição limitada aos itens recentes (`max-per-profile`), sem prometer janela completa ou paginação persistida da plataforma. O ensaio do adaptador usa exclusivamente cliente falso. Validar o método e acesso reais exige autorização posterior.

## Reprodução de homologação

```bash
docker compose run --rm etl -m unittest discover -s tests -v
docker compose run --rm etl -m unittest discover -s tests -p test_a1_incremental.py -v
# Offline com escala, saída NOVA (não reutilizar pasta de evidência):
docker compose run --rm etl etl/homologar_a1.py --outdir etl/output/a1_ensaio_novo --scale
# No host Linux/WSL com Python3 e Docker; persistência nova obrigatória:
python3 etl/homologar_a1.py --outdir db/reconciliation/a1_ensaio_novo --wrangler
```

O ensaio Wrangler usa `.wrangler/a1_<nome_da_saida>/state`; recusa persistência existente. Todas as chamadas usam `--local`, com configuração do projeto, e nunca `.wrangler/state` para escrita. O backup sintético é feito com one-offs encerrados; restauração ocorre em outra pasta. O script não escreve no catálogo principal nem promove registry real.

## Piloto posterior — sujeito a autorização

Proposta: 160 observações recentes em dois lotes de 80; 60 gastronomia, 40 lazer/experiências, 40 agendas culturais/eventos e 20 equipamentos culturais/espaços públicos. Selecionar fontes com direito de acesso/reutilização comprovado: exports fornecidos pelos titulares, feeds/datasets oficialmente licenciados ou API permitida. Instagram somente se fonte e método forem explicitamente autorizados. Não baixar fontes novas nesta entrega.

Janela proposta: lugares nos últimos 60 dias e agendas nos últimos 21 dias, com ocorrências futuras concretas. Triagem separa eventos vencidos, promoções e recorrências ambíguas. Variar bairros e tipos de estabelecimento; registrar lacunas em vez de preencher com inferências. Não confundir quantidade de posts com estabelecimentos únicos.

Antes de qualquer gasto: deduplicar por post/hash contra o store; aplicar triagem; selecionar amostra de 10–20 candidatos para avaliação A3 autorizada; estimar custo pelo número de revisões inéditas elegíveis e preço vigente do provedor, com teto aprovado pelo usuário. Não há preço ou custo real medido nesta execução.

Medir por fonte: proporção útil após revisão, endereço/datas comprovados, novos lugares únicos, fontes vinculadas a entidades existentes, candidatos por 100 posts, conflitos, duplicatas, alterações e custo por entidade nova aprovada. Revisão humana cobre unidade física, autor/fonte, datas, atualidade, preço e toda fusão/ocultação. Guardar falsos positivos e falsos negativos observados.

Aumentar volume só após os dois lotes sem corrupção/perda, IDs estáveis, custo dentro do teto aprovado e fila de revisão compatível com a capacidade editorial. A simulação indicou que candidatos podem crescer rapidamente com nomes semelhantes; não automatizar sua aprovação nem assumir rendimento real a partir de fixtures.

## Continuação A3/A4 — 22/10/2026

A pendência A3 de cache legado por post_code foi tratada: request_id agora depende da entrada efetivamente enviada/prompt/modelo/parâmetros/contrato. Ranking e perfil de descoberta continuam na auditoria, mas foram excluídos da mensagem para não invalidar cache sem mudança factual. Fonte nova sem alteração do conteúdo enviado não exige outra inferência. Alteração real produz nova versão e invalida a aprovação A4 antiga para essa evidência. Extrações históricas sem hashes/modelo verificáveis ficam legacy_unverified.

Prévia, custos/bounds e opt-in estão em [A3_EXTRACAO_VERSIONADA.md](A3_EXTRACAO_VERSIONADA.md). Isso supera as observações anteriores sobre cache apenas por post_code para o caminho novo, sem presumir migração automática do histórico. A integração foi homologada com respostas sintéticas e D1 isolado; aquisição e Maritaca live continuam sem autorização.
