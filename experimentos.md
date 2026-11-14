# Registro de Experimentos

Todas as medições abaixo usam os mesmos parâmetros no `scripts/medir.sh` (`VUS=20`, `DURACAO=60s`, `AQUECIMENTO=15s`, `SEMENTE=42`) e os mesmos limites de container (`banco`: 1,0 CPU / 512 MB; `api`: 0,5 CPU / 256 MB). Os valores comparados são sempre a **mediana de 3 execuções** com o mesmo rótulo.

- **Referência de comparação:** A mudança `01` compara contra a linha de base (`00-linha-de-base`). Para as mudanças seguintes, cada linha indica explicitamente se o "antes" é a mudança imediatamente anterior ou a linha de base.

## Linha de Base (`00-linha-de-base`)

- **Commit:** `5709347`
- **Pastas (3 execuções):**
  - [resultados/20261112-095036-00-linha-de-base/](resultados/20261112-095036-00-linha-de-base/resumo.txt) (2.60 req/s | p95 24377.1 ms | Banco CPU 97.7% / RAM 397.8 MiB)
  - [resultados/20261112-095440-00-linha-de-base/](resultados/20261112-095440-00-linha-de-base/resumo.txt) (2.67 req/s | p95 25315.9 ms | Banco CPU 96.2% / RAM 390.8 MiB)
  - [resultados/20261112-095651-00-linha-de-base/](resultados/20261112-095651-00-linha-de-base/resumo.txt) (2.57 req/s | p95 25286.5 ms | Banco CPU 97.8% / RAM 373.9 MiB)
- **Mediana:** `req/s = 2.60` | `p50 = 1397.7 ms` | `p95 = 25286.5 ms` | `p99 = 29730.1 ms` | `Banco CPU média = 97.7%` / `RAM média = 390.8 MiB` (`máx 464.8 MiB`) | `API CPU média = 6.7%` / `RAM média = 31.2 MiB` (`máx 38.3 MiB`).

---

## Tabela de Mudanças Aplicadas

| ID / Rótulo | Mudança & Commit | Hipótese | Fonte da Ideia | Status | Comparado Contra | Antes (Mediana) | Depois (Mediana) | Pastas (Antes → Depois) | Conclusão |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `01-pool-conexoes` | Substituir `pg.Client` efêmero por `pg.Pool` (`max: 10`) em [api/src/db.js](api/src/db.js) (`f20fc74`) | Manter um pool de conexões persistentes reduzirá a latência e aumentará a vazão ao eliminar handshakes TCP e criação de processos (`fork`) no PostgreSQL a cada consulta. | [node-postgres Pooling](https://node-postgres.com/features/pooling); [Brandur Leach](https://brandur.org/postgres-connections) | Aplicada e medida | `00-linha-de-base` | **req/s:** 2.60<br>**p95:** 25286.5 ms<br>**Banco:** CPU 97.7%, RAM 390.8 MiB<br>**API:** CPU 6.7%, RAM 31.2 MiB | **req/s:** 3.58 (+37.7%)<br>**p95:** 19809.0 ms (-21.7%)<br>**Banco:** CPU 99.2%, RAM 404.1 MiB<br>**API:** CPU 6.1%, RAM 34.2 MiB | **Antes:** [095036](resultados/20261112-095036-00-linha-de-base/resumo.txt), [095440](resultados/20261112-095440-00-linha-de-base/resumo.txt), [095651](resultados/20261112-095651-00-linha-de-base/resumo.txt)<br>**Depois:** [150722](resultados/20261114-150722-01-pool-conexoes/resumo.txt), [150927](resultados/20261114-150927-01-pool-conexoes/resumo.txt), [151134](resultados/20261114-151134-01-pool-conexoes/resumo.txt) | **Mantida.** O pool elevou a vazão em 37,7% e reduziu o p95 global em 21,7% sem aumentar os limites de hardware, mantendo os 42 testes de contrato. A CPU do banco segue em 99,2% porque as consultas continuam fazendo varreduras sequenciais sem índices. |
| `02-remover-log-resposta` | Remover middleware de log síncrono com corpo da resposta em [api/src/server.js](api/src/server.js) (`6cd21b1`) | Eliminar a dupla serialização JSON e a escrita síncrona no `stdout` reduziria o bloqueio do Event Loop, a CPU e a pressão de memória da API em caso de aumento massivo das reqs. | [Express Performance Best Practices](https://expressjs.com/en/advanced/best-practice-performance.html); [Node.js Event Loop](https://nodejs.org/en/learn/asynchronous-work/dont-block-the-event-loop) | Aplicada, sem ganho | `01-pool-conexoes` | **req/s:** 3.58<br>**p95:** 19809.0 ms<br>**Banco:** CPU 99.2%, RAM 404.1 MiB<br>**API:** CPU 6.1%, RAM 34.2 MiB | **req/s:** 3.22 (-10.1%)<br>**p95:** 21471.3 ms (+8.4%)<br>**Banco:** CPU 98.0%, RAM 410.0 MiB<br>**API:** CPU 5.6%, RAM 32.7 MiB | **Antes:** [150722](resultados/20261114-150722-01-pool-conexoes/resumo.txt), [150927](resultados/20261114-150927-01-pool-conexoes/resumo.txt), [151134](resultados/20261114-151134-01-pool-conexoes/resumo.txt)<br>**Depois:** [191314](resultados/20261114-191314-02-remover-log-resposta/resumo.txt), [191658](resultados/20261114-191658-02-remover-log-resposta/resumo.txt), [191853](resultados/20261114-191853-02-remover-log-resposta/resumo.txt) | **Hipótese refutada neste estágio.** A CPU da API caiu apenas de 6,1% para 5,6% e a RAM média variou de 34,2 para 32,7 MiB (pico 38,7 → 41,1 MiB). A vazão caiu 10,1% (variação normal do ambiente), pois com o banco saturado em 98% de CPU (~3 req/s), o custo do log na API é desprezível frente aos segundos gastos em Seq Scans no PostgreSQL. |

