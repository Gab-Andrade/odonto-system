# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Sistema de gestão odontológica multi-clínica. Hoje só existe o backend (Fase 0 – Fundação); visão, roadmap e decisões em [docs/PLANO.md](docs/PLANO.md). Código, comentários, mensagens de commit e textos de API em **português**.

## Comandos

Tudo a partir de `backend/` (Python 3.12+, `pip install -e ".[dev]"`):

```sh
ruff check . && ruff format --check .      # lint (CI roda os dois)
pytest                                     # sem banco: integração é pulada
pytest tests/test_unit.py::nome_do_teste   # um teste
alembic upgrade head                       # usa MIGRATIONS_DATABASE_URL (role dono)
alembic revision -m "descricao"            # migrações são escritas à mão (ver abaixo)
uvicorn app.main:app --reload
```

Ambiente completo: `docker compose up --build` na raiz (Postgres + API em :8000, migra na subida). Primeira clínica: `docker compose exec api python -m app.cli criar-clinica ...` (ver README).

Testes de integração (`@pytest.mark.integration`) exigem `TEST_DATABASE_URL` (role `odonto_app`) e `TEST_MIGRATIONS_DATABASE_URL` (role `odonto`). O banco de teste é **apagado** (downgrade base → upgrade head) a cada sessão — nunca aponte para o banco de dev. O CI (`.github/workflows/ci.yml`) roda tudo contra `odonto_test`.

## Arquitetura

Monólito modular FastAPI. `app/core/` tem infraestrutura transversal; `app/modules/<dominio>/` segue `models.py`, `schemas.py`, `service.py`, `router.py` (+ `deps.py` quando expõe dependências). `identidade` é o módulo de referência.

### Multi-tenant com Row-Level Security (o ponto mais importante)

- Dois roles no Postgres: `odonto` (dono do schema, roda migrações) e `odonto_app` (a aplicação; sem BYPASSRLS, não é dono). Criado por `docker/postgres/roles.sql`; default privileges dão CRUD ao `odonto_app` em tabelas novas automaticamente.
- `app/core/db.py`: um listener `after_begin` executa `set_config('app.clinic_id', ..., true)` em **toda** transação de uma sessão criada por `tenant_session(clinic_id)`. Sessões de `get_db()` não têm tenant e só enxergam tabelas globais (`clinics`, `users`, `clinic_memberships`, isoladas na camada de serviço).
- Tabela de domínio de clínica = model com `TenantMixin` **e** migração chamando `app.core.rls.enable_tenant_rls("<tabela>")` (e `disable_tenant_rls` no downgrade). Esquecer a migração vaza dados entre clínicas.
- Por isso, consultas em sessão de tenant **não** filtram por `clinic_id` manualmente — o RLS já faz.
- Ao adicionar models, importe-os em `app/models.py` (alimenta o metadata do Alembic e dos testes) e inclua a tabela no `TRUNCATE` da fixture `clean_db` em `tests/conftest.py`.

### Auth e papéis

- JWT (`app/core/security.py`) carrega `sub` (usuário) e `cid` (clínica). O **papel é relido do banco a cada request** (`identidade.service.active_role`), então desativar usuário/vínculo/clínica corta o acesso na hora.
- Endpoints de outros módulos usam `Depends(require_roles(Role.X, ...))` e `Depends(get_tenant_db)` de `app.modules.identidade.deps`. Papéis em `app/core/roles.py`.

### Auditoria (LGPD)

`app.core.audit.record(session, user, "acao", ...)` adiciona à sessão; o commit é de quem chama. `audit_logs` é append-only: a migração revoga UPDATE/DELETE/TRUNCATE do `odonto_app`.

### Convenções

- `Base` usa naming convention para constraints (`app/core/models.py`); enums são `native_enum=False` com CHECK criado na migração.
- Ruff com regras `S` (bandit) ativas; `B008` ignorado por causa de `Depends()`.
