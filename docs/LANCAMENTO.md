# Critérios de go/no-go do soft launch

| Verificação | Estado deste pacote | Responsável operacional |
|---|---|---|
| Python: triagem, extração opcional, revisão, seed | Implementado; 12 testes Python + 10 verificações Worker passaram no ambiente de montagem | Projeto |
| Eventos vencidos bloqueados | Implementado no ETL e API | Projeto |
| Busca/cors/limites/ranking básicos | Implementado e parcialmente testado via mock + SQLite | Projeto |
| Astro e CSS integrados | Implementado, **build Astro não executado neste ambiente** | Dev/CI |
| Docker Compose local (API + Astro + D1) iniciado e testado | **Pendente: execução no computador do projeto** | Dev |
| D1 remoto migrado e conferido | **Não realizado** | Operador Cloudflare |
| Worker implantado e com origem Pages autorizada | **Não realizado** | Operador Cloudflare |
| Pages implantado com PUBLIC_API_URL | **Não realizado** | Operador Cloudflare |
| Marca original (`logo.png`) | Arte horizontal transparente original recuperada; confirmar no navegador | Dev |
| Páginas legais e contatos revisados | **Pendente: textos são modelos iniciais** | Responsável pelo projeto |
| 13 lugares da base revistos quanto à operação atual | **Pendente** | Revisão editorial |
| Eventos recentes para tornar a busca temporal útil | **Pendente** | Coleta/ETL |
| Analytics de page views (opcional) | Habilitar pelo painel Cloudflare Pages | Operador Cloudflare |
| Analytics de busca/clicks customizados | Não implementado nesta fase | Roadmap pós-soft-launch |
| Remoção de arquivos `.wrangler` do Git | **Pendente** | Dev |
| 20 consultas reais e teste mobile | **Pendente** | QA manual |

## Pesquisa de aceitação (amostragem)

- `hamburger`, `hamburgueria`, `burger`
- `restaurante`, `bar`, `café`
- `Santa Tereza`, `Savassi`, `Centro`, `Cidade Nova`
- `música ao vivo`, `pagode`, `rock`, `jazz`
- `evento gratuito hoje`, `eventos amanhã`, `eventos fim de semana`
- `lugar para ir com criança`, `família`
- Termo inexistente, termo com `%` ou `_`, 160+ caracteres, e URL inesperada

Registrar para cada consulta se trouxe um resultado **correto, atualizado e útil**, não apenas se a API retornou HTTP 200. Com apenas 13 lugares elegíveis, ausência de resultados para muitas buscas é esperada e não significa defeito da API.

## Pendências técnicas reconhecidas

1. Entity resolution: mesmo lugar divulgado por posts diferentes ainda pode gerar cards duplicados.
2. Equivalência linguística e relevância: sinônimos manuais cobrem termos comuns; não substituem avaliação por queries reais.
3. Proteção contra extração da base: dados não são baixados na build, mas uma API pública pode ser explorada; configurar proteção de bots/rate limits no painel Cloudflare se necessário.
4. Verificação de estabelecimentos: título/endereço/preço derivados da fonte social precisam de recertificação periódica.
5. Datas de recorrência e eventos noturnos que terminam no dia seguinte vão para revisão manual, não são inferidos silenciosamente.
6. A autenticação administrativa, pagamentos, painel, agente e motor vetorial continuam explicitamente fora do MVP.
