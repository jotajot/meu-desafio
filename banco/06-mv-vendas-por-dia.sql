-- Visão materializada pré-agregada por dia para o relatório vendas-por-dia (G7)
CREATE MATERIALIZED VIEW mv_vendas_por_dia AS
SELECT p.criado_em::date AS dia_data,
       to_char(p.criado_em::date, 'YYYY-MM-DD') AS dia,
       COUNT(DISTINCT p.id) AS pedidos,
       SUM(i.quantidade) AS itens,
       SUM(i.quantidade::bigint * i.preco_unitario_centavos) AS receita_centavos
  FROM pedidos p
  JOIN itens_pedido i ON i.pedido_id = p.id
 WHERE p.status <> 'cancelado'
 GROUP BY p.criado_em::date;

-- Índice único por data (habilita REFRESH MATERIALIZED VIEW CONCURRENTLY e busca por janela em < 0,1 ms)
CREATE UNIQUE INDEX idx_mv_vendas_por_dia_data ON mv_vendas_por_dia (dia_data);

VACUUM ANALYZE mv_vendas_por_dia;

