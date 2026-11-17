---
modulo: auditoria
atualizado_em: 6ad16b3
---
# Auditoria

> Consulta do registro de "quem fez o quê, quando" da clínica (LGPD).

## Responsabilidades

- Expor a leitura do log de auditoria da clínica do usuário (`modules/auditoria/router.py`).

Fora daqui: o model `AuditLog` e a função de gravação `record()` ficam em `app/core/audit.py`, porque todos os módulos gravam auditoria e não devem depender de um módulo de domínio.

## Modelo de dados

| Tabela | Tenant (RLS) | Papel |
|---|---|---|
| `audit_logs` | sim | uma linha por ação: `action`, entidade afetada, IP, user-agent, `details` (JSONB) |

- **Append-only:** a migração 0001 revoga `UPDATE, DELETE, TRUNCATE` de `odonto_app`. Só o role dono consegue limpar a tabela, como a fixture `clean_db` faz.
- `user_id` usa `ondelete="SET NULL"`: o registro sobrevive à remoção do usuário.
- `clinic_id` usa `RESTRICT`: uma clínica com auditoria não pode ser apagada.

## API

| Método | Rota | Papéis | O que faz |
|---|---|---|---|
| GET | `/auditoria?limit=50` | admin, gestor | registros mais recentes da clínica (`limit` de 1 a 500) |

## Regras de negócio e invariantes

- A consulta não filtra `clinic_id` de propósito, porque o RLS restringe à clínica do token. Testado em `tests/test_tenancy_integration.py`.
- `record()` só faz `session.add`. Se quem chama não fizer commit, o registro se perde junto com a transação. Isso é intencional: auditoria e ação são atômicas.

## Tenancy e auditoria

- Usa `get_tenant_db`.
- Convenção de `action`: `<modulo>.<acao>` (ex.: `auth.login`). `entity_type`/`entity_id` identificam o registro afetado, e `details` guarda o contexto extra (nunca senhas ou dados clínicos completos).

## Decisões

| Decisão | Motivo |
|---|---|
| Model e `record()` em `core`, não no módulo | Todos os módulos gravam auditoria, e a dependência fica core ← módulos |
| Append-only garantido por GRANT no banco | Nem um bug na aplicação consegue alterar o histórico |

## Como estender

- **Auditar uma ação nova:** `audit.record(db, user, "<modulo>.<acao>", entity_type="<Model>", entity_id=obj.id, request=request)` antes do `db.commit()`.
- **Filtros na consulta** (por usuário, ação, período): os índices em `user_id`, `action` e `created_at` já existem.

## Armadilhas

- A listagem não tem paginação além de `limit`, então não dá para ler registros antigos que fiquem além dos 500 mais recentes.
- Ações feitas fora de uma sessão de tenant (antes de existir clínica) não têm como ser auditadas, porque `clinic_id` é obrigatório.
