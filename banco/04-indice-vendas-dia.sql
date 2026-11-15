-- Índice parcial cobridor para o relatório vendas-por-dia (filtro sargable por criado_em excluindo cancelados)
CREATE INDEX idx_pedidos_criado_ativo
    ON pedidos (criado_em, id)
    WHERE status <> 'cancelado';

-- Atualiza estatísticas e mapa de visibilidade para habilitar Index-Only Scan em pedidos
VACUUM ANALYZE pedidos;

