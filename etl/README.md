# ETL Oncovo (offline, Python 3.11+)

Fonte bruta (`all_posts.jsonl`) e extrações LLM ficam fora do Git. Não faça commit de
credenciais, dados brutos, transcrições ou logs com legendas.

1. `python etl/triagem.py --input /caminho/all_posts.jsonl --output etl/processed/fila_100.jsonl --limit 100`
2. Para reaproveitar extrações já aprovadas, copie `extracoes_validas_100.jsonl` para `etl/processed/extracoes.jsonl`. Ou processe lotes com `python etl/extrair_llm.py --input etl/processed/fila_100.jsonl --output etl/processed/extracoes.jsonl --max-items 10` (prévia sem custo); acrescente `--execute` para usar créditos. Defina `MARITACA_API_KEY` no ambiente.
3. Avalie **editorialmente** extrações, riscos e postagens; marque `publish_status` em `etl/items_publicaveis.jsonl`. A política é fail-closed (não promove `review`).
4. `python etl/preparar_publicacao.py --approved etl/items_publicaveis.jsonl --extractions etl/processed/extracoes.jsonl --raw /caminho/all_posts.jsonl`
5. Confira `etl/output/revisao.csv`, `etl/output/search_items.jsonl` e o vencimento dos eventos.
6. `python etl/gerar_seed.py` cria `db/seed.sql` sem `DELETE FROM search_items` geral. Faça backup e execute no D1.

**Não** rode o script antigo de seed no remoto: ele apagava a tabela e gerava IDs diferentes a cada execução. Nunca copie `starts_at` livre de um lugar para o banco: horários comerciais não são datas de eventos. Na extração, `post_code` e URL são anexados pelo Python, economizando tokens do LLM. O novo prompt é independente e não reproduz literalmente o prompt antigo, que não estava nas fontes fornecidas.

### Garantias atuais e limites

- Deduplicação por `post_code` na fila; IDs estáveis derivados de plataforma+código do post.
- Legenda com mínimo de 80 caracteres; sem OCR/transcrição.
- Datas de eventos: apenas ISO explícito, fuso `America/Sao_Paulo`; sem inferência de recorrência.
- Eventos antigos expiram; promoções são ocultadas; `review` fica excluído.
- Datas absolutas podem tornar-se obsoletas entre extração e uso; reexecute a preparação antes de publicar.
- Nenhum processo valida, por si só, se um estabelecimento continua aberto: revisões periódicas são necessárias.
