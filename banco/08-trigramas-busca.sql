-- Experimento 12: re-teste do índice de trigramas (descartado no 04) sobre o estado 10.
-- No estado 10 a busca por substring responde por 91,8% do tempo de execução no banco
-- (diagnostico/06-pg-stat-statements-estado-10.txt) e faz Seq Scan nos 190 blocos de produtos
-- descartando ~19 mil linhas por chamada (diagnostico/07-explain-busca-sem-gin.txt).
-- O índice GIN com gin_trgm_ops atende LIKE/ILIKE '%termo%' (PostgreSQL 16, F.35 pg_trgm).
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX idx_produtos_nome_trgm ON produtos USING gin (nome gin_trgm_ops);

-- Atualiza estatísticas e mapa de visibilidade de produtos
VACUUM ANALYZE produtos;
