# Registro de decisões — Oncovô?

Última revisão: 21/10/2026. Este documento separa **decisões de produto já discutidas**, **decisões técnicas desta integração** e **hipóteses ainda não validadas**. Mudar uma decisão exige adicionar registro com data, contexto, alternativas, consequência e teste afetado; não apagar o histórico.

## Decisões vigentes (MVP)

| ID | Estado | Decisão e justificativa | Consequência / reavaliação |
|---|---|---|---|
| D-001 | Mantida | Produto inicial = busca de lugares e eventos em Belo Horizonte, não chatbot. | Medir qualidade da busca e cliques; não pagar LLM em cada consulta. |
| D-002 | Mantida | Frontend estático Astro + Tailwind + TypeScript. | SEO técnico simples, carregamento rápido, cards responsivos. |
| D-003 | Mantida | Cloudflare Worker + D1 como runtime planejado. | D1 atrás da API; sem exposição do arquivo bruto para download no frontend. |
| D-004 | Mantida | Sem login, Keycloak, Flowise, PostgreSQL, Pinecone ou Meilisearch no MVP. | Reduz implantação, segurança operacional e custos. |
| D-005 | Mantida | Cards mostram título, tipo, bairro, data se evento, preço, tags, fonte e mapa quando possível. | Sem página individual obrigatória. |
| D-006 | Mantida | LLM apenas no ETL offline; extrações seguem revisão editorial. | Economia previsível e controle de risco. |
| D-007 | Mantida | Promoções ocultas; evento precisa data válida e não expirada; recorrência sem ocorrência inequívoca fica em revisão. | Não publicar evento vencido. |
| D-008 | Mantida | Quatro estados: published, review, expired, hidden; baixa confiança/contradições não são aprovadas automaticamente. | Confiança mínima 0,75 + outras regras. |
| D-009 | Mantida | IDs determinísticos por plataforma + post_code; fonte original recuperada por post_code. | Não pedir post_url ao LLM, mas preservá-la no banco como link derivado. |
| D-010 | Mantida | Base tratada localmente em Python, publicada via seed SQL idempotente. | Preservar trilha editorial. |
| D-011 | Mantida | Primeiro validar MVP local, depois soft launch, só então roadmap extenso. | Lançamento não depende de monetização. |

## Novas decisões da integração do legado — 21/10/2026

### D-012 — Identidade visual original recuperada (aceita)
**Contexto:** A primeira home usava fundo amber-50, cores quentes, logo vermelha central, input laranja-claro e tratamento coloquial (“Qual rolê tá procurando em BH?”). O usuário deseja mantê-la.
**Decisão:** Usar a arte horizontal transparente antiga em `web/public/logo.png` e preservar o quadrado legado como backup, além da paleta, acrescentando apenas cards exploratórios e melhoria de cards de resultados, sem alterar o modelo de busca.
**Alternativa rejeitada:** identidade visual genérica de dashboard em tons de azul. **Teste:** revisão visual em celular e desktop.

### D-013 — Docker como envelope de desenvolvimento, não como infraestrutura pública (aceita; integração Docker pendente de execução)
**Contexto:** Antes de criar/configurar nova conta Cloudflare, todo o produto deve funcionar no computador do desenvolvedor.
**Decisão:** Docker Compose com API Wrangler/Miniflare, web Astro e ETL Python; serviço de coleta opcional, separado. D1 é emulado pelo próprio Wrangler; `.wrangler/state` é persistido localmente.
**Alternativa rejeitada:** subir Postgres/SQLite separado que divergiria do D1. **Teste:** `docs/DOCKER_LOCAL.md` e `python scripts/smoke_local.py`.

### D-014 — Recuperar triagem rica do Dia 1 (aceita)
**Contexto:** O código histórico possuía pesos por fonte, classificação heurística, deduplicação por code, hashes de legenda e auditoria CSV, ausentes na triagem simplificada.
**Decisão:** `etl/triagem_avancada.py` portado a partir de `dia1_higienizacao_triagem.py`, com referência temporal dinâmica; manter `etl/triagem.py` como alternativa leve. **Limitação:** heurísticas por palavras não são verdade absoluta; precisam de conferência.

### D-015 — Recuperar prompt Maritaca rigoroso e mantê-lo versionado (aceita; revalidação da API pendente)
**Contexto:** O teste histórico distingue especificamente horário de evento, funcionamento, promoção, obrigações de ingresso e evidências.
**Decisão:** `etl/prompts/maritaca_legacy_v2.txt` reaproveita as instruções de extração; `etl/extrair_llm.py` faz dry-run por padrão, injeta post_code e post_url localmente e exige validação pós-LLM.
**Tradeoff:** prompt mais longo = maior custo por post. **Teste futuro:** amostra estratificada real, validação qualitativa e preço por 100 posts antes de rodar o lote completo.

### D-016 — Coleta Instagram manual e isolada (aceita com ressalvas)
**Contexto:** O código histórico usava Instagrapi/Hiker com credenciais em texto simples. O novo serviço de coleta não deve executar automaticamente.
**Decisão:** `etl/instagram_collect.py` usa variável de ambiente, limite baixo por perfil e `--execute`; depende de `instagrapi` opcional, sem bypass de bloqueios. Preferir fontes autorizadas / APIs oficiais; verificar termos e direitos antes de usar.
**Consequência:** Não integrar coleta à imagem pública/Worker. **Teste externo obrigatório:** autenticação, permissões e contrato da biblioteca em ambiente controlado.

### D-017 — Segredos antigos não migram (aceita — ação humana urgente)
**Contexto:** Arquivo `.env` e scripts legados possuem credenciais/possíveis tokens expostos no ZIP.
**Decisão:** Não incluir nada disso no pacote; colocar `.env` e armazenamento de sessões no `.gitignore`; nunca realizar login durante teste unitário.
**Consequência:** Rotacionar os segredos ainda ativos e revisar eventual histórico Git antes de publicar o legado em outro repositório.

### D-018 — Aprovação editorial explícita (aceita)
**Contexto:** Extração correta não implica lugar ativo nem evento vigente.
**Decisão:** `etl/criar_revisao.py` cria novos itens sempre com `publish_status=review`; pessoa confere antes de alterar para `published`. Publicador não promove registros em revisão.

### D-019 — Banco não destrutivo e despublicação cuidadosa (aceita com operação manual)
**Contexto:** DROP/DELETE geral prejudicam histórico, mas UPSERT sozinho mantém itens previamente publicados que foram removidos da última exportação.
**Decisão:** schema `CREATE TABLE IF NOT EXISTS`, UPSERT por ID, expiração no Worker; desativação de lugares antigos deve ser explícita via revisão/migração, nunca inferida de uma amostra parcial. **Pendente P0 para manutenção contínua:** fluxo revisado de despublicação de locais encerrados.

### D-020 — Separação entre simulação local e conta Cloudflare (aceita)
**Contexto:** O repositório trazia um `database_id` de uma conta anterior, mas a conta definitiva será configurada depois.
**Decisão:** Usar ID fictício de D1 no template `wrangler.toml` para desenvolvimento local; substituir pelo UUID da conta nova antes de qualquer comando `--remote`. **Teste:** nunca executar comando remoto durante setup local.

### D-021 — Fontes e dados privados não entram no ZIP de distribuição (aceita)
**Contexto:** ZIP legado ~108 MB contém `.venv`, `.git`, dumps de dados e conteúdo não necessário para execução.
**Decisão:** Entregar apenas código revisado, assets selecionados, dados editoriais já existentes no repo, testes, exemplos e documentação. Histórico completo do scraping fica local em `etl/raw/`, ignorado pelo Git.

<!-- Frente A A0/A2 22-10-2026 -->
## Frente A — Decisões A0/A2 — 22/10/2026

### D-022 — Dedupe por entidade física, preservando o dedupe de post (aceita para homologação)
**Contexto:** `preparar_publicacao.py` cria `id` por `instagram:post_code`; UPSERT preserva identidade da postagem, não do estabelecimento. `B-008` estava em aberto.
**Alternativas:** (1) mudar diretamente PK/schema do D1; (2) resolver offline, manter `search_items` e mapear fontes; (3) continuar dedupe por post.
**Decisão:** adotar (2). Introduzir `etl/resolver_entidades.py` após `preparar_publicacao.py`: fusão automática só com mesmo nome/cidade/endereço exato com logradouro + número (unidade incluída); similaridade gera candidatos para revisão. Eventos só se fundem com nome/local/datas e horários exatos. Sem endereço comprovado, não fundir automaticamente.
**Consequências:** saída canônica temporária e `source_entity_map.csv` com múltiplas fontes; não muda `/api/search`, Worker nem schema D1. `D-009` permanece correto para identidade do **post**, mas é substituído como critério de identidade do **card**. Filiais e ocorrências permanecem separadas.
**Critério de teste:** regressões sintéticas de fusão, filiais, eventos distintos, rejeição e casos ambíguos; testes sem coleta/LLM.
**Depende de:** D-007, D-008, D-018; fecha parcialmente B-008, pendente promoção para D1 em A5.

### D-023 — IDs estáveis e override humano versionado (aceita para homologação)
**Contexto:** alterar a fonte primária ou reprocessar novos posts poderia alterar a PK de um card e quebrar resultados já armazenados.
**Alternativas:** recalcular PK em todo lote; migrar schema D1 imediatamente; fixar mapeamento offline por `entity_id` e `card_id`.
**Decisão:** registro `etl/entity_registry.json` preserva identidades aprovadas; o resolvedor gera apenas `entity_registry.proposed.json`. `etl/entity_overrides.json` exige motivo/revisor/data para fusões; rejeições explícitas impedem fusão automática. Conflitos de identidades já fixadas encerram o processo sem publicação.
**Consequências:** mudanças de ID exigem revisão de `source_entity_map.csv` e reconciliação D1 antes de produção. Fonte primária pode mudar sem renumerar a entidade.
**Critério de teste:** reordenação de lote, adição incremental, execução parcial, rejeição explícita e divergência de registro.
**Depende de:** D-019; implementação de reconciliação segura fica em A5.

### D-024 — Não alterar runtime e não despublicar na A2 (aceita)
**Contexto:** a branch `main` corresponde ao commit-base `67981bdd` e o Docker/D1 local foi validado manualmente pelo desenvolvedor. A base de teste não é atual.
**Alternativas:** adicionar tabela de fontes e migração D1 agora; aplicar automaticamente seed canônico; gerar staging separado e validar.
**Decisão:** apenas staging offline e documentação de integração com Frente B, sem mudanças em `db/schema.sql`, `db/seed.sql`, Worker, URLs ou prompt Maritaca. Não inferir despublicação a partir de lotes parciais. O seed atual mantém UPSERT, mas NÃO retira IDs antigos após fusões; tratar isso em A5 mediante diff revisado, backup e SQL reversível.
**Consequências:** deduplicação **não é declarada implantada em produção** nesta fase. Os IDs/remoções devem ser auditados antes de qualquer seed no D1. O catálogo antigo não comprova operação atual de estabelecimentos.
**Critério de teste:** o novo resolvedor não executa SQL ou chamadas externas; gerar CSV/JSONL e comparar contrato de colunas do seed. Docker/Wrangler local será revalidado no ambiente com Docker.
**Substitui/atualiza:** D-013 (status de Docker: manual validado em 22/10/2026; não equivale a CI completo), D-019 (reconciliação continua pendente), B-001 (parte de Docker local manual satisfeita, falta teste automatizado).

### D-025 — Bloqueio explícito de publicação por risco temporal/editorial (mantida e ampliada)
**Contexto:** o estágio canônico não deve recuperar eventos expirados nem elevar automaticamente itens `review`, `hidden` ou promoções.
**Alternativas:** confiar apenas no arquivo final anterior; revalidar status e ISO com fuso no resolvedor.
**Decisão:** a nova etapa aceita só `published` de tipo `place`/`event`, e revalida data/hora e término de eventos com timezone. Fusão não constitui aprovação editorial; local ativo deve ser rechecado antes do lançamento.
**Consequências:** execução antiga ou incompleta não faz novos cards aparecerem; o seed de publicação mantém gate editorial.
**Critério de teste:** entradas expiradas, status review/hidden, promoção e datas inválidas não saem no catálogo canônico.
**Depende de:** D-007 e D-008; mantém confiança mínima 0,75 na etapa editorial existente.

### D-026 — Integridade estrita de JSONL como pré-condição do ETL (aceita)
**Contexto:** legendas reais podem conter `U+2028` dentro das strings JSON. Na auditoria, `str.splitlines()` gerou um falso positivo de corrupção de arquivo, enquanto leitura estrita por `\n` confirmou 1.170 registros brutos e 100 extrações válidas. O raw possui 4 códigos repetidos; arquivos futuros também podem apresentar JSON inválido.
**Alternativas:** ignorar linhas inválidas; tentar reconstruir legendas por concatenação heurística; validar e bloquear o lote para recuperação auditada.
**Decisão:** adotar validação prévia estrita em `etl/auditar_jsonl.py`, com contagem de linhas físicas, objetos válidos, chaves ausentes/duplicadas, SHA-256 do arquivo e resumo sem conteúdo privado. JSON inválido e chave ausente bloqueiam; `code` repetido em raw é apenas reportado para dedupe na triagem, enquanto duplicata em etapas deduplicadas bloqueia. Recuperação/re-exportação é procedimento separado sob revisão, não automática.
**Consequências:** cópias históricas foram confirmadas como íntegras e não exigem reparo; `U+2028` dentro da legenda deve ser preservado. Duplicatas são auditadas sem eliminar evidências do raw. No MVP, manter `read_jsonl()` existente estrito.
**Critério de teste:** linhas realmente corrompidas, chaves ausentes, duplicatas após triagem e não-objetos causam erro e relatório; duplicatas raw são auditadas sem bloquear; arquivo íntegro com `U+2028` passa.
**Depende de:** A0; não modifica o coletor já existente.


## Itens não decididos / condições para publicar

- **B-001 (P0):** testar `docker compose build`, `docker compose up`, init/seed D1 e busca na máquina do projeto; Docker não disponível no ambiente de montagem do pacote.
- **B-002 (P0):** confirmar quais estabelecimentos dos 13 itens antigos estão ativos; nenhum foi revalidado externamente.
- **B-003 (P0):** trocar o placeholder de D1 pelo novo ID Cloudflare, configurar origens reais e domínio, testar Worker/Pages antes do público.
- **B-004 (P0):** obter dados de eventos atuais com consentimento/fonte adequada, verificar datas e publicar via revisão.
- **B-005 (P0):** preencher contato institucional e revisar documentos de privacidade/termos.
- **B-006 (P1):** decidir métrica de buscas sem resultado e cliques, observando LGPD/minimização de coleta.
- **B-007 (P1):** executar benchmark para decidir se FTS5, busca dedicada ou apenas sinônimos/LIKE servem melhor; evitar comprometer custo/latência por suposição.
- **B-008 (P1):** desenhar resolução de entidade (vários posts do mesmo estabelecimento) separada do dedupe por `post_code`.

## Como registrar uma nova decisão

Use `D-022 — Título (proposta/aceita/substituída)`, `Data`, `Contexto`, `Alternativas`, `Decisão`, `Consequências`, `Critério de teste` e `Substitui/depende de` quando aplicável.

<!-- Frente A A2.1 homologação histórica 22-10-2026 -->
## Frente A — Decisões A2.1 (homologação e reconciliação) — 22/10/2026

### D-027 — Candidatos por endereço coincidente, sem fusão automática (aceita para homologação)
**Contexto:** nos 13 cards historicamente elegíveis, `SPACE FRIENDS` e `Space Friends Park` compartilham o endereço informado Rua Catumbi, 390, mas o limiar de similaridade de nomes (0,84) não os sinalizava (similaridade ~0,839). Compartilhar endereço não prova que seja o mesmo negócio; lojas/atividades diferentes podem coexistir no mesmo prédio.
**Alternativas:** abaixar limiar geral; unir por endereço; criar motivo de revisão separado para coincidência de endereço.
**Decisão:** manter a fusão por assinatura forte (nome + endereço com logradouro e número + cidade, quando idênticos), e acrescentar `candidate_basis=same_full_address` aos pares não fundidos com mesmo endereço normalizado completo/cidade, mesmo se nomes diferentes. Um candidato jamais vira fusão sem evidência editorial.
**Consequência:** aumenta sensibilidade da fila manual sem ampliar falsos merges automáticos. Salas/lojas distintas são preservadas; grandes edifícios podem produzir mais candidatos que exigem triagem.
**Teste:** `tests/test_a2_homologacao.py`, casos de marca diferente no mesmo endereço e diferentes números de unidade.
**Depende de:** D-022, D-023.

### D-028 — Reconciliação explicitamente proposta e não executada (aceita)
**Contexto:** o pipeline histórico produz 13 cards elegíveis; o resolvedor agrupa dois posts de Pescados da Esquina em um card, resultando em 12 entidades. O UPSERT canônico isolado não esconde o ID antigo `6c4ca31679b544b260f84863` caso ele já exista na base anterior.
**Alternativas:** `DELETE` integral, esconder registros ausentes de lote parcial, migrar PK do D1, ou produzir diff auditável por fonte.
**Decisão:** criar `etl/auditar_reconciliacao.py` que cruza snapshot anterior + catálogo canônico + `source_entity_map.csv`, valida fonte/ID/tipo e produz apenas `reconciliation_review.csv` e relatório com hashes SHA-256. Não gera SQL, não altera D1 e não trata itens ausentes do lote como despublicação.
**Consequência:** despublicação de cards fundidos só após confirmação de origem e aprovação humana, comparação com o estado D1 real, backup e plano de reversão. A A5 ainda precisa do executor SQL condicionado a esse gate.
**Teste:** duplicata proposta, fonte divergente bloqueada, lote parcial sem ocultação e seed idempotente que mantém o card antigo publicado.
**Depende de:** D-019, D-024; trabalho A5 pendente.

### D-029 — Amostra histórica nunca é prova de atualidade nem de estado do D1 (mantida e explicitada)
**Contexto:** em 22/10/2026, a reprodução offline com os 100 registros editoriais e 100 extrações históricas resultou em 13 cards elegíveis e 12 entidades canônicas; são 0 eventos elegíveis. Há uma fusão segura por nome+endereço e um par suspeito para revisão. A validação Docker no computador do projeto foi confirmada pelo usuário, mas não foi repetida nesta sessão.
**Decisão:** relatórios desta etapa são de homologação, não instruções de publicar. Manter `entity_registry.proposed.json` separado da registry aprovada. Antes de qualquer atualização pública, revalidar lugares/ocorrências e comparar com um snapshot real do D1 de homologação, nunca usar simplesmente o catálogo histórico como snapshot remoto.
**Critério de teste:** relatórios sinalizam `publish_ready=false`; nenhuma ação remota/externa nesta etapa.
**Depende de:** D-024, D-025; mantém A1/A3/A4/A5/A6 sob seus respectivos gates.
