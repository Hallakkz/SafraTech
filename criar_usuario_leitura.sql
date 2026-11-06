-- Cria um usuário SOMENTE LEITURA para o aplicativo (execute como superusuário, uma única vez).
-- Não altera a estrutura nem os dados dos bancos: apenas concede permissão de leitura.
-- Uso:  psql -U postgres -v senha="'sua_senha_forte'" -f sql/criar_usuario_leitura.sql
CREATE ROLE safratech_leitura LOGIN PASSWORD :senha;

\connect solo_database
GRANT CONNECT ON DATABASE solo_database TO safratech_leitura;
GRANT USAGE ON SCHEMA solo, meta TO safratech_leitura;
GRANT SELECT ON ALL TABLES IN SCHEMA solo, meta TO safratech_leitura;

\connect nutricao_database
GRANT CONNECT ON DATABASE nutricao_database TO safratech_leitura;
GRANT USAGE ON SCHEMA nutricao, meta TO safratech_leitura;
GRANT SELECT ON ALL TABLES IN SCHEMA nutricao, meta TO safratech_leitura;

\connect plantio_database
GRANT CONNECT ON DATABASE plantio_database TO safratech_leitura;
GRANT USAGE ON SCHEMA plantio, meta TO safratech_leitura;
GRANT SELECT ON ALL TABLES IN SCHEMA plantio, meta TO safratech_leitura;

-- Bancos de pecuária de corte (tabelas e views no esquema public)
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
