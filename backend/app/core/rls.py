"""SQL de Row-Level Security por clínica, usado nas migrações.

Uso numa migração:

    for stmt in enable_tenant_rls("patients"):
        op.execute(stmt)
"""

TENANT_PREDICATE = "clinic_id = NULLIF(current_setting('app.clinic_id', true), '')::uuid"


def enable_tenant_rls(table: str) -> list[str]:
    return [
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        # FORCE: aplica a policy até para o dono da tabela.
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
        f"CREATE POLICY tenant_isolation ON {table} "
        f"USING ({TENANT_PREDICATE}) WITH CHECK ({TENANT_PREDICATE})",
    ]


def disable_tenant_rls(table: str) -> list[str]:
    return [
        f"DROP POLICY IF EXISTS tenant_isolation ON {table}",
        f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY",
    ]
