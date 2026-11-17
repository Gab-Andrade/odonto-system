# Odonto System

Sistema web de gestão odontológica: prontuário digital, odontograma 2D/3D, precificação
configurável, financeiro/estoque e inteligência clínica, otimizado para uso em tablet.

Visão, arquitetura e roadmap: [docs/PLANO.md](docs/PLANO.md).

## Estrutura

```
backend/    API FastAPI (monólito modular) + migrações Alembic + testes
docker/     scripts do Postgres (role da aplicação)
docs/       documentação
```

O frontend (React + Vite PWA) entra na sequência da Fase 0.

## Rodando com Docker

```sh
docker compose up --build
```

- API e documentação interativa: http://localhost:8000/docs
- As migrações rodam automaticamente na subida da API.

Criar a primeira clínica e o usuário admin (a senha é pedida no terminal):

```sh
docker compose exec api python -m app.cli criar-clinica \
  --nome "Clínica Exemplo" --slug exemplo \
  --admin-email admin@exemplo.com.br --admin-nome "Nome do Admin"
```

## Rodando o backend sem Docker

Requer Python 3.12+ e um PostgreSQL 16 com o role da aplicação criado:

```sh
psql -U odonto -d odonto -v app_password=odonto_app -v owner=odonto -f docker/postgres/roles.sql
```

```sh
cd backend
python -m venv .venv
.venv/Scripts/activate        # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

## Testes

```sh
cd backend
pytest                         # unitários; os de integração são pulados sem banco
ruff check . && ruff format --check .
```

Os testes de integração (isolamento entre clínicas, login, auditoria) rodam quando
`TEST_DATABASE_URL` e `TEST_MIGRATIONS_DATABASE_URL` apontam para um banco de teste
(**ele é apagado e recriado a cada execução**). No GitHub Actions eles rodam sempre.

## Decisões de segurança da fundação

- **Isolamento por clínica com Row-Level Security.** A aplicação conecta com o role
  `odonto_app` (sem superusuário, sem `BYPASSRLS`, sem ser dono das tabelas). Toda tabela
  com `clinic_id` recebe a policy via `app.core.rls.enable_tenant_rls` na migração.
- **Acesso revogável na hora.** O token JWT identifica usuário e clínica, mas o papel
  e o vínculo ativo são conferidos no banco a cada requisição.
- **Auditoria append-only.** `audit_logs` não aceita UPDATE/DELETE pelo role da aplicação.
- **Senhas com argon2id.** O login leva o mesmo tempo para e-mail inexistente, para não
  revelar quais e-mails estão cadastrados.
