"""Rotas do painel do gestor (só leitura).

- `/painel/visao-geral`: a clínica inteira — admin e gestor.
- `/painel/meu-desempenho`: os próprios números — dentista e admin (o dono-dentista).
- `/painel/equipe`, `/painel/tendencias`, `/painel/metas`: equipe, série mensal e metas —
  admin e gestor (o dentista vê a própria série em `/painel/minha-tendencia`).
- Alertas por regra entram só como contagem (o detalhe com pacientes fica em
  /inteligencia, que é auditado).

Só números agregados: nenhum dado individual de paciente, por isso a leitura não é
auditada (o acesso ao paciente continua pelo prontuário, que é).
"""

import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audit
from app.core.context import CurrentUser
from app.core.roles import Role
from app.modules.identidade.deps import get_tenant_db, require_roles
from app.modules.identidade.models import ClinicMembership, User
from app.modules.inteligencia import service as alerts_service
from app.modules.painel import gestao, service
from app.modules.painel.models import GoalMetric
from app.modules.painel.schemas import (
    AgendaOut,
    AlertsSummaryOut,
    GoalIn,
    GoalOut,
    MonthMetricsOut,
    MyPerformanceOut,
    OverdueOut,
    OverviewOut,
    PayablesOut,
    ProductionOut,
    QuotesOut,
    RevenueOut,
    SettlementBrief,
    StockOut,
    TeamMemberOut,
    TeamOut,
    TrendOut,
    TrendPointOut,
)

router = APIRouter(prefix="/painel", tags=["painel"])

MANAGE = (Role.ADMIN, Role.GESTOR)
CLINICIAN = (Role.ADMIN, Role.DENTISTA)


def _month(mes: str | None) -> date:
    if mes is None:
        return service.today().replace(day=1)
    try:
        year, month = (int(part) for part in mes.split("-"))
        if not gestao.MIN_YEAR <= year <= gestao.MAX_YEAR:
            raise ValueError
        return date(year, month, 1)
    except ValueError:
        raise HTTPException(status_code=422, detail="Mês no formato AAAA-MM.") from None


Month = Query(None, pattern=r"^\d{4}-\d{2}$", description="AAAA-MM (padrão: mês atual).")


def _names(db: Session, clinic_id: uuid.UUID, ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    # `users` e vínculos são globais (sem RLS): só nomes de quem tem vínculo com a clínica.
    query = (
        select(User.id, User.full_name)
        .join(ClinicMembership, ClinicMembership.user_id == User.id)
        .where(User.id.in_(ids), ClinicMembership.clinic_id == clinic_id)
    )
    return dict(db.execute(query).all())


@router.get("/visao-geral", response_model=OverviewOut)
def overview(
    mes: str | None = Month,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    day = service.today()
    month = _month(mes)
    prod = service.production(db, month)
    names = _names(db, user.clinic_id, [p.dentist_id for p in prod])
    return OverviewOut(
        day=day,
        month=month,
        agenda=AgendaOut(**service.agenda_day(db, day).__dict__),
        revenue=RevenueOut(**service.revenue(db, month).__dict__),
        overdue=OverdueOut(**service.overdue_receivables(db, day).__dict__),
        payables=PayablesOut(**service.payables(db, day).__dict__),
        quotes=QuotesOut(**service.quotes(db, month, day).__dict__),
        stock=StockOut(**service.stock_alerts(db, day).__dict__),
        production=sorted(
            (ProductionOut(**p.__dict__, dentist_name=names.get(p.dentist_id)) for p in prod),
            key=lambda p: p.value,
            reverse=True,
        ),
        comparison=_comparison(db, month),
        goals=_goals(db, month, clinic_only=True),
        alerts=_alerts(db, user),
    )


@router.get("/meu-desempenho", response_model=MyPerformanceOut)
def my_performance(
    mes: str | None = Month,
    user: CurrentUser = Depends(require_roles(*CLINICIAN)),
    db: Session = Depends(get_tenant_db),
):
    day = service.today()
    month = _month(mes)
    me = user.user_id
    prod = service.production(db, month, me)
    mine = prod[0] if prod else service.Production(me, 0, service.fin_rules.money(Decimal("0")))
    settlement = service.last_settlement(db, me)
    return MyPerformanceOut(
        dentist_id=me,
        day=day,
        month=month,
        agenda_today=AgendaOut(**service.agenda_day(db, day, me).__dict__),
        encounters=service.encounters_in_month(db, month, me),
        production=ProductionOut(**mine.__dict__),
        quotes=QuotesOut(**service.quotes(db, month, day, me).__dict__),
        last_settlement=(
            SettlementBrief(period_end=settlement.period_end, total=settlement.total)
            if settlement
            else None
        ),
        comparison=_comparison(db, month, me),
        goals=_goals(db, month, dentist_id=me),
        alerts=_alerts(db, user, me),
    )


# ---------- Fase 5.2 ----------


def _metrics_out(m: gestao.MonthMetrics) -> MonthMetricsOut:
    return MonthMetricsOut(**gestao.metrics_dict(m))


def _comparison(db: Session, month: date, dentist_id: uuid.UUID | None = None):
    previous = gestao.fin_rules.add_months(month.replace(day=1), -1)
    return gestao.compare(
        gestao.month_metrics(db, month, dentist_id),
        gestao.month_metrics(db, previous, dentist_id),
    )


def _goal_out(p: gestao.GoalProgress) -> GoalOut:
    g = p.goal
    return GoalOut(
        id=g.id,
        month=g.month,
        metric=g.metric.value,
        dentist_id=g.dentist_id,
        target=g.target,
        achieved=p.achieved,
        pct=p.pct,
    )


def _goals(
    db: Session,
    month: date,
    *,
    dentist_id: uuid.UUID | None = None,
    clinic_only: bool = False,
) -> list[GoalOut]:
    goals = gestao.list_goals(db, month, dentist_id)
    if clinic_only:
        goals = [g for g in goals if g.dentist_id is None]
    metrics = {d: gestao.month_metrics(db, month, d) for d in {g.dentist_id for g in goals}}
    return [_goal_out(p) for p in gestao.progress(goals, metrics)]


def _alerts(db: Session, user: CurrentUser, dentist_id: uuid.UUID | None = None):
    counts = alerts_service.summary(db, user.role, dentist_id)
    return AlertsSummaryOut(total=sum(counts.values()), by_rule=counts)


@router.get("/equipe", response_model=TeamOut)
def team(
    mes: str | None = Month,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    """Comparativo por dentista no mês: produção, orçamentos, agenda e metas."""
    month = _month(mes)
    return TeamOut(
        month=month,
        members=[
            TeamMemberOut(
                dentist_id=m.user_id,
                name=m.name,
                role=m.role.value,
                metrics=_metrics_out(m.metrics),
                goals=[_goal_out(g) for g in m.goals],
            )
            for m in gestao.team(db, user.clinic_id, month)
        ],
    )


Months = Query(6, ge=1, le=gestao.MAX_TREND_MONTHS, description="Quantos meses mostrar.")
Until = Query(None, pattern=r"^\d{4}-\d{2}$", description="Último mês (AAAA-MM).")


def _trend(db: Session, month: date, meses: int, dentist_id: uuid.UUID | None) -> TrendOut:
    return TrendOut(
        dentist_id=dentist_id,
        months=[
            TrendPointOut(metrics=_metrics_out(m), variation_pct=v)
            for m, v in gestao.trend(db, month, meses, dentist_id)
        ],
    )


@router.get("/tendencias", response_model=TrendOut)
def trends(
    ate: str | None = Until,
    meses: int = Months,
    dentista_id: uuid.UUID | None = Query(None, description="Vazio: a clínica inteira."),
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    """Série mensal dos indicadores com a variação contra o mês anterior."""
    if dentista_id is not None and not gestao.is_dentist(db, dentista_id, user.clinic_id):
        raise HTTPException(status_code=422, detail="Dentista não encontrado na clínica.")
    return _trend(db, _month(ate), meses, dentista_id)


@router.get("/minha-tendencia", response_model=TrendOut)
def my_trend(
    ate: str | None = Until,
    meses: int = Months,
    user: CurrentUser = Depends(require_roles(*CLINICIAN)),
    db: Session = Depends(get_tenant_db),
):
    return _trend(db, _month(ate), meses, user.user_id)


@router.get("/metas", response_model=list[GoalOut])
def list_goals(
    mes: str | None = Month,
    _: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    return _goals(db, _month(mes))


def _metric(value: str) -> GoalMetric:
    try:
        return GoalMetric(value)
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Métrica: recebido, producao, procedimentos ou aprovado."
        ) from None


@router.put("/metas", response_model=GoalOut)
def set_goal(
    body: GoalIn,
    request: Request,
    response: Response,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    """Cria ou substitui a meta do mês para a métrica (e o dentista, se informado)."""
    try:
        goal, created = gestao.set_goal(
            db, user, body.month, _metric(body.metric), body.dentist_id, body.target
        )
    except gestao.GoalError as exc:
        raise HTTPException(status_code=422, detail=exc.message) from None
    audit.record(
        db,
        user,
        "painel.meta_definida",
        entity_type="meta",
        entity_id=goal.id,
        details={"mes": goal.month.isoformat(), "metrica": goal.metric.value, "nova": created},
        request=request,
    )
    db.commit()
    if created:
        response.status_code = status.HTTP_201_CREATED
    metrics = {goal.dentist_id: gestao.month_metrics(db, goal.month, goal.dentist_id)}
    return _goal_out(gestao.progress([goal], metrics)[0])


@router.delete("/metas/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_goal(
    goal_id: uuid.UUID,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    try:
        goal = gestao.get_goal(db, goal_id)
    except gestao.GoalNotFound as exc:
        raise HTTPException(status_code=404, detail=exc.message) from None
    details = {"mes": goal.month.isoformat(), "metrica": goal.metric.value}
    gestao.delete_goal(db, goal)
    audit.record(
        db,
        user,
        "painel.meta_removida",
        entity_type="meta",
        entity_id=goal_id,
        details=details,
        request=request,
    )
    db.commit()
