-- Concede leitura nos três bancos de pecuária a um usuário somente leitura JÁ EXISTENTE
-- (use se o usuário safratech_leitura foi criado antes da integração da pecuária).
-- Execute como superusuário:  psql -U postgres -f sql/conceder_leitura_pecuaria.sql
-- Não altera estrutura nem dados: apenas concede permissão de leitura (tabelas e views do esquema public).

\connect pecuaria_compra_database
GRANT CONNECT ON DATABASE pecuaria_compra_database TO safratech_leitura;
GRANT USAGE ON SCHEMA public TO safratech_leitura;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO safratech_leitura;

\connect pecuaria_desempenho_database
GRANT CONNECT ON DATABASE pecuaria_desempenho_database TO safratech_leitura;
GRANT USAGE ON SCHEMA public TO safratech_leitura;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO safratech_leitura;

\connect pecuaria_rentabilidade_database
GRANT CONNECT ON DATABASE pecuaria_rentabilidade_database TO safratech_leitura;
GRANT USAGE ON SCHEMA public TO safratech_leitura;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO safratech_leitura;
