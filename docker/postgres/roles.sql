-- Cria o role usado pela aplicação: sem superusuário, sem BYPASSRLS e sem ser
-- dono das tabelas, para que as policies de Row-Level Security sempre valham.
--
-- Variáveis psql obrigatórias:
--   app_password  senha do role odonto_app
--   owner         role dono do schema (o que roda as migrações)
--
-- psql ... -v app_password=xxx -v owner=odonto -f roles.sql

CREATE ROLE odonto_app LOGIN PASSWORD :'app_password'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;

GRANT USAGE ON SCHEMA public TO odonto_app;

-- Tabelas e sequências criadas pelas migrações (role dono) ficam acessíveis à aplicação.
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner" IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO odonto_app;
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner" IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO odonto_app;
