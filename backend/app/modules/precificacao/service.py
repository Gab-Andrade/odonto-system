"""Regras de negócio da precificação (entrega 1: tabelas fixas, herança, atribuição, resolução).

Resolução do preço de um procedimento:
1. Coleta as atribuições que se aplicam ao contexto (clínica sempre; dentista e convênio se
   informados), de tabelas ativas, ordenadas por prioridade (menor vence).
2. Para cada tabela candidata, pega a versão vigente na data e procura o procedimento:
   - item próprio da versão → preço do item;
   - senão, se a tabela herda de outra → preço resolvido na tabela-pai (mesma data)
     com o ajuste percentual da versão, arredondado em centavos;
   - senão → passa para a próxima candidata.
3. A primeira que encontrar vence. A memória de cálculo registra todas as tentativas.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.context import CurrentUser
from app.core.roles import Role
from app.modules.identidade.service import active_role
from app.modules.precificacao.models import (
    PriceAssignment,
    PriceItem,
    PriceSnapshot,
    PriceTable,
    PriceTableVersion,
    ScopeType,
    TableStatus,
    VersionStatus,
)

CENTS = Decimal("0.01")
MAX_PRICE = Decimal("9999999999.99")  # limite de Numeric(12,2)
# Quem pode ter tabela de preço própria como "dentista" (o admin costuma ser o dono-dentista).
DENTIST_ROLES = frozenset({Role.DENTISTA, Role.ADMIN})
MAX_INHERITANCE_DEPTH = 10
DEFAULT_PRIORITY = {ScopeType.CONVENIO: 10, ScopeType.DENTISTA: 20, ScopeType.CLINICA: 30}


# ---------- Exceções de domínio ----------


class PricingError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFound(PricingError):
    pass


class RuleViolation(PricingError):
    pass


class PriceNotFound(PricingError):
    def __init__(self, message: str, trace: list[dict[str, Any]]):
        super().__init__(message)
        self.trace = trace


# ---------- Funções puras ----------


def today() -> date:
    return datetime.now(ZoneInfo(get_settings().clinic_timezone)).date()


def apply_adjustment(price: Decimal, pct: Decimal | None) -> Decimal:
    """Aplica o ajuste percentual e arredonda em centavos (meio para cima)."""
    if pct is None:
        return price.quantize(CENTS, rounding=ROUND_HALF_UP)
    return (price * (Decimal(100) + pct) / Decimal(100)).quantize(CENTS, rounding=ROUND_HALF_UP)


def ensure_dentist(db: Session, user: CurrentUser, dentist_id: uuid.UUID) -> None:
    if active_role(db, dentist_id, user.clinic_id) not in DENTIST_ROLES:
        raise RuleViolation("O dentista informado não tem vínculo ativo de dentista nesta clínica.")


def check_valid_from(valid_from: date, today_: date, last_published: date | None) -> None:
    """Uma versão não pode valer no passado nem antes da última versão publicada."""
    if valid_from < today_:
        raise RuleViolation("A vigência não pode começar no passado.")
    if last_published is not None and valid_from < last_published:
        raise RuleViolation(
            f"A vigência não pode começar antes da última versão publicada ({last_published})."
        )


# ---------- Tabelas ----------


def list_tables(db: Session) -> list[PriceTable]:
    return list(db.scalars(select(PriceTable).order_by(PriceTable.name)))


def get_table(db: Session, table_id: uuid.UUID) -> PriceTable:
    table = db.get(PriceTable, table_id)  # o RLS esconde tabelas de outras clínicas
    if table is None:
        raise NotFound("Tabela de preço não encontrada.")
    return table


def _ensure_unique_name(db: Session, name: str, exclude_id: uuid.UUID | None = None) -> None:
    stmt = select(PriceTable.id).where(func.lower(PriceTable.name) == name.lower())
    if exclude_id is not None:
        stmt = stmt.where(PriceTable.id != exclude_id)
    if db.scalar(stmt) is not None:
        raise RuleViolation(f"Já existe uma tabela chamada '{name}'.")


def create_table(
    db: Session,
    user: CurrentUser,
    *,
    name: str,
    description: str | None,
    parent_table_id: uuid.UUID | None,
    adjustment_pct: Decimal | None,
) -> tuple[PriceTable, PriceTableVersion]:
    """Cria a tabela e já abre a versão 1 como rascunho."""
    _ensure_unique_name(db, name)
    if parent_table_id is not None:
        parent = get_table(db, parent_table_id)
        if parent.status != TableStatus.ATIVA:
            raise RuleViolation("A tabela-pai está arquivada.")
    elif adjustment_pct is not None:
        raise RuleViolation("Ajuste percentual só se aplica a tabelas que herdam de outra.")

    table = PriceTable(
        clinic_id=user.clinic_id,
        name=name,
        description=description,
        parent_table_id=parent_table_id,
    )
    db.add(table)
    db.flush()
    draft = PriceTableVersion(
        clinic_id=user.clinic_id,
        table_id=table.id,
        version=1,
        adjustment_pct=adjustment_pct,
    )
    db.add(draft)
    db.flush()
    return table, draft


def update_table(db: Session, table: PriceTable, changes: dict[str, Any]) -> PriceTable:
    if "name" in changes and changes["name"] is not None:
        _ensure_unique_name(db, changes["name"], exclude_id=table.id)
        table.name = changes["name"]
    if "description" in changes:
        table.description = changes["description"]
    if changes.get("status") == TableStatus.ARQUIVADA and table.status != TableStatus.ARQUIVADA:
        _ensure_can_archive(db, table)
        table.status = TableStatus.ARQUIVADA
    elif changes.get("status") == TableStatus.ATIVA and table.status != TableStatus.ATIVA:
        if table.parent_table_id is not None:
            parent = db.get(PriceTable, table.parent_table_id)
            if parent is None or parent.status != TableStatus.ATIVA:
                raise RuleViolation("A tabela-pai está arquivada; reative-a antes.")
        table.status = TableStatus.ATIVA
    db.flush()
    return table


def _ensure_can_archive(db: Session, table: PriceTable) -> None:
    active_child = db.scalar(
        select(PriceTable.name).where(
            PriceTable.parent_table_id == table.id, PriceTable.status == TableStatus.ATIVA
        )
    )
    if active_child is not None:
        raise RuleViolation(f"A tabela '{active_child}' herda desta; arquive-a antes.")
    if db.scalar(select(PriceAssignment.id).where(PriceAssignment.table_id == table.id)):
        raise RuleViolation("Remova as atribuições desta tabela antes de arquivá-la.")


# ---------- Versões ----------


def list_versions(db: Session, table: PriceTable) -> list[PriceTableVersion]:
    return list(
        db.scalars(
            select(PriceTableVersion)
            .where(PriceTableVersion.table_id == table.id)
            .order_by(PriceTableVersion.version.desc())
        )
    )


def get_version(db: Session, table: PriceTable, version_id: uuid.UUID) -> PriceTableVersion:
    version = db.get(PriceTableVersion, version_id)
    if version is None or version.table_id != table.id:
        raise NotFound("Versão não encontrada.")
    return version


def _ensure_draft(version: PriceTableVersion) -> None:
    if version.status != VersionStatus.RASCUNHO:
        raise RuleViolation("Versão publicada não pode ser alterada. Crie uma nova versão.")


def _last_published(db: Session, table_id: uuid.UUID) -> PriceTableVersion | None:
    return db.scalar(
        select(PriceTableVersion)
        .where(
            PriceTableVersion.table_id == table_id,
            PriceTableVersion.status == VersionStatus.PUBLICADA,
        )
        .order_by(PriceTableVersion.valid_from.desc(), PriceTableVersion.version.desc())
        .limit(1)
    )


def create_draft(db: Session, user: CurrentUser, table: PriceTable) -> PriceTableVersion:
    """Abre um rascunho copiando a última versão publicada (itens e ajuste)."""
    existing = db.scalar(
        select(PriceTableVersion.version).where(
            PriceTableVersion.table_id == table.id,
            PriceTableVersion.status == VersionStatus.RASCUNHO,
        )
    )
    if existing is not None:
        raise RuleViolation(f"A versão {existing} já está em rascunho.")

    next_number = (
        db.scalar(
            select(func.max(PriceTableVersion.version)).where(
                PriceTableVersion.table_id == table.id
            )
        )
        or 0
    ) + 1
    base = _last_published(db, table.id)
    draft = PriceTableVersion(
        clinic_id=user.clinic_id,
        table_id=table.id,
        version=next_number,
        adjustment_pct=base.adjustment_pct if base else None,
    )
    db.add(draft)
    db.flush()
    if base is not None:
        for item in list_items(db, base):
            db.add(
                PriceItem(
                    clinic_id=user.clinic_id,
                    version_id=draft.id,
                    procedure_code=item.procedure_code,
                    description=item.description,
                    category=item.category,
                    price=item.price,
                )
            )
        db.flush()
    return draft


def update_draft(
    db: Session, table: PriceTable, version: PriceTableVersion, changes: dict[str, Any]
) -> PriceTableVersion:
    _ensure_draft(version)
    if "adjustment_pct" in changes:
        if changes["adjustment_pct"] is not None and table.parent_table_id is None:
            raise RuleViolation("Ajuste percentual só se aplica a tabelas que herdam de outra.")
        version.adjustment_pct = changes["adjustment_pct"]
    db.flush()
    return version


def list_items(db: Session, version: PriceTableVersion) -> list[PriceItem]:
    return list(
        db.scalars(
            select(PriceItem)
            .where(PriceItem.version_id == version.id)
            .order_by(PriceItem.procedure_code)
        )
    )


def replace_items(
    db: Session, user: CurrentUser, version: PriceTableVersion, items: list[dict[str, Any]]
) -> list[PriceItem]:
    """Substitui todos os itens do rascunho (é o mesmo fluxo que a importação vai usar)."""
    _ensure_draft(version)
    db.execute(delete(PriceItem).where(PriceItem.version_id == version.id))
    new_items = [PriceItem(clinic_id=user.clinic_id, version_id=version.id, **i) for i in items]
    db.add_all(new_items)
    db.flush()
    return new_items


def publish(
    db: Session,
    user: CurrentUser,
    table: PriceTable,
    version: PriceTableVersion,
    valid_from: date | None,
) -> PriceTableVersion:
    _ensure_draft(version)
    if table.status != TableStatus.ATIVA:
        raise RuleViolation("Tabela arquivada não pode publicar versões.")
    if table.parent_table_id is None and not list_items(db, version):
        raise RuleViolation("A versão não tem itens.")

    start = valid_from or today()
    last = _last_published(db, table.id)
    check_valid_from(start, today(), last.valid_from if last else None)

    version.status = VersionStatus.PUBLICADA
    version.valid_from = start
    version.published_at = datetime.now(UTC)
    version.published_by = user.user_id
    db.flush()
    return version


def effective_version(db: Session, table_id: uuid.UUID, on: date) -> PriceTableVersion | None:
    """Versão publicada vigente na data (a de início mais recente; empate → maior número)."""
    return db.scalar(
        select(PriceTableVersion)
        .where(
            PriceTableVersion.table_id == table_id,
            PriceTableVersion.status == VersionStatus.PUBLICADA,
            PriceTableVersion.valid_from <= on,
        )
        .order_by(PriceTableVersion.valid_from.desc(), PriceTableVersion.version.desc())
        .limit(1)
    )


# ---------- Atribuições ----------


def list_assignments(db: Session) -> list[PriceAssignment]:
    return list(
        db.scalars(
            select(PriceAssignment).order_by(PriceAssignment.priority, PriceAssignment.created_at)
        )
    )


def get_assignment(db: Session, assignment_id: uuid.UUID) -> PriceAssignment:
    assignment = db.get(PriceAssignment, assignment_id)
    if assignment is None:
        raise NotFound("Atribuição não encontrada.")
    return assignment


def create_assignment(
    db: Session,
    user: CurrentUser,
    *,
    table_id: uuid.UUID,
    scope_type: ScopeType,
    scope_id: uuid.UUID | None,
    priority: int | None,
) -> PriceAssignment:
    table = get_table(db, table_id)
    if table.status != TableStatus.ATIVA:
        raise RuleViolation("Tabela arquivada não pode ser atribuída.")

    if scope_type == ScopeType.CLINICA:
        if scope_id is not None:
            raise RuleViolation("Atribuição à clínica não leva scope_id.")
    elif scope_id is None:
        raise RuleViolation("Informe o scope_id do dentista ou convênio.")
    # Convênios ainda não têm cadastro próprio; a validação entra junto com o módulo.
    if scope_type == ScopeType.DENTISTA:
        ensure_dentist(db, user, scope_id)

    duplicate = db.scalar(
        select(PriceAssignment.id).where(
            PriceAssignment.table_id == table_id,
            PriceAssignment.scope_type == scope_type,
            PriceAssignment.scope_id.is_(None)
            if scope_id is None
            else PriceAssignment.scope_id == scope_id,
        )
    )
    if duplicate is not None:
        raise RuleViolation("Esta tabela já está atribuída a este escopo.")

    assignment = PriceAssignment(
        clinic_id=user.clinic_id,
        table_id=table_id,
        scope_type=scope_type,
        scope_id=scope_id,
        priority=priority if priority is not None else DEFAULT_PRIORITY[scope_type],
    )
    db.add(assignment)
    db.flush()
    return assignment


def delete_assignment(db: Session, assignment: PriceAssignment) -> None:
    db.delete(assignment)
    db.flush()


# ---------- Resolução ----------


@dataclass
class Resolution:
    procedure_code: str
    description: str
    category: str | None
    price: Decimal
    table_id: uuid.UUID
    version_id: uuid.UUID
    effective_on: date
    trace: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class _Found:
    price: Decimal
    description: str
    category: str | None
    version_id: uuid.UUID
    steps: list[dict[str, Any]]


def _resolve_in_table(
    db: Session, table: PriceTable, code: str, on: date, depth: int = 0
) -> tuple[_Found | None, str]:
    if depth > MAX_INHERITANCE_DEPTH:
        return None, "herança profunda demais"
    version = effective_version(db, table.id, on)
    if version is None:
        return None, "sem versão vigente na data"

    item = db.scalar(
        select(PriceItem).where(
            PriceItem.version_id == version.id, PriceItem.procedure_code == code
        )
    )
    if item is not None:
        step = {
            "tabela": table.name,
            "tabela_id": str(table.id),
            "versao": version.version,
            "origem": "item da tabela",
            "valor": str(item.price),
        }
        return _Found(item.price, item.description, item.category, version.id, [step]), "ok"

    if table.parent_table_id is None:
        return None, "procedimento ausente na tabela"

    parent = db.get(PriceTable, table.parent_table_id)
    if parent is None or parent.status != TableStatus.ATIVA:
        return None, "tabela-pai indisponível ou arquivada"
    found, reason = _resolve_in_table(db, parent, code, on, depth + 1)
    if found is None:
        return None, f"procedimento ausente na tabela e na tabela-pai ({reason})"

    price = apply_adjustment(found.price, version.adjustment_pct)
    if price > MAX_PRICE:
        return None, "valor herdado com ajuste excede o limite permitido"
    step = {
        "tabela": table.name,
        "tabela_id": str(table.id),
        "versao": version.version,
        "origem": f"herdado de '{parent.name}'",
        "ajuste_pct": str(version.adjustment_pct) if version.adjustment_pct is not None else None,
        "valor": str(price),
    }
    # O preço é desta versão; descrição e categoria vêm do item original.
    return (
        _Found(price, found.description, found.category, version.id, [*found.steps, step]),
        "ok",
    )


def resolve(
    db: Session,
    *,
    procedure_code: str,
    dentist_id: uuid.UUID | None = None,
    insurer_id: uuid.UUID | None = None,
    on: date | None = None,
) -> Resolution:
    on = on or today()
    scopes = [PriceAssignment.scope_type == ScopeType.CLINICA]
    if dentist_id is not None:
        scopes.append(
            (PriceAssignment.scope_type == ScopeType.DENTISTA)
            & (PriceAssignment.scope_id == dentist_id)
        )
    if insurer_id is not None:
        scopes.append(
            (PriceAssignment.scope_type == ScopeType.CONVENIO)
            & (PriceAssignment.scope_id == insurer_id)
        )

    candidates = db.execute(
        select(PriceAssignment, PriceTable)
        .join(PriceTable, PriceTable.id == PriceAssignment.table_id)
        .where(or_(*scopes), PriceTable.status == TableStatus.ATIVA)
        .order_by(PriceAssignment.priority, PriceAssignment.created_at)
    ).all()

    trace: list[dict[str, Any]] = []
    for assignment, table in candidates:
        found, reason = _resolve_in_table(db, table, procedure_code, on)
        attempt: dict[str, Any] = {
            "tabela": table.name,
            "tabela_id": str(table.id),
            "escopo": assignment.scope_type.value,
            "prioridade": assignment.priority,
            "resultado": "encontrado" if found else reason,
        }
        if found is None:
            trace.append(attempt)
            continue
        attempt["calculo"] = found.steps
        trace.append(attempt)
        return Resolution(
            procedure_code=procedure_code,
            description=found.description,
            category=found.category,
            price=found.price,
            table_id=table.id,
            version_id=found.version_id,
            effective_on=on,
            trace=trace,
        )

    if not candidates:
        raise PriceNotFound("Nenhuma tabela de preço atribuída para este contexto.", trace)
    raise PriceNotFound(
        f"Procedimento '{procedure_code}' não encontrado nas tabelas aplicáveis.", trace
    )


def freeze(
    db: Session,
    user: CurrentUser,
    resolution: Resolution,
    *,
    dentist_id: uuid.UUID | None,
    insurer_id: uuid.UUID | None,
) -> PriceSnapshot:
    # O snapshot é imutável: não pode guardar referência a dentista de outra clínica.
    if dentist_id is not None:
        ensure_dentist(db, user, dentist_id)
    snapshot = PriceSnapshot(
        clinic_id=user.clinic_id,
        procedure_code=resolution.procedure_code,
        description=resolution.description,
        category=resolution.category,
        price=resolution.price,
        table_id=resolution.table_id,
        version_id=resolution.version_id,
        dentist_id=dentist_id,
        insurer_id=insurer_id,
        effective_on=resolution.effective_on,
        trace=resolution.trace,
        created_by=user.user_id,
    )
    db.add(snapshot)
    db.flush()
    return snapshot


def get_snapshot(db: Session, snapshot_id: uuid.UUID) -> PriceSnapshot:
    snapshot = db.get(PriceSnapshot, snapshot_id)
    if snapshot is None:
        raise NotFound("Snapshot de preço não encontrado.")
    return snapshot
