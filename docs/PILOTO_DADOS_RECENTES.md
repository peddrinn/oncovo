# Primeiro piloto — proposta, não executada

Hipótese: 160 observações em dois lotes de 80, distribuídas inicialmente em 60 gastronomia, 40 lazer/experiências, 40 agendas de eventos e 20 espaços culturais/públicos. Ajustar à disponibilidade autorizada e à capacidade editorial; não prometer rendimento real antes da amostra.

Janela pretendida: lugares ~60 dias, agendas ~21 dias, priorizando ocorrências futuras comprovadas. O método deve declarar cobertura efetiva; um fetch dos N posts mais recentes não garante cobertura integral da janela. Variar bairros/tipos, registrar fontes conhecidas e lacunas, evitar seleção só por popularidade.

## Autorização 1 — aquisição/ingestão

Antes de qualquer download, coleta ou login, o usuário precisa aprovar:

1. Lista nominal de fontes/perfis/URLs e responsável por cada origem.
2. Método específico: arquivo fornecido pelo titular, dataset/feed oficialmente reutilizável ou API/integração autorizada. Disponibilidade pública sozinha não comprova licença. Instagram não está autorizado automaticamente.
3. Evidência de permissão/licença/consentimento aplicável, termos e escopo de uso; acesso privado/cookies/sessões ficam fora do Git.
4. Limites por fonte, 2×80 como teto operacional inicial, janela pretendida, cadência e política de interrupção diante de bloqueio/falha. Sem evasão ou login não autorizado.
5. Identificador do piloto/lotes, diretório local, retenção e quem fará revisão. Nenhuma inferência paga está incluída nessa autorização.

Manifesto proposto a preencher antes da execução: pilot_id, autorizador/referência/data, fontes nominais, método por fonte, categoria/bairros, janela e limites, batch_ids, destino raw, responsável por revisão, versão do pipeline e hashes dos arquivos. A1 gerará manifests/checkpoints reais somente ao executar dados autorizados. Não criar agora um manifesto que finja aquisição concluída.

Após adquirir cada lote autorizado: auditar JSONL, A1 global por post/hash, triagem e prévia A3. Medir recebidos, novos, repetidos, alterados, inválidos, descarte/ambiguidade por fonte, elegíveis e hits. Comparar entidades contra registry revisada via A2; fontes múltiplas por entidade não são novos lugares. Dados não publicados permanecem em revisão.

## Autorização 2 — inferência paga, separada

Somente depois da aquisição/planejamento, aprovar explicitamente:

1. plan_id e hashes da fila/manifesto; modelo/versão, prompt preservado e contrato; destino dos dados e condições de envio ao provedor.
2. Cotação vigente identificada por modelo/data/moeda/URL oficial ou parâmetros fornecidos pelo usuário com origem; preços separados de entrada/saída.
3. Bound de tokens de entrada verificado com referência apropriada de tokenizer/overhead/contexto. A heurística caracteres/3 não autoriza execução.
4. Quantidade inicial: até 20 tentativas (inclui retries), saída até 2.500 tokens por chamada, retry automático padrão 1 tentativa total. Usar 10–20 itens estratificados disponíveis, sem inventar estratos ausentes.
5. Teto financeiro e referência de autorização. **Proposta política inicial: até R$20 se a cotação/autorização forem em BRL**; isso não é estimativa de preço Maritaca nem garantia de que processa 20 itens. Se a cotação estiver em outra moeda, solicitar teto nessa moeda, sem câmbio implícito. O custo reservado deve caber no teto antes de cada tentativa; pode resultar em menos de 20 chamadas ou bloqueio completo.
6. Responsável por conferir usage/falhas, resolver tentativas de cobrança incerta e autorizar eventuais retries. Não zerar reservas de timeouts sem evidência.

Não executar o restante dos 160 com base apenas no primeiro opt-in. Revisar amostra humana, erro por campo/estrato, tempo de revisão e custo real informado/calculado antes de ampliar o envelope.

## Métricas e expansão

Formar referência humana de ~20 casos com raw, versão de extração e revisor identificados. Medir completude, evidência literal, tipo/local/unidade/datas/preço, contradições, alucinação e publicabilidade. Reportar denominadores por campo/tipo/fonte e distinguir ausência de gabarito. Eventos vencidos/promoções/recorrências não comprovadas não entram na busca.

Medir custo por post/revisão inferida, chamadas evitadas, entidade nova aprovada e candidato de fusão. `LLM elegível` não é previsão de estabelecimento aproveitável. Registrar carga de revisão: A2 já mostrou que nomes semelhantes podem gerar muitos candidatos sem justificar fusão.

Expandir só se os dois lotes preservarem integridade/IDs, campos críticos tiverem qualidade humana aceitável para o produto, gasto permanecer no teto, custo por entidade fizer sentido e houver capacidade de revisão. Interromper em corrupção, quebra de autorização, orçamento/usage incerto, excesso de erros críticos ou fila editorial sem capacidade. Sem taxas reais atuais, esses critérios são gates a medir, não resultados alcançados.

Publicação e reconciliação real continuam exigindo aprovações próprias: unidade/fonte/registry, atualidade e ocultação A5. Nenhuma autorização de aquisição ou inferência paga implica automaticamente publicação.
