---
name: nova-migracao
description: Escreve uma migração Alembic do backend seguindo o padrão do projeto (RLS por clínica, CHECK de enums, append-only, downgrade). Use ao criar ou alterar tabelas.
---
# Nova migração Alembic

As migrações são **escritas à mão**. Use autogenerate só como conferência, porque ele não gera RLS, CHECKs de enum nem REVOKEs. Referência: `backend/alembic/versions/0001_fundacao.py`.

## Passos

1. Descubra a última revisão: `ls backend/alembic/versions/`. Os IDs são sequenciais com 4 dígitos (`0001`, `0002`...).
2. Crie `backend/alembic/versions/<NNNN>_<descricao_snake>.py` com:
   ```python
   revision: str = "<NNNN>"
   down_revision: str | None = "<NNNN-1>"
   ```
   Docstring em português na primeira linha, descrevendo a mudança.
3. Para cada tabela:
   - `sa.Column("id", sa.Uuid(), primary_key=True)`.
   - Timestamps: copie o helper `_timestamps()` da 0001 para dentro da migração. Não importe de outra migração.
   - Nomes de constraint/índice seguindo a naming convention de `app/core/models.py`: `uq_<tabela>_<coluna>`, `ix_<tabela>_<coluna>`, `fk_<tabela>_<coluna>_<ref>`. Em `CheckConstraint`, passe só o sufixo (`name="role_valid"`), porque a convention acrescenta `ck_<tabela>_`.
   - Enum: coluna `sa.String(N)` + `sa.CheckConstraint("campo IN ('a', 'b')", name="campo_valid")`, com valores vindos de uma tupla na migração (não importe o enum do app, já que a migração precisa ser estável no tempo).
4. **Tabela de clínica** (model com `TenantMixin`):
   ```python
   sa.Column("clinic_id", sa.Uuid(), sa.ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False),
   ...
   op.create_index("ix_<tabela>_clinic_id", "<tabela>", ["clinic_id"])
   for stmt in enable_tenant_rls("<tabela>"):
       op.execute(stmt)
   ```
   Não é preciso GRANT: os default privileges de `docker/postgres/roles.sql` já liberam CRUD ao `odonto_app`.
5. **Append-only** (evolução clínica, históricos): copie o bloco `DO $$ ... REVOKE UPDATE, DELETE, TRUNCATE ... $$` da 0001.
6. **Downgrade** na ordem inversa: `disable_tenant_rls` → `drop_index` (se criado à parte) → `drop_table` (filhas antes das pais).
7. Atualize o model correspondente para bater com a migração e confira:
   ```sh
   cd backend && alembic upgrade head && alembic check && alembic downgrade -1 && alembic upgrade head
   ```
   (precisa de banco; sem banco, peça ao usuário ou deixe para o CI)
8. Inclua a tabela nova no `TRUNCATE` de `clean_db` em `backend/tests/conftest.py`.
9. Acione o agente `revisor-tenancy` para revisar.
