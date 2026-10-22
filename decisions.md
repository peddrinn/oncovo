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
