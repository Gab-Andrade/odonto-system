---
name: novo-modulo
description: Cria um novo módulo de domínio no backend (ex. pacientes, agenda, estoque, precificacao) seguindo o padrão do projeto, com models, schemas, service, router, migração com RLS e testes. Use quando o usuário pedir um módulo, domínio ou CRUD novo.
argument-hint: <nome-do-modulo> [descrição das entidades]
---
# Novo módulo de domínio

Módulo: `$ARGUMENTS`. Se as entidades e os campos não estiverem claros, consulte a seção do módulo em `docs/PLANO.md` (seção 4) e pergunte ao usuário só o que faltar.

Use **apenas** `backend/app/modules/identidade/` e `backend/app/modules/auditoria/router.py` como referência de estilo. Não leia outros módulos.

## Estrutura

`backend/app/modules/<nome>/`:

| Arquivo | Conteúdo |
|---|---|
| `__init__.py` | vazio |
| `models.py` | Models com `UUIDPkMixin, TenantMixin, TimestampMixin, Base` (de `app.core.models`). Docstring do módulo explicando o domínio. |
| `schemas.py` | Pydantic v2. Entrada (`XCreate`, `XUpdate`) **sem** `clinic_id`; saída (`XOut`) com `model_config = ConfigDict(from_attributes=True)`. |
| `service.py` | Regras de negócio. Recebe `Session` + `CurrentUser`; exceções de domínio próprias (como `InvalidCredentials` em identidade). Sem dependências de FastAPI. |
| `router.py` | `APIRouter(prefix="/<nome>", tags=["<nome>"])`. Converte exceções do service em `HTTPException`. |

## Regras obrigatórias

- Sessão: `db: Session = Depends(get_tenant_db)`. Autorização: `Depends(require_roles(Role...))`. Ambos vêm de `app.modules.identidade.deps`.
- Não filtre por `clinic_id` nas consultas, porque o RLS já filtra. Ao criar registros, `clinic_id=user.clinic_id`.
- Operações sobre dados de paciente/financeiro: `audit.record(db, user, "<nome>.<acao>", entity_type=..., entity_id=..., request=request)` antes do `db.commit()`.
- Registros clínicos imutáveis (ex. evolução): sem endpoint de update/delete; correções entram como adendo.
- Textos de API, docstrings e mensagens de erro em português.

## Passos

1. Escreva models, schemas, service e router.
2. Importe os models em `backend/app/models.py` (e no `__all__`).
3. Registre o router em `backend/app/main.py` (`app.include_router(...)`).
4. Crie a migração seguindo a skill `nova-migracao`.
5. Adicione as tabelas ao `TRUNCATE` de `clean_db` em `backend/tests/conftest.py`, antes de `audit_logs`/`clinics` por causa das FKs.
6. Testes em `backend/tests/test_<nome>_integration.py` com `pytestmark = pytest.mark.integration`, usando as fixtures `client` e `make_clinic` e os helpers de login de `tests/test_auth_integration.py`. Mínimo:
   - CRUD feliz via API;
   - papel sem permissão → 403;
   - clínica B não enxerga nem altera registro da clínica A (via API **e** via `tenant_session`).
   Lógica pura (cálculos, validações) vai em testes unitários sem banco.
7. Em paralelo, numa única mensagem: acione o agente `test-runner` e o agente `revisor-tenancy` (escopo: o módulo novo). Corrija o que vier e rode o `test-runner` de novo.
8. Com testes e revisão ok, rode a skill `documentar <nome>` (gera docs técnica e de usuário em paralelo).
9. Se a implementação envolver uma decisão de arquitetura, proponha uma linha para a tabela "Decisões registradas" de `docs/PLANO.md`.
