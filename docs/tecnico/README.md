# Documentação técnica

Para quem vai mexer no código, sejam pessoas ou agentes. Visão de produto e roadmap estão em [PLANO.md](../PLANO.md). Comandos e convenções rápidas estão em [CLAUDE.md](../../CLAUDE.md).

Cada módulo tem um documento próprio, gerado e atualizado pela skill `documentar`. Leia o do módulo antes de alterá-lo.

## Módulos

| Módulo | Resumo |
|---|---|
| [identidade](identidade.md) | Clínicas, usuários, vínculos, login (JWT) e dependências de autenticação/papéis usadas por todos os módulos |
| [auditoria](auditoria.md) | Consulta do log de auditoria (LGPD) da clínica |
| [precificacao](precificacao.md) | Tabelas de preço versionadas com herança, atribuição por escopo, resolução com memória de cálculo, snapshots e importação de planilhas |

## Fundação (válida para todos os módulos)

### Isolamento entre clínicas

O banco tem dois roles:

| Role | Uso | RLS |
|---|---|---|
| `odonto` | dono do schema; roda migrações e as fixtures de limpeza dos testes | `FORCE ROW LEVEL SECURITY` vale até para ele |
| `odonto_app` | a aplicação | sem `BYPASSRLS` e não é dono das tabelas, então as policies sempre valem |

Fluxo de uma requisição autenticada:

```
Bearer JWT ─► identidade.deps.get_current_user   (sessão global get_db)
                 └─ active_role(): papel relido do banco
          ─► identidade.deps.get_tenant_db       (tenant_session(clinic_id))
                 └─ listener after_begin (core/db.py):
                    set_config('app.clinic_id', <id>, true) em TODA transação
          ─► policy tenant_isolation (core/rls.py) filtra USING e WITH CHECK
```

Consequências:
- Consultas em sessão de tenant não filtram `clinic_id`, porque o banco já filtra. Uma escrita com `clinic_id` de outra clínica falha com erro de RLS.
- Sessão sem tenant (`get_db`) enxerga **zero** linhas de tabelas com RLS, porque o predicado resulta em `NULL`.
- `set_config(..., true)` é local à transação. Por isso o listener reaplica o valor a cada `begin`, inclusive depois de um `commit()` no meio do request.

Toda tabela nova de clínica precisa de `TenantMixin` no model **e** de `enable_tenant_rls()` na migração (skill `nova-migracao`). Isso é conferido pelo agente `revisor-tenancy`.

### Autorização

Papéis em `app/core/roles.py`: `admin`, `gestor`, `dentista`, `asb`, `recepcao`. Endpoints usam `require_roles(...)` de `identidade.deps`. Detalhes em [identidade](identidade.md).

### Auditoria

`app.core.audit.record()` adiciona um `AuditLog` à sessão de tenant, e quem chama faz o commit. A tabela é append-only para `odonto_app`. Detalhes em [auditoria](auditoria.md).

### Testes

- Unitários não usam banco. Os de integração (`@pytest.mark.integration`) recriam o schema inteiro (downgrade base → upgrade head) por sessão de testes.
- `clean_db` faz `TRUNCATE` como `odonto` antes de cada teste. Tabela nova precisa entrar nessa lista.
- `make_clinic(role=...)` cria clínica + usuário + vínculo e devolve `(clinic, user, password)`.
