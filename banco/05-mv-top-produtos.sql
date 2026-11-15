-- Visão materializada pré-agregada para eliminar a varredura de 1,5M de itens em top-produtos (G7)
CREATE MATERIALIZED VIEW mv_top_produtos AS
SELECT pr.id,
       pr.nome,
       pr.categoria,
       sum(i.quantidade) AS unidades,
       sum(i.quantidade::bigint * i.preco_unitario_centavos) AS receita_centavos
  FROM itens_pedido i
  JOIN pedidos p ON p.id = i.pedido_id
  JOIN produtos pr ON pr.id = i.produto_id
 WHERE p.status <> 'cancelado'
 GROUP BY pr.id, pr.nome, pr.categoria;

-- Índice único por produto (permite REFRESH MATERIALIZED VIEW CONCURRENTLY em produção)
CREATE UNIQUE INDEX idx_mv_top_produtos_id ON mv_top_produtos (id);

-- Índice na ordenação do ranking para retornar LIMIT $1 sem Sort
CREATE INDEX idx_mv_top_produtos_ranking ON mv_top_produtos (receita_centavos DESC, id ASC);

VACUUM ANALYZE mv_top_produtos;

