-- Índices B-Tree para eliminar varreduras sequenciais e ordenações em disco (G3, G4 e G5)

-- G4: Busca case-insensitive de clientes por e-mail ordenada por id
CREATE INDEX idx_clientes_lower_email ON clientes (lower(email), id);

-- G3: Busca de pedidos por cliente já ordenada por criado_em DESC, id DESC (Pipelined Order By)
CREATE INDEX idx_pedidos_cliente_criado_id ON pedidos (cliente_id, criado_em DESC, id DESC);

-- G3: Busca de itens por pedido já ordenada por id
CREATE INDEX idx_itens_pedido_pedido_id_id ON itens_pedido (pedido_id, id);

-- G5: Contagem e listagem paginada por status já ordenada (elimina Sort em disco e habilita Index-Only Scan no count)
CREATE INDEX idx_pedidos_status_criado_id ON pedidos (status, criado_em DESC, id DESC);

-- Atualiza estatísticas do otimizador (inclusive do índice funcional) e mapa de visibilidade
VACUUM ANALYZE;

