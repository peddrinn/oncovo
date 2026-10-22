# Auditoria técnica da primeira versão do Oncovô? — 21/10/2026

**Fontes examinadas:** ZIP `oncovo_primeira_versao(1).zip` enviado pelo usuário; repositório atual `peddrinn/oncovo` (branch main) e arquivos do pacote de 20/10/2026. Este relatório analisa **código autoral, configuração, assets e estruturas de dados** por arquivo/família funcional. Não audita individualmente os ~11 mil arquivos de bibliotecas terceiras e diretórios `.venv`/`.git` contidos no ZIP; isso exigiria auditoria de dependências separada.

## 1. Diagnóstico

O ZIP antigo tem 10.924 entradas e aproximadamente 495 MB descomprimidos, dos quais grande parte é ambiente virtual/depósitos Git/bibliotecas. **Não é apropriado copiar a árvore inteira para o repo novo.** A arquitetura antiga contém dois produtos misturados: (1) descobertas locais com ETL e (2) chatbot com Flowise, autenticação, pagamento/doações e componentes vetoriais. O segundo é desnecessário ao MVP decidido.

A aparência da antiga `flowise-api-frontend/oncovo-front/public/index.html` tem três elementos visualmente bons: **logo vermelha central**, **fundo `bg-amber-50`** e **caixa de busca `bg-orange-50`**, combinados com botão vermelho. A implementação antiga inseria login Keycloak/Google/Facebook e retornava textos via chatbot; essas partes não são reaproveitadas. O catálogo de cards do MVP atual é melhor para validar consultas rápidas.

## 2. Arquivos e subcomponentes — veredito

| Origem antiga | Evidência e avaliação | Decisão / arquivo moderno |
|---|---|---|
| `flowise-api-frontend/oncovo-front/public/index.html` | Home com paleta âmbar/vermelho, logo, formulário simples e autenticação | **Design recuperado**, fluxo refeito em `web/src/pages/index.astro`; login removido. |
| `public/images/logo1.png`, `public/logo.png` | Marca vermelha “ONCOVÔ?”; mesma identidade utilizada na versão nova | **Promover `images/logo1.png` para `web/public/logo.png`** (arte horizontal transparente, sem borda branca); preservar o logo quadrado anterior apenas como `logo-legado-quadrado.png`. |
| `public/animacao.css` | Animação de digitação e tipografia Nefelibata Sans sem arquivo de fonte fornecido | **Não copiar** animação; usar indicadores de estado acessíveis e fontes do sistema. |
| `public/app.js` | Faz requisição POST da mensagem para backend chatbot e processa HTML de retorno | **Substituído** pela busca GET `/api/search` e cards criados com `textContent` (contra injeção de HTML). |
| `public/contato.html` | Página extensa com “ajude-nos”, Pix, preços/planos e formulários/links antigos | **Não publicar como está**; afirmações institucionais/financeiras exigem confirmação. Usar `sobre/`, `privacidade/`, `termos/` atuais. |
| `oncovo-front/index.js`, `controllers/flowise.js`, `package.json` | Express/integração Flowise, camadas de autenticação | **Arquivar**; runtime passa a Worker read-only. |
| `flowise-api-frontend/.git`, `oncovo-front/node_modules` | Histórico Git e dependências locais | **Excluir** de distribuição e do repositório. |
| `docker-compose.yml` da raiz antiga | Define runtime Flowise com configuração de ambiente legado | **Substituir** por Compose local de API, web e ETL. |
| `dados/docker-compose.yml` | Infra de banco relacional histórico | **Não incluir** Postgres no MVP D1. |
| `auth-manage/docker-compose.yml` e `auth-manage/keycloak-compose/*` | Keycloak e observabilidade de autenticação | **Não usar** sem contas de usuários. |
| `sql-record-manager/Dockerfile` | Gerenciamento de documentos para pipeline antigo | **Não usar** no catálogo SQL MVP. |
| `llm.py`, `send_vector_data.py` | Modelos/integração com agentes ou vetor/Flowise | **Retirar runtime**; não trazer Pinecone/Flowise. |
| `dados/insta_content/insta_collector.py` | Lista de perfis, login Instagrapi, coleta e gravação por perfil/geral; continha credencial embutida | **Reescrito** em `etl/instagram_collect.py` com env, `--execute`, JSONL e limites; proibido migrar credencial. |
| `dados/insta_content/scrap_free.py` | Serializa modelos Pydantic v1/v2 e guarda `_profile_username`, `_scraped_at` | **Lógica recuperada** no coletor, com preservação da origem e dedupe. |
| `dados/insta_content/scrap_hiker.py` | Tentativa HikerAPI + Instagrapi, código exploratório e credencial embutida | **Descartar como ferramenta ativa**; revisar/rotacionar tokens antigos. |
| `dados/insta_content/data_clean.py` | Normalização com Pandas/pytz e formatos próprios do legado | **Não migrar** como dependência; regras necessárias implementadas com stdlib Python. |
| `dados/insta_content/storage.py`, `insert_info_banco.py` | Carga para PostgreSQL via credenciais históricas | **Substituir** pelo `gerar_seed.py` e D1 local; não copiar credenciais. |
| `dados/insta_content/normalizar_dados.py`, `processa_infos.py` | Transformações exploratórias para entidades/classes | **Referência futura** para normalização/entity resolution; manter fora da publicação para reduzir acoplamento. |
| `processa_categorias.py`, `associa_cat_subcat.py`, `otimizacao_labels.py` | Pipelines de taxonomia/tags e associação categoria/subcategoria | **Aguardar** validação de dados/ranking. Taxonomia complexa foi prematura no MVP. |
| `lista_cat.json`, `subcat*.json`, `tags_*.json`, `categorias_atualizadas.json`, `link_cat_subcat*.json` | Vocabulários históricos de rótulos com possíveis duplicatas/inconsistências | **Não copiar em produção**; revisar licenças, normalização e necessidade de cada rótulo antes de introduzir tabelas. |
| `dados/insta_content/arquivos/raw/dia1_higienizacao_triagem.py` | **Melhor script legado de limpeza:** dedupe por code e legenda, separa perfis/autores, calcula scores/filas, CSV de auditoria | **Portado** para `etl/triagem_avancada.py`, corrige data fixa `2026-06-20` e dependência externa. |
| `dados/insta_content/arquivos/raw/teste_maritaca_10_api.py` | **Prompt histórico rigoroso e amostra estratificada:** evidências, nullable, datas relativas, conflitos de ingresso, promoção versus evento | **Portar especificação** para `etl/prompts/maritaca_legacy_v2.txt` e `etl/validacao_extracao.py`; sem herdar `post_code`/`post_url` redundantes na saída. |
| `dados/insta_content/arquivos/raw/transformacao_produto.py` | Gera status/título/subtítulo/busca; porém produz datas do tipo `04/07 às 14:00` e usa horário de abertura em `starts_at` de locais | **Não executar no MVP**; `preparar_publicacao.py` gera ISO com fuso e recusa datas ambíguas. |
| `dados/insta_content/arquivos/raw/outputs_dia1/*` e `clean_data/*` | Saídas de execução e dados derivados | **Não versionar**; gerar novamente em `etl/processed/`. |
| `dados/insta_content/ETL_pipeline.txt` | Descreve orquestração histórica em alto nível | **Substituído** por `docs/ETL_OPERACAO.md` e `decisions.md`. |
| `Relatorio Projeto Oncovo.txt`, `to-do.md`, `arquitetura`, `database_modeling.drawio`, `info` | Registros históricos úteis, mas representam múltiplas fases e hipóteses técnicas | **Preservar no acervo histórico do usuário**, não usar como especificação normativa do MVP. |
| `.env`, `.venv`, `.venv-1`, qualquer sessão de login | Credenciais, dependências ou dados de máquina presentes no ZIP | **Não migrar e não publicar**. Rotacionar senhas/tokens válidos, mesmo que o arquivo nunca tenha sido commitado. |

## 3. ETL: riscos recuperados versus melhorias

### Coleta
Anterior: login automatizado com usuário/senha literais, captura indiscriminada e pouca governança de execução. Novo: `--execute`, limites por perfil, saída JSONL, indicação explícita do método opcional e tratamento de segredos. **Não significa** que Instagrapi esteja autorizado pela plataforma: avaliar métodos permitidos é responsabilidade operacional.

### Higienização
Anterior: algoritmo muito bom em `dia1_higienizacao_triagem.py`, com `CURRENT_DATE` fixo. Atual: algoritmo recuperado, referência temporal dinâmica, stdout auditável, dados brutos locais e separação clara entre triagem heurística e verdade editorial. Executado sobre `all_posts.jsonl` previamente fornecido: **1.170 posts, 1.166 códigos únicos, 4 descartes por dedupe de código, 837 registros mantidos na fila limpa e 100 priorizados**. Isso **não** significa 837 locais publicáveis. No reprocessamento editorial de 21/10/2026, com a regra de que `partial` pede revisão, os 100 itens ficaram em **13 published, 38 review, 41 expired, 8 hidden**; o resumo de 20/10 tinha 32 review e 14 hidden por uma regra diferente.

### LLM
Anterior: prompt longo, mas com requisitos de evidência e análise de contradições; versão nova simplificada era mais curta porém perdia detalhes. Atual: recupera conteúdo rigoroso, remove dois identificadores redundantes da saída, grava versão do prompt, preserva os controles de revisão. Ainda requer novo benchmark externo; não declare melhoria de qualidade ou redução monetária sem medir.

### Produto
Anterior: a transformação convertia datas e horas para strings amigáveis, impróprias para SQL/expiração. Atual: apenas eventos com data ISO confiável entram como `published`; lugares jamais recebem `starts_at`; promoções ficam `hidden`. Revisão humana para mudança de status.

## 4. Segurança e dependências

1. **Alta gravidade:** no ZIP há `.env` e código legado com credenciais/tokens escritos no próprio fonte, além de bibliotecas antigas. Não foram transportados para esta entrega. Se reais/ainda ativos, **revogue/rotacione** senhas e chaves (Instagram, Hiker e serviços relacionados) antes de reutilizar qualquer instalação.
2. **Alta gravidade:** não inclua `.git`, `.venv`, `node_modules`, bancos/SQLite, logs ou dados brutos em commits. `.gitignore` protege novas mudanças mas **não remove histórico já publicado**; reveja `git ls-files` e eventualmente histórico se necessário.
3. **Média:** a coleta de conteúdo de terceiros envolve termos de serviço, direitos autorais, retenção e transparência. Exiba metadados mínimos e links; evite publicar legendas inteiras e dados pessoais desnecessários.
4. **Média:** a API pública não aceita inserções e usa SQL parametrizado. Restrição por `Origin` é medida de navegador, **não autenticação da API**; rate limiting/bot management ficam como fase posterior se houver abuso.
5. **Média:** a base histórica de junho de 2026 pode ter lugares desativados. Não publicar até revisão de existência e endereço atuais.

## 5. Avaliação do repositório atual e mudanças propostas

O repositório atual já contém Worker, API de busca, schema não destrutivo, prompt simplificado, preparação para publicar e home Astro. Portanto este pacote atua como **evolução pontual**: adiciona Docker Compose, três Dockerfiles + coletor isolado, recupera a triagem elaborada e as validações do prompt, preserva identidade visual com cards de exploração, adiciona testes/decisões/operação local. Não recria banco vetor, auth ou chatbot.

**Riscos não resolvidos automaticamente:** executar Docker real, confirmar conformidade da fonte Instagram, comprovar desempenho da busca com dados novos, conferir estabelecimentos e atualizar dados de eventos. Todos constam no checklist `docs/DOCKER_LOCAL.md` e nos bloqueios `decisions.md`.
