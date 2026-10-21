# Auditoria e entrega — 20/10/2026

## Fonte verificada

Repositório `peddrinn/oncovo` (branch `main`), acessado em 20/10/2026 pelo conector GitHub com permissão **somente leitura**. Arquivos lidos: `wrangler.toml`, `package.json`, `web/package.json`, `web/astro.config.mjs`, `web/src/pages/index.astro`, `web/src/styles/global.css`, `db/schema.sql`, `etl/gerar_seed.py`, `worker/index.ts`, `.gitignore` e árvore completa. Os dados locais analisados são os três JSONL fornecidos no contexto deste projeto.

## Defeitos reproduzidos da versão anterior

1. Astro apontando para `http://localhost:8787/api/search` independentemente de ambiente: quebra em produção.
2. CSS `web/src/styles/global.css` não estava importado pela página inicial; Tailwind 4 instalado mas sem emissão das classes no bundle.
3. SQL de schema com `DROP TABLE IF EXISTS` e seed com `DELETE FROM search_items`, alto risco de perda da base remota.
4. UUID a cada seed gerava linhas novas, sem continuidade de ID estável.
5. `starts_at` editorial contém valores como `às 18:00` e `04/07 às 14:00`, não timestamps ISO padronizados.
6. Busca apenas AND de `LIKE` sem expansão de acentos/sinônimos/filtros; resultados irrelevantes ou ausentes.
7. Eventos vencidos poderiam estar marcados `published` na tabela e exibidos.
8. Links de rodapé apontavam para arquivos `contato.html` inexistentes.
9. `.wrangler/state` com artefatos SQLite estava versionado.

## Decisões preservadas

- MVP = busca + lista de cards em BH.
- ETL offline em Python; Maritaca opcional e econômico, com limite de lote e revisão humana.
- Cloudflare D1/Worker + Astro/Cloudflare Pages; sem LLM no runtime.
- Links para post original e mapa em cada card, sem página individual.
- Sem login, Pinecone, Meilisearch, chatbot ou orquestradores de agentes.

## Resultado empírico

- `all_posts.jsonl`: 1.170 registros e 1.166 códigos distintos; fila configurada de 100 itens.
- `items_publicaveis.jsonl`: 100 decisões editoriais históricas.
- Revalidação com `extracoes_validas_100.jsonl`: 13 lugares publicados, 32 em revisão, 41 eventos expirados, 14 ocultados.
- Banco SQLite local: 13 linhas `place/published`; execução consecutiva do mesmo seed mantém o número de registros (UPSERT idempotente).
- Consultas SQL executadas em SQLite com parâmetros montados pelo Worker; busca `hamburger` retornou 3 resultados na base de teste revalidada.
- Python: 6 testes automáticos; Worker: 10 verificações de runtime por mock + TypeScript válido. A sintaxe do script cliente foi transpilada sem erros.

## Limitações dos testes

- Não foi realizado `npm ci`/`astro build` neste ambiente, pois dependências do projeto não estavam instaladas nem havia acesso de rede via terminal para baixá-las.
- Não foi possível comparar o D1 remoto com o banco local, executar deploy nem confirmar URLs públicas ou CORS em produção.
- O teste local de SQL não substitui teste no motor D1 remoto, verificação mobile, revisão de dados atuais ou teste de ponta a ponta no Cloudflare Pages.
- A política editorial não confirma se os 13 estabelecimentos estão abertos hoje.
- O script novo de extração Maritaca não foi executado contra API real: falta chave/execução autorizada; foi baseado no endpoint e parâmetros documentados, mas o prompt novo ainda precisa de avaliação de qualidade sobre lote controlado.

## Evidência de deploy necessária

Logs do GitHub CI verdes, build Astro, health da API retornando `dataset_version`, consulta real pelo navegador do domínio Pages, status/CORS corretos, métricas de carga e revisão editorial atualizada.
