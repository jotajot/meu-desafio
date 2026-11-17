# Próximos Testes (Ideias com Status "Pesquisada, teste futuro")

Este documento reúne alternativas pesquisadas na literatura e na documentação oficial que ficaram fora do ciclo principal de medições — seja por exigirem alteração do contrato HTTP (proibida pela régua do desafio), por envolverem infraestrutura adicional (novos containers e custo extra de CPU/RAM) ou por dependerem de mudanças estruturais na tabela base.

---

## 1. Paginação por Cursor (*Keyset Pagination*) em `GET /pedidos`

- **Status:** Pesquisada, teste futuro
- **Fonte:** Winand, M. *Use The Index, Luke! — No-Offset Pagination*. Disponível em: https://use-the-index-luke.com/no-offset
- **Por que não foi testada aqui:** A rota `GET /pedidos?status=&pagina=` recebe número de página via `OFFSET` (ex.: `pagina=1000` na carga e `pagina=15000` no `contrato/verificar.js`) e devolve o campo `total`. Trocar para paginação por cursor quebraria o contrato HTTP exigido pelo desafio.
- **Ganho esperado:** Mesmo com o índice composto `(status, criado_em DESC, id DESC)`, o `OFFSET` obriga o banco a percorrer e descartar $N$ entradas do índice até atingir a página solicitada (custo linear $O(N)$). Com *Keyset Pagination* (`WHERE (criado_em, id) < ($cursor_data, $cursor_id)`), o tempo de busca permanece constante $O(\log N)$ independentemente da profundidade da página.
- **Como testaria:** Criaria uma nova versão do endpoint (`/v2/pedidos?status=&cursor=`) mantendo a ordenação por `(criado_em DESC, id DESC)` sem `OFFSET` e sem `count(*)` obrigatório a cada página, e mediria comparando a latência em páginas profundas (equivalente à página 1.000 e à página 15.000).
- **O que precisaria para testar:** Permissão para versionar/alterar o contrato HTTP e adaptação do script de carga (`carga/teste-carga.js`) e dos casos de teste para navegar por cursor em vez de `pagina`.

---

## 2. Pooler Externo com PgBouncer (*Transaction Pooling*)

- **Status:** Pesquisada, teste futuro
- **Fonte:** PgBouncer Project. *Lightweight connection pooler for PostgreSQL*. Disponível em: https://www.pgbouncer.org/ ; Supabase Docs. *Connecting to Postgres & Connection Management (Pooling)*. Disponível em: https://supabase.com/docs/guides/database/connecting-to-postgres
- **Ganho esperado:** Embora o `pg.Pool` na API já tenha eliminado conexões efêmeras para uma única instância Node.js, o PgBouncer em modo `transaction` permitiria escalar horizontalmente múltiplas réplicas da API multiplexando centenas de clientes sobre poucos processos backend no PostgreSQL, reduzindo consumo de RAM por conexão no banco.
- **Como testaria:** Adicionaria um serviço `pgbouncer` no `docker-compose.yml` com `pool_mode = transaction`, apontaria `DB_HOST` da API para o PgBouncer e executaria 3 baterias de `scripts/medir.sh`, comparando vazão e p95 contra o custo adicional de CPU/RAM do container `pgbouncer` no `recursos.txt` (e avaliando o impacto com múltiplas réplicas da API).
- **O que precisaria para testar:** Configuração do container `pgbouncer` (com `userlist.txt` e `pgbouncer.ini`), ajuste de limites no `docker-compose.yml` e cenário de carga com maior concorrência ou múltiplas instâncias da API.

---

## 3. Cache Distribuído em Memória com Redis (*Cache-Aside* + TTL)

- **Status:** Pesquisada, teste futuro
- **Fonte:** Redis Documentation. *Cache-aside pattern*. Disponível em: https://redis.io/docs/latest/develop/use-cases/cache-aside/
- **Ganho esperado:** No experimento `11-cache-busca-produtos` (descartado e revertido), um cache LRU local na API reduziu a CPU do banco de 98,0% para 43,7% e elevou a vazão para 455,78 req/s, mas cada réplica da API teria o próprio cache. Depois, o índice de trigramas do `12` resolveu a mesma rota no banco, com resultado melhor e sem estado na API. Por isso, hoje eu só testaria Redis em um cenário com várias réplicas da API e termos de busca variados: a carga atual usa 12 termos fixos, o que deixa a taxa de acerto de qualquer cache artificialmente alta. O Redis permitiria compartilhar respostas entre réplicas com expiração centralizada (TTL).
- **Como testaria:** Subiria um container `redis` no `docker-compose.yml`, escalaria/ajustaria o orçamento da camada de aplicação implementando *Cache-Aside* com TTL curto (ex.: 30–60 s) e proteção contra *cache stampede*, executaria 3× `scripts/medir.sh` e confrontaria o ganho de latência/vazão com o custo extra de memória e CPU do novo container no `recursos.txt`.
- **O que precisaria para testar:** Adição do serviço `redis` e da dependência na API (`api/package.json`), definição explícita de orçamento adicional de CPU/RAM para o cache, uma carga com termos de busca variados (o que exige mudar `carga/`, fora do escopo do desafio) e, em produção com escritas, definição de estratégia de invalidação e testes com tráfego de escrita (`INSERT`/`UPDATE`).

---

## 4. Particionamento Declarativo por Faixa de Data (*Range Partitioning*)

- **Status:** Pesquisada, teste futuro
- **Fonte:** The PostgreSQL Global Development Group. *PostgreSQL Documentation: Table Partitioning*. Disponível em: https://www.postgresql.org/docs/current/ddl-partitioning.html
- **Por que não foi testada aqui:** Alterar a definição de `pedidos` para tabela particionada exige modificar o DDL de criação (`banco/01-estrutura.sql`, que faz parte da régua imutável) e incluir a coluna de particionamento (`criado_em`) na chave primária/única.
- **Ganho esperado:** Em cenários de crescimento contínuo da tabela `pedidos` (dezenas de milhões de linhas), o particionamento mensal/anual por `criado_em` habilitaria *Partition Pruning* em consultas com janela de datas (como `vendas-por-dia`), mantendo índices menores em RAM e permitindo expurgo instantâneo de histórico antigo (`DROP TABLE` / `DETACH PARTITION`).
- **Como testaria:** Criaria `pedidos` com `PARTITION BY RANGE (criado_em)` (partições mensais ou trimestrais) em uma base de maior volume (ex.: 5–10M de pedidos), validaria os planos via `EXPLAIN (ANALYZE, BUFFERS)` confirmando a poda de partições e compararia 3 medições de carga contra a tabela monolítica.
- **O que precisaria para testar:** Permissão para recriar o esquema base (`01-estrutura.sql`) ou migrar dados para tabela particionada, além de massa de dados maior que a memória disponível para evidenciar os ganhos de localidade de índices.

---

## 5. Ajuste Fino de Memória do PostgreSQL (`shared_buffers`, `work_mem`, `effective_cache_size`)

- **Status:** Pesquisada, teste futuro
- **Fonte:** The PostgreSQL Global Development Group. *PostgreSQL 16 Documentation: 20.4. Resource Consumption*. Disponível em: https://www.postgresql.org/docs/16/runtime-config-resource.html
- **Ganho esperado:** Aumentar `work_mem` (padrão 4 MB) evita *spill* para disco em operações de `Sort` e `HashAggregate`, enquanto ajustar `shared_buffers` e `effective_cache_size` adequados ao limite de 512 MB do container reduz leituras repetidas do cache do sistema operacional e melhora decisões do otimizador baseadas em custos.
- **Como testaria:** Partindo da configuração recomendada (`13`, banco com 0,5 CPU), testaria em dois passos separados: (1) reduzir o limite de memória do banco de 512 MB para 256 MB, já que a tabela inteira de `produtos` ocupa 190 blocos e os índices das rotas quentes são pequenos; (2) só então ajustar `-c shared_buffers=...` e `-c work_mem=...` no `command` do serviço `banco` para caber no novo limite. Cada passo com 3 execuções de `scripts/medir.sh`, observando o `mem_max` no `recursos.txt` e a ausência de erros. Atenção: a RAM medida inclui cache de páginas e variou muito entre execuções do mesmo código, então o critério tem que ser erro/OOM e vazão, não a média de RAM.
- **O que precisaria para testar:** Ajuste iterativo do `command` no `docker-compose.yml` após estabilizar os índices e queries finais, acompanhado de monitoramento de `mem_max` e `EXPLAIN (ANALYZE, BUFFERS)`.



---

## 6. Tamanho do pool de conexões (`DB_POOL_MAX`)

- **Status:** Pesquisada, teste futuro
- **Fonte:** Carlson, B. *node-postgres: Pooling*. Disponível em: https://node-postgres.com/features/pooling ; Leach, B. *How to Manage Connections Efficiently in Postgres, or Any Database* (2018). Disponível em: https://brandur.org/postgres-connections
- **Por que não foi testada aqui:** O pool ficou fixo em 10 conexões desde o `01`, sem que eu testasse outro valor.
- **Ganho esperado:** No `13`, com meia CPU no banco, a CPU do banco por requisição subiu de 0,72 para 0,91 ms (+26%) e o banco foi pausado em 93,1% dos períodos ([diagnostico/10](diagnostico/10-throttling-cpu-banco.txt)). Minha hipótese, não verificada, é que 10 processos disputando meia CPU geram troca de contexto e espera. Um pool menor poderia devolver parte dessa eficiência sem aumentar o hardware.
- **Como testaria:** Na configuração `13`, mudaria só a variável de ambiente `DB_POOL_MAX` da API (já lida em `api/src/db.js`) para 4 e depois para 20, uma mudança por commit, com 3 execuções de `scripts/medir.sh` cada, comparando vazão, `p95` e CPU do banco por requisição ([diagnostico/medianas.py](diagnostico/medianas.py)).
- **O que precisaria para testar:** Apenas tempo de medição; não exige mudar a régua.

---

## 7. Política de atualização das materialized views sob escrita

- **Status:** Pesquisada, teste futuro
- **Fonte:** The PostgreSQL Global Development Group. *PostgreSQL 16 Documentation: REFRESH MATERIALIZED VIEW*. Disponível em: https://www.postgresql.org/docs/16/sql-refreshmaterializedview.html ; [diagnostico/08-refresh-materialized-views.txt](diagnostico/08-refresh-materialized-views.txt)
- **Por que não foi testada aqui:** A carga do desafio só lê, então as três materialized views (`mv_top_produtos`, `mv_vendas_por_dia`, `mv_contagem_pedidos_status`) nunca ficam desatualizadas durante a medição. Em produção, elas ficariam defasadas até o próximo `REFRESH`.
- **Ganho esperado:** Manter o ganho dos relatórios com uma defasagem conhecida. Sem carga concorrente, o `REFRESH ... CONCURRENTLY` levou 1,2 s (`mv_top_produtos`), 1,4 s (`mv_vendas_por_dia`) e 0,1 s (`mv_contagem_pedidos_status`), o que é compatível com atualização a cada poucos minutos. A documentação confirma que `CONCURRENTLY` não bloqueia leituras e exige índice `UNIQUE`, que as três views já têm.
- **Como testaria:** (1) Medir o `REFRESH` sob a carga do `medir.sh`, observando o efeito no `p95` das outras rotas. (2) Para o `total` de `GET /pedidos`, que hoje vem da view e pode divergir da lista de pedidos da mesma resposta, comparar com uma tabela de contadores atualizada por trigger: a leitura fica exata e o custo passa para a escrita.
- **O que precisaria para testar:** Um agendador para o `REFRESH` (cron externo ou extensão de agendamento) e uma carga com escrita (ver ficha 8).

---

## 8. Carga com escrita e modelo aberto

- **Status:** Pesquisada, teste futuro
- **Fonte:** Schroeder, B.; Wierman, A.; Harchol-Balter, M. *Open Versus Closed: A Cautionary Tale*. NSDI 2006. Disponível em: https://www.usenix.org/conference/nsdi-06/open-versus-closed-cautionary-tale ; Grafana Labs. *Open and closed models* (k6). Disponível em: https://grafana.com/docs/k6/latest/using-k6/scenarios/concepts/open-vs-closed/
- **Por que não foi testada aqui:** Exige mudar `carga/`, que faz parte da régua. A carga do desafio é fechada (`constant-vus`, sem pausa) e só de leitura.
- **Ganho esperado:** Não é um ganho de desempenho, e sim de validade. Em carga fechada, a vazão depende do tempo de resposta e o recurso gargalo fica sempre perto de 100%. Com taxa de chegada fixa (modelo aberto), daria para medir quanto de CPU sobra para uma demanda real, e com 10% de `INSERT` de pedidos daria para medir o custo dos índices criados e a defasagem das views.
- **Como testaria:** Em uma cópia da régua fora do desafio, usaria um executor de taxa de chegada constante do k6 com algumas taxas fixas (por exemplo, a vazão do `13`) e acrescentaria uma rota de escrita, comparando o estado original com o final.
- **O que precisaria para testar:** Permissão para alterar a régua e uma rota de escrita na API.

---

## 9. Separar o experimento 10 em três

- **Status:** Pesquisada, teste futuro
- **Fonte:** [experimentos.md](experimentos.md), linha `10-otimizar-pedidos-status`.
- **Por que não foi testada aqui:** O commit `c78ddb1` juntou três mudanças (índice cobridor `INCLUDE (cliente_id)`, `mv_contagem_pedidos_status` e troca do `SELECT *` por colunas explícitas). O salto de 3,7× não pode ser atribuído a nenhuma delas.
- **Ganho esperado:** Nenhum ganho novo: o objetivo é saber qual das três mudanças importa. Se a contagem pela view for a principal, a ficha 7 fica mais importante; se for o índice cobridor, a view de contagem poderia ser retirada, eliminando uma fonte de defasagem.
- **Como testaria:** A partir do estado `09`, aplicar as três mudanças em commits separados, com 3 execuções de `scripts/medir.sh` cada, no mesmo dia.
- **O que precisaria para testar:** Cerca de 1 hora de medições e recriação do banco entre os passos.

---

## 10. Dividir a mesma cota de CPU entre API e banco

- **Status:** Pesquisada, teste futuro
- **Fonte:** Docker. *Resource constraints*. Disponível em: https://docs.docker.com/engine/containers/resource_constraints/ ; Express. *Production best practices: performance and reliability* (seção "Run your app in a cluster"). Disponível em: https://expressjs.com/en/advanced/best-practice-performance.html
- **Por que não foi testada aqui:** O gargalo mudou de lugar duas vezes no fim do trabalho: no `12` (1,5 vCPU) foi a API, com 48,2% de 50%; no `13` (1,0 vCPU) voltou a ser o banco, com 49,7% de 50% e a API em 25,8%. Não testei outras divisões da mesma cota total.
- **Ganho esperado:** Com o mesmo 1,0 vCPU do `13`, uma divisão como 0,4 para a API e 0,6 para o banco pode aumentar a vazão sem custo adicional, porque a API tinha folga e o banco não. Como o JavaScript da API roda em uma única thread, um único processo Node.js tende a não aproveitar uma cota de mais de 1 CPU; nesse caso seria preciso rodar mais de um processo (cluster).
- **Como testaria:** Partindo do `13`, mudar só os dois `cpus` no `docker-compose.yml` mantendo a soma em 1,0, com 3 execuções de `scripts/medir.sh` por divisão.
- **O que precisaria para testar:** Apenas tempo de medição; não exige mudar a régua.
