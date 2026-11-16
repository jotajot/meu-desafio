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
- **Ganho esperado:** No experimento `11-cache-busca-produtos` (descartado e revertido), um cache LRU local em memória na API reduziu a CPU do banco de `98.0%` para `43.7%` e elevou a vazão para `455.78 req/s`, mas saturou o limite de `0.5 vCPU` da instância única da API (`48.6%`), elevou a RAM do banco e criou estado local não compartilhável. Um cache externo distribuído com Redis permitiria compartilhar respostas de rotas com alta localidade (como `GET /produtos/busca`) entre múltiplas réplicas horizontais da API com expiração centralizada (TTL).
- **Como testaria:** Subiria um container `redis` no `docker-compose.yml`, escalaria/ajustaria o orçamento da camada de aplicação implementando *Cache-Aside* com TTL curto (ex.: 30–60 s) e proteção contra *cache stampede*, executaria 3× `scripts/medir.sh` e confrontaria o ganho de latência/vazão com o custo extra de memória e CPU do novo container no `recursos.txt`.
- **O que precisaria para testar:** Adição do serviço `redis` e da dependência na API (`api/package.json`), definição explícita de orçamento adicional de CPU/RAM para o cache e, em produção com escritas, definição de estratégia de invalidação/eventual consistência e testes com tráfego de escrita (`INSERT`/`UPDATE`).

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
- **Como testaria:** Passaria flags `-c shared_buffers=128MB -c work_mem=16MB -c effective_cache_size=384MB` no `command` do serviço `banco` em `docker-compose.yml`, mantendo exatamente os mesmos limites de 1 CPU / 512 MB, e compararia 3 execuções de `scripts/medir.sh` observando também o pico de memória no `recursos.txt` para garantir ausência de *OOM* sob 20 conexões simultâneas.
- **O que precisaria para testar:** Ajuste iterativo do `command` no `docker-compose.yml` após estabilizar os índices e queries finais, acompanhado de monitoramento de `mem_max` e `EXPLAIN (ANALYZE, BUFFERS)`.

