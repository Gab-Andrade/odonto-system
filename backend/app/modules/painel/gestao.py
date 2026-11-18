"""Painel do gestor completo (Fase 5.2): indicadores por mês, tendências, equipe e metas.

Tudo em SQL agregado na sessão de tenant (RLS). Só números: nenhum dado individual de
paciente. Metas são a única escrita do módulo.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.context import CurrentUser
from app.core.roles import Role
from app.modules.agenda.models import Appointment, AppointmentStatus, EntryKind
from app.modules.financeiro import regras as fin_rules
from app.modules.financeiro.models import Payment
from app.modules.identidade.models import ClinicMembership, User
from app.modules.identidade.service import active_role
from app.modules.pacientes.models import Patient
from app.modules.painel import service as base
from app.modules.painel.models import GoalMetric, PanelGoal
from app.modules.prontuario.models import Encounter
from app.modules.tratamento.models import ItemStatus, PlanStatus, TreatmentPlan, TreatmentPlanItem

DENTIST_ROLES = (Role.DENTISTA, Role.ADMIN)  # admin = dono-dentista
MAX_TREND_MONTHS = 24
MIN_YEAR, MAX_YEAR = 2000, 2100  # evita estourar o limite de date nas contas de mês
APPROVED = (PlanStatus.APROVADO, PlanStatus.CONCLUIDO)
DECIDED = (PlanStatus.APROVADO, PlanStatus.CONCLUIDO, PlanStatus.RECUSADO)


class GoalError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class GoalNotFound(GoalError):
    pass


class GoalRuleViolation(GoalError):
    pass


# ---------- regras puras ----------


def variation(current: Decimal | int | None, previous: Decimal | int | None) -> Decimal | None:
    """Variação percentual (uma casa) do mês anterior para o atual; None sem base."""
    if current is None or previous is None or previous == 0:
        return None
    pct = (Decimal(current) - Decimal(previous)) * 100 / Decimal(previous)
    return pct.quantize(Decimal("0.1"))


def ratio_pct(part: int, whole: int) -> Decimal | None:
    if whole == 0:
        return None
    return (Decimal(part) * 100 / Decimal(whole)).quantize(Decimal("0.1"))


def months_back(last: date, count: int) -> list[date]:
    """Os `count` meses terminando em `last` (dia 1), do mais antigo ao mais recente."""
    first = last.replace(day=1)
    return [fin_rules.add_months(first, -i) for i in range(count - 1, -1, -1)]


# ---------- indicadores do mês ----------


@dataclass
class MonthMetrics:
    month: date
    recebido: Decimal | None  # só da clínica
    producao: Decimal
    procedimentos: int
    aprovado: Decimal  # valor dos itens aprovados de orçamentos decididos no mês
    orcamentos_emitidos: int
    orcamentos_decididos: int
    orcamentos_aprovados: int
    conversao_pct: Decimal | None  # aprovados ÷ decididos no mês
    ticket_medio: Decimal | None  # valor aprovado ÷ orçamentos aprovados
    consultas: int  # consultas no mês, sem as canceladas
    faltas: int
    taxa_faltas_pct: Decimal | None  # faltas ÷ (atendidas + faltas)
    atendimentos: int
    novos_pacientes: int | None  # só da clínica

    def value(self, metric: GoalMetric) -> Decimal | None:
        return {
            GoalMetric.RECEBIDO: self.recebido,
            GoalMetric.PRODUCAO: self.producao,
            GoalMetric.PROCEDIMENTOS: Decimal(self.procedimentos),
            GoalMetric.APROVADO: self.aprovado,
        }[metric]


def _between(column, first: date, nxt: date):
    return (column >= base._instant(first)) & (column < base._instant(nxt))


def month_metrics(db: Session, month: date, dentist_id: uuid.UUID | None = None) -> MonthMetrics:
    first, nxt = base.month_bounds(month)
    prod = base.production(db, first, dentist_id)
    procedures = sum(p.procedures for p in prod)
    produced = base._money(sum((p.value for p in prod), Decimal("0")))

    plans = select(TreatmentPlan)
    if dentist_id is not None:
        plans = plans.where(TreatmentPlan.dentist_id == dentist_id)
    p = plans.subquery()
    issued = db.scalar(
        select(func.count()).select_from(p).where(_between(p.c.issued_at, first, nxt))
    )
    decided_rows = dict(
        db.execute(
            select(p.c.status, func.count())
            .where(_between(p.c.decided_at, first, nxt), p.c.status.in_([s.value for s in DECIDED]))
            .group_by(p.c.status)
        ).all()
    )
    decided = sum(decided_rows.values())
    approved = sum(n for s, n in decided_rows.items() if s in APPROVED)
    approved_value = db.scalar(
        select(func.sum(TreatmentPlanItem.unit_price))
        .join(p, p.c.id == TreatmentPlanItem.plan_id)
        .where(
            _between(p.c.decided_at, first, nxt),
            p.c.status.in_([s.value for s in APPROVED]),
            TreatmentPlanItem.status.in_((ItemStatus.APROVADO, ItemStatus.REALIZADO)),
        )
    )
    approved_value = base._money(approved_value)

    appts = select(Appointment.status, func.count()).where(
        Appointment.kind == EntryKind.CONSULTA, _between(Appointment.starts_at, first, nxt)
    )
    if dentist_id is not None:
        appts = appts.where(Appointment.dentist_id == dentist_id)
    by_status = dict(db.execute(appts.group_by(Appointment.status)).all())
    S = AppointmentStatus
    consultas = sum(n for s, n in by_status.items() if s != S.CANCELADO)
    faltas = by_status.get(S.FALTA, 0)

    enc = select(func.count()).where(_between(Encounter.started_at, first, nxt))
    if dentist_id is not None:
        enc = enc.where(Encounter.dentist_id == dentist_id)

    recebido = novos = None
    if dentist_id is None:
        recebido = base._money(
            db.scalar(
                select(func.sum(Payment.amount)).where(
                    Payment.paid_on >= first, Payment.paid_on < nxt
                )
            )
        )
        novos = db.scalar(select(func.count()).where(_between(Patient.created_at, first, nxt))) or 0

    return MonthMetrics(
        month=first,
        recebido=recebido,
        producao=produced,
        procedimentos=procedures,
        aprovado=approved_value,
        orcamentos_emitidos=issued or 0,
        orcamentos_decididos=decided,
        orcamentos_aprovados=approved,
        conversao_pct=ratio_pct(approved, decided),
        ticket_medio=base._money(approved_value / approved) if approved else None,
        consultas=consultas,
        faltas=faltas,
        taxa_faltas_pct=ratio_pct(faltas, by_status.get(S.ATENDIDO, 0) + faltas),
        atendimentos=db.scalar(enc) or 0,
        novos_pacientes=novos,
    )


COMPARED = (
    "recebido",
    "producao",
    "procedimentos",
    "aprovado",
    "orcamentos_emitidos",
    "consultas",
    "faltas",
    "atendimentos",
    "novos_pacientes",
)


def compare(current: MonthMetrics, previous: MonthMetrics) -> dict[str, Decimal | None]:
    """Variação % de cada indicador contra o mês anterior."""
    return {k: variation(getattr(current, k), getattr(previous, k)) for k in COMPARED}


def trend(
    db: Session, last: date, count: int, dentist_id: uuid.UUID | None = None
) -> list[tuple[MonthMetrics, dict[str, Decimal | None]]]:
    """Série mensal com a variação de cada mês contra o anterior."""
    count = max(1, min(count, MAX_TREND_MONTHS))
    months = months_back(last, count + 1)  # um a mais, para a variação do primeiro
    series = [month_metrics(db, m, dentist_id) for m in months]
    return [(series[i], compare(series[i], series[i - 1])) for i in range(1, len(series))]


# ---------- metas ----------


def is_dentist(db: Session, user_id: uuid.UUID, clinic_id: uuid.UUID) -> bool:
    return active_role(db, user_id, clinic_id) in DENTIST_ROLES


@dataclass
class GoalProgress:
    goal: PanelGoal
    achieved: Decimal | None
    pct: Decimal | None


def list_goals(db: Session, month: date, dentist_id: uuid.UUID | None = None) -> list[PanelGoal]:
    query = select(PanelGoal).where(PanelGoal.month == month.replace(day=1))
    if dentist_id is not None:
        query = query.where(PanelGoal.dentist_id == dentist_id)
    return list(db.scalars(query.order_by(PanelGoal.dentist_id.nulls_first(), PanelGoal.metric)))


def set_goal(
    db: Session,
    user: CurrentUser,
    month: date,
    metric: GoalMetric,
    dentist_id: uuid.UUID | None,
    target: Decimal,
) -> tuple[PanelGoal, bool]:
    """Cria ou atualiza a meta do mês. Devolve (meta, criada)."""
    if target <= 0:
        raise GoalRuleViolation("A meta precisa ser maior que zero.")
    if metric == GoalMetric.RECEBIDO and dentist_id is not None:
        raise GoalRuleViolation("Meta de recebido é só da clínica (recebimento não tem dentista).")
    if metric == GoalMetric.PROCEDIMENTOS and target != target.to_integral_value():
        raise GoalRuleViolation("Meta de procedimentos é um número inteiro.")
    if not MIN_YEAR <= month.year <= MAX_YEAR:
        raise GoalRuleViolation(f"Mês fora do intervalo ({MIN_YEAR} a {MAX_YEAR}).")
    if dentist_id is not None and not is_dentist(db, dentist_id, user.clinic_id):
        raise GoalRuleViolation("Dentista não encontrado na clínica.")
    month = month.replace(day=1)
    query = select(PanelGoal).where(PanelGoal.month == month, PanelGoal.metric == metric)
    query = query.where(
        PanelGoal.dentist_id.is_(None) if dentist_id is None else PanelGoal.dentist_id == dentist_id
    )
    goal = db.scalar(query.with_for_update())
    created = goal is None
    if goal is None:
        goal = PanelGoal(
            clinic_id=user.clinic_id, month=month, metric=metric, dentist_id=dentist_id
        )
        db.add(goal)
    goal.target = target
    goal.updated_by = user.user_id
    db.flush()
    db.refresh(goal)
    return goal, created


def get_goal(db: Session, goal_id: uuid.UUID) -> PanelGoal:
    goal = db.get(PanelGoal, goal_id)
    if goal is None:
        raise GoalNotFound("Meta não encontrada.")
    return goal


def delete_goal(db: Session, goal: PanelGoal) -> None:
    db.delete(goal)
    db.flush()


def progress(
    goals: list[PanelGoal], metrics: dict[uuid.UUID | None, MonthMetrics]
) -> list[GoalProgress]:
    result = []
    for goal in goals:
        m = metrics.get(goal.dentist_id)
        achieved = m.value(goal.metric) if m else None
        pct = ratio_pct_decimal(achieved, goal.target)
        result.append(GoalProgress(goal, achieved, pct))
    return result


def ratio_pct_decimal(part: Decimal | None, whole: Decimal) -> Decimal | None:
    if part is None or not whole:
        return None
    return (part * 100 / whole).quantize(Decimal("0.1"))


# ---------- equipe ----------


@dataclass
class Member:
    user_id: uuid.UUID
    name: str
    role: Role
    metrics: MonthMetrics
    goals: list[GoalProgress] = field(default_factory=list)


def dentists(db: Session, clinic_id: uuid.UUID) -> list[tuple[uuid.UUID, str, Role]]:
    """Dentistas e admins ativos da clínica (tabelas globais: filtro explícito)."""
    rows = db.execute(
        select(User.id, User.full_name, ClinicMembership.role)
        .join(ClinicMembership, ClinicMembership.user_id == User.id)
        .where(
            ClinicMembership.clinic_id == clinic_id,
            ClinicMembership.active,
            User.active,
            ClinicMembership.role.in_(DENTIST_ROLES),
        )
        .order_by(User.full_name)
    ).all()
    return [(i, n, r) for i, n, r in rows]


def team(db: Session, clinic_id: uuid.UUID, month: date) -> list[Member]:
    goals = list_goals(db, month)
    members = []
    for user_id, name, role in dentists(db, clinic_id):
        metrics = month_metrics(db, month, user_id)
        mine = [g for g in goals if g.dentist_id == user_id]
        members.append(Member(user_id, name, role, metrics, progress(mine, {user_id: metrics})))
    # Dentista que saiu mas produziu no mês continua no comparativo.
    known = {m.user_id for m in members}
    for p in base.production(db, month):
        if p.dentist_id is not None and p.dentist_id not in known:
            name = db.scalar(
                select(User.full_name)
                .join(ClinicMembership, ClinicMembership.user_id == User.id)
                .where(User.id == p.dentist_id, ClinicMembership.clinic_id == clinic_id)
            )
            metrics = month_metrics(db, month, p.dentist_id)
            members.append(Member(p.dentist_id, name or "(sem vínculo)", Role.DENTISTA, metrics))
    return members


def metrics_dict(m: MonthMetrics) -> dict[str, Any]:
    return dict(m.__dict__)
