# Otimização de API Node.js e PostgreSQL: de 2,60 para 292,39 req/s sem custo extra

## 1. Resumo

Uma API de e-commerce em Node.js 20 e PostgreSQL 16 (`0,5 CPU / 256 MB` na API; `1,0 CPU / 512 MB` no banco) entregava mediana de `2,60 req/s` e `p95` de `25.286,5 ms` sob 20 usuários virtuais, saturando o banco em `97,7%` de CPU. Após diagnóstico por `EXPLAIN (ANALYZE, BUFFERS)` e 11 experimentos isolados, aplicamos *pool* de conexões, remoção de *logs* síncronos, índices B-Tree compostos/funcionais/cobridores, eliminação de N+1, agregação SQL e visões materializadas. Mantendo o mesmo hardware e 42/42 respostas idênticas, a vazão subiu para **`292,39 req/s` (112,46×)** e o `p95` caiu para **`192,1 ms` (-99,2%)**.

## 2. Contexto e diagnóstico

Na configuração original ([`00-linha-de-base`](../resultados/20261112-095440-00-linha-de-base/resumo.txt)), 20 usuários virtuais em fila fechada no k6 geravam apenas `189` requisições em 60 s (`2,60 req/s`, `p50 = 1397,7 ms`, `p95 = 25286,5 ms`), com o PostgreSQL em `97,7%` de CPU e `390,8 MiB` de RAM.

As evidências coletadas comprovaram cinco causas raiz:
- [01-indices-originais.txt](../diagnostico/01-indices-originais.txt): apenas chaves primárias existiam, sem índices em chaves estrangeiras, `email` ou `status`.
- [02-estatisticas-tabelas-base.txt](../diagnostico/02-estatisticas-tabelas-base.txt): `1.273.500.000` tuplas lidas via varredura sequencial em `itens_pedido` (`idx_scan = 0`) e `218.000.000` em `pedidos`.
- [03-explain-analyze-original.txt](../diagnostico/03-explain-analyze-original.txt): *Seq Scans* em `clientes` (`224,4 ms`), `pedidos` (`988,6 ms`), `itens_pedido` (`913,5 ms`), ordenação em disco (`external merge Disk: 32640kB` em `/pedidos`) e junções de `1099,5 ms` em `top-produtos`.
- Código de `api/src/{db,rotas}.js` e [04-amostra-logs-api.txt](../diagnostico/04-amostra-logs-api.txt): conexão aberta/fechada por consulta (`pg.Client`), laços N+1 (~22 queries por chamada em `/clientes/:id/pedidos`), agregação em memória no Node.js com filtro não-*sargable* (`criado_em::date`) e log síncrono no `stdout`.

**Hipótese de causa:** *forks* por conexão no PostgreSQL, varreduras sequenciais repetidas, laços N+1 e agregações em tempo real esgotam a única CPU do banco.

## 3. Estado da arte

### Gerenciamento de conexões
O PostgreSQL usa modelo *process-per-connection*, no qual cada conexão exige *handshake* TCP, autenticação e `fork()` no sistema operacional (Leach, s.d.). A documentação do `node-postgres` recomenda manter um *pool* persistente (`pg.Pool`) na aplicação (Carlson, s.d.), enquanto guias de mercado sugerem *poolers* como o PgBouncer para múltiplas réplicas (Supabase Docs, s.d.).

### Indexação relacional, busca textual e otimização de consultas
Desde Selinger et al. (1979), otimizadores baseados em custo escolhem entre *Seq Scan* e índices conforme seletividade e I/O. No PostgreSQL, chaves estrangeiras não recebem índice automático, predicados com `lower(email)` exigem índices por expressão (Winand, s.d.) e índices B-Tree compostos ou cobridores (`INCLUDE`) habilitam ordenação encadeada e *Index-Only Scans* sem acesso à *heap* (PostgreSQL, 2024a). Para `ILIKE '%termo%'`, o módulo `pg_trgm` (PostgreSQL, 2024b) e o caso do GitLab (Peterse, s.d.) usam índices GIN de trigramas, cuja eficácia depende da seletividade e do tamanho da tabela. Já consultas N+1, filtros não-*sargable*, `SELECT *` em colunas largas e agregação fora do SGBD multiplicam o custo de rede e memória (Graefe, 1993; Dombrovskaya et al., 2021).

### Pré-computação analítica e caminho crítico na API
Consultas analíticas pesadas podem ser persistidas em `MATERIALIZED VIEW` indexável (PostgreSQL, 2024c), trocando recálculo contínuo por atualização periódica. No Node.js/Express, práticas de produção recomendam evitar `console.log(JSON.stringify(...))` síncronos para não bloquear o *Event Loop* (Express.js, s.d.; Node.js, s.d.), enquanto padrões de *cache-aside* reduzem leituras ao banco mediante consistência eventual (AWS, s.d.).

## 4. Alternativas consideradas

| Alternativa | Custo | Desempenho | Risco | Esforço |
| --- | --- | --- | --- | --- |
| **A. Pool na API + Índices + SQL + Materialized Views** | Zero extra (`0,5 + 1,0 CPU`) | Alto (`>100×` em leitura) | Baixo (defasagem em MVs sob escrita) | Médio |
| **B. Infraestrutura extra (PgBouncer / Redis)** | Médio (+CPU/RAM em containers) | Alto para múltiplas réplicas/cache | Médio (invalidação e operação) | Médio-alto |
| **C. Cache LRU em memória na API** | Zero container extra (usa cota da API) | Alto em leitura; satura `0,5 CPU` da API | Médio (estado local e migração de gargalo) | Baixo |
| **D. Escala vertical (mais CPUs/RAM)** | Alto (fatura maior) | Moderado (não corrige $O(N)$) | Baixo | Mínimo |

A alternativa **A** resolve as causas algorítmicas ($O(N) \to O(\log N)$) sem ampliar infraestrutura. A **B** adicionaria containers cobrados no `recursos.txt` sem ganho necessário para uma réplica única. A **C** reduz carga do banco, mas satura a cota de `0,5 CPU` da API e cria estado por instância. A **D** apenas compra folga temporária mantendo varreduras ineficientes.

## 5. Solução escolhida e por quê

Consolidamos a aplicação no estado **`10-otimizar-pedidos-status`** (conjunto **A**): `pg.Pool` (`max: 10`), remoção do *log* síncrono, 4 índices B-Tree iniciais, junção única com `LEFT JOIN`, agregação no SQL com filtro *sargable*, índice parcial cobridor em `pedidos(criado_em, id)`, `mv_top_produtos`, `mv_vendas_por_dia` e índice cobridor com `mv_contagem_pedidos_status` em `GET /pedidos`.

Para a realidade da T4H, essa escolha entrega **112×** mais vazão dentro do orçamento original (`1,5 vCPU` e `768 MB`), com o contrato HTTP preservado.

Experimentos sem benefício líquido foram **descartados com evidência**: `04-indice-trigramas` reduziu a vazão (`12,39 → 8,63 req/s`) sobre `produtos` de apenas 20 mil linhas e baixa seletividade; e `11-cache-busca-produtos`, embora tenha baixado a CPU do banco para `43,7%`, saturou a API em `48,6%` de `50%` (`0,5 CPU`), elevou a RAM do banco (`350,5 → 434,6 MiB`) e trouxe consistência eventual, sendo revertida em código.

## 6. Experimento e resultado

Todas as medições usaram `VUS=20`, `DURACAO=60s`, `AQUECIMENTO=15s`, `SEMENTE=42` e contrato `42/42` validado, comparando a mediana de 3 execuções contra a etapa anterior (`05` compara contra `03` após descarte de `04`).

| Mudança | Hipótese | p95 antes → depois | req/s antes → depois | CPU/RAM (mediana) | Pastas | Conclusão |
| --- | --- | --- | --- | --- | --- | --- |
| `01-pool-conexoes` | Pool reduz `fork`/TCP | `25286,5 → 19809,0 ms` | `2,60 → 3,58` | B: 99,2%/404M; A: 6,1%/34M | [01](../resultados/20261114-150927-01-pool-conexoes/resumo.txt) | Mantida (+37,7%) |
| `02-remover-log-resposta` | Remover log alivia API | `19809,0 → 21471,3 ms` | `3,58 → 3,22` | B: 98,0%/410M; A: 5,6%/33M | [02](../resultados/20261114-191658-02-remover-log-resposta/resumo.txt) | Sem ganho (banco saturado) |
| `03-indices-btree` | 4 B-Trees evitam `Seq Scan` | `21471,3 → 6736,1 ms` | `3,22 → 12,39` | B: 97,8%/421M; A: 16,9%/39M | [03](../resultados/20261114-210852-03-indices-btree/resumo.txt) | Mantida (3,85×) |
| `04-indice-trigramas` | GIN acelera `ILIKE` | `6736,1 → 9078,5 ms` | `12,39 → 8,63` | B: 95,4%/424M; A: 26,3%/40M | [04](../resultados/20261114-223530-04-indice-trigramas/resumo.txt) | Descartada (190 blocos) |
| `05-eliminar-n-mais-1` | `LEFT JOIN` evita loop N+1 | `6736,1 → 4399,9 ms` | `12,39 → 16,79` | B: 98,5%/422M; A: 17,5%/43M | [05](../resultados/20261114-235556-05-eliminar-n-mais-1/resumo.txt) | Mantida (+35,5% vs 03) |
| `06-agregacao-sql-vendas-por-dia` | Filtro *sargable* + `GROUP BY` | `4399,9 → 3675,7 ms` | `16,79 → 17,49` | B: 98,0%/409M; A: 3,6%/25M | [06](../resultados/20261115-103050-06-agregacao-sql-vendas-por-dia/resumo.txt) | Mantida (-79,4% CPU API) |
| `07-indice-criado-em` | Índice parcial em `pedidos` | `3675,7 → 2999,6 ms` | `17,49 → 17,33` | B: 98,0%/420M; A: 3,4%/25M | [07](../resultados/20261115-174505-07-indice-criado-em/resumo.txt) | Mantida (-18,4% p95) |
| `08-mv-top-produtos` | MV evita varrer 1,5M itens | `2999,6 → 1619,8 ms` | `17,33 → 37,27` | B: 98,8%/451M; A: 5,0%/27M | [08](../resultados/20261115-185228-08-mv-top-produtos/resumo.txt) | Mantida (+115,1%) |
| `09-mv-vendas-por-dia` | MV diária evita `itens_pedido` | `1619,8 → 695,0 ms` | `37,27 → 78,56` | B: 98,3%/395M; A: 9,7%/28M | [09](../resultados/20261115-201213-09-mv-vendas-por-dia/resumo.txt) | Mantida (+110,8%) |
| `10-otimizar-pedidos-status` | `INCLUDE` + MV de contagem | `695,0 → 192,1 ms` | `78,56 → 292,39` | B: 98,0%/351M; A: 21,0%/30M | [10](../resultados/20261115-211802-10-otimizar-pedidos-status/resumo.txt) | **Final (+272,2%)** |
| `11-cache-busca-produtos` | Cache LRU 60 s em `produtos` | `192,1 → 86,3 ms` | `292,39 → 455,78` | B: 43,7%/435M; A: 48,6%/31M | [11](../resultados/20261115-224351-11-cache-busca-produtos/resumo.txt) | Descartada (migrou p/ API) |

*(B = Banco; A = API, em MiB.)* Até `07`, mesmo após `pedidos` cair de `20.834` para `65` blocos ([05-explain-vendas-por-dia-pos-indice.txt](../diagnostico/05-explain-vendas-por-dia-pos-indice.txt)), `top-produtos` e `itens_pedido` (`9.555` blocos) saturavam o banco. Pré-computar relatórios (`08`, `09`) e remover `count(*)`/`SELECT *` (`10`) levou a vazão a `292,39 req/s` reduzindo a RAM do banco (`390,8 → 350,5 MiB`).

![Gráfico de evolução da vazão (req/s) e da latência p95 (ms) da linha de base ao experimento 11](img/evolucao-desempenho.png)

## 7. Limites e testes futuros

Na nossa avaliação, a solução atual possui três limites principais:
1. **Carga apenas de leitura:** sob `INSERT`/`UPDATE` concorrentes, os índices extras causam amplificação de escrita e as visões materializadas requerem `REFRESH MATERIALIZED VIEW CONCURRENTLY`, impondo defasagem ou custo periódico de atualização.
2. **Paginação e busca textual:** `GET /pedidos` mantém `OFFSET` linear $O(N)$ e `GET /produtos/busca` segue com `Seq Scan` (`p95 = 212,6 ms` no estágio `10`), saturando o banco em `98,0%` a `~292 req/s`.
3. **Lacunas não testadas:** tráfego misto de escrita, acima de 20 VUs e ajuste de `shared_buffers`/`work_mem`.

**Evidência que derrubaria a conclusão:** degradação severa de escrita pelos índices, bloqueio em `REFRESH` ou crescimento de `produtos` em 50× inviabilizando `Seq Scan`. As ideias adiadas (*keyset*, PgBouncer, Redis *cache-aside*, particionamento e *tuning* de memória) estão em [proximos-testes.md](../proximos-testes.md).

## 8. Referências

1. AWS Whitepapers. *Database Caching Strategies Using Redis — Caching Patterns*. Disponível em: https://docs.aws.amazon.com/whitepapers/latest/database-caching-strategies-using-redis/caching-patterns.html. Acesso em: 15 nov. 2026.
2. Carlson, B. *node-postgres Documentation: Pooling*. Disponível em: https://node-postgres.com/features/pooling. Acesso em: 15 nov. 2026.
3. Dombrovskaya, H., Novikov, B., & Bailliekova, A. (2021). *PostgreSQL Query Optimization: The Ultimate Guide to Building Efficient Queries*. Apress. Disponível em: https://doi.org/10.1007/978-1-4842-6885-8. Acesso em: 15 nov. 2026.
4. Express.js Documentation. *Production Best Practices: Performance and Reliability*. Disponível em: https://expressjs.com/en/advanced/best-practice-performance.html. Acesso em: 15 nov. 2026.
5. Graefe, G. (1993). *Query Evaluation Techniques for Large Databases*. ACM Computing Surveys, 25(2), 73–169. Disponível em: https://doi.org/10.1145/152610.152611. Acesso em: 15 nov. 2026.
6. Leach, B. *Managing High Postgres Connection Counts*. Disponível em: https://brandur.org/postgres-connections. Acesso em: 15 nov. 2026.
7. Node.js Documentation. *Don't Block the Event Loop (or the Worker Pool)*. Disponível em: https://nodejs.org/en/learn/asynchronous-work/dont-block-the-event-loop. Acesso em: 15 nov. 2026.
8. Peterse, Y. (GitLab). *Fast Search Using PostgreSQL Trigram Indexes*. Disponível em: https://about.gitlab.com/blog/fast-search-using-postgresql-trigram/. Acesso em: 15 nov. 2026.
9. Selinger, P. G., Astrahan, M. M., Chamberlin, D. D., Lorie, R. A., & Price, T. G. (1979). *Access Path Selection in a Relational Database Management System*. ACM SIGMOD, pp. 23–34. Disponível em: https://doi.org/10.1145/582095.582099. Acesso em: 15 nov. 2026.
10. Supabase Docs. *Connecting to Postgres & Connection Management (Pooling)*. Disponível em: https://supabase.com/docs/guides/database/connecting-to-postgres. Acesso em: 15 nov. 2026.
11. The PostgreSQL Global Development Group. *PostgreSQL 16 Documentation: Chapter 11 — Indexes*. Disponível em: https://www.postgresql.org/docs/16/indexes.html. Acesso em: 15 nov. 2026.
12. The PostgreSQL Global Development Group. *PostgreSQL 16 Documentation: F.35. pg_trgm — Trigram Matching*. Disponível em: https://www.postgresql.org/docs/16/pgtrgm.html. Acesso em: 15 nov. 2026.
13. The PostgreSQL Global Development Group. *PostgreSQL 16 Documentation: 41.3. Materialized Views*. Disponível em: https://www.postgresql.org/docs/16/rules-materializedviews.html. Acesso em: 15 nov. 2026.
14. Winand, M. *Use The Index, Luke! — Case-Insensitive Search (LOWER) & No-Offset Pagination*. Disponível em: https://use-the-index-luke.com/sql/where-clause/functions/case-insensitive-search e https://use-the-index-luke.com/no-offset. Acesso em: 15 nov. 2026.

## 9. Uso de IA

Agentes de IA auxiliaram na elaboração dos comandos SQL de diagnóstico, na implementação isolada das refatorações e na revisão editorial deste artigo. Todas as decisões experimentais (inclusive o descarte de `04` e `11`) foram conduzidas pelo autor, todos os links foram conferidos nas fontes originais e todos os números foram validados diretamente em `resultados/`, `diagnostico/` e `scripts/verificar-contrato.sh`.
