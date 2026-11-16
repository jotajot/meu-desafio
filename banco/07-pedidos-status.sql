-- Otimização da rota GET /pedidos?status=&pagina= (G5):
-- 1. Substitui o índice composto por versão cobridora (INCLUDE cliente_id),
--    eliminando fetches na heap (e leitura de observacoes) via Index-Only Scan.
-- 2. Pré-agrega a contagem de pedidos por status em visão materializada,
--    eliminando o count(*) repetido sobre ~100 mil linhas por status.

DROP INDEX IF EXISTS idx_pedidos_status_criado_id;

CREATE INDEX idx_pedidos_status_criado_id_cobridor
    ON pedidos (status, criado_em DESC, id DESC)
    INCLUDE (cliente_id);

CREATE MATERIALIZED VIEW mv_contagem_pedidos_status AS
SELECT
    status,
    count(*)::bigint AS total
FROM pedidos
GROUP BY status;

CREATE UNIQUE INDEX idx_mv_contagem_pedidos_status
    ON mv_contagem_pedidos_status (status);

VACUUM ANALYZE pedidos;
ANALYZE mv_contagem_pedidos_status;

