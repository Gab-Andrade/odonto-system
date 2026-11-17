"""Rotas do painel do gestor (só leitura).

- `/painel/visao-geral`: a clínica inteira — admin e gestor.
- `/painel/meu-desempenho`: os próprios números — dentista e admin (o dono-dentista).

Só números agregados: nenhum dado individual de paciente, por isso a leitura não é
auditada (o acesso ao paciente continua pelo prontuário, que é).
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.context import CurrentUser
from app.core.roles import Role
from app.modules.identidade.deps import get_tenant_db, require_roles
from app.modules.identidade.models import ClinicMembership, User
from app.modules.painel import service
from app.modules.painel.schemas import (
    AgendaOut,
    MyPerformanceOut,
    OverdueOut,
    OverviewOut,
    PayablesOut,
    ProductionOut,
    QuotesOut,
    RevenueOut,
    SettlementBrief,
    StockOut,
)

router = APIRouter(prefix="/painel", tags=["painel"])

MANAGE = (Role.ADMIN, Role.GESTOR)
CLINICIAN = (Role.ADMIN, Role.DENTISTA)


def _month(mes: str | None) -> date:
    if mes is None:
        return service.today().replace(day=1)
    try:
        year, month = (int(part) for part in mes.split("-"))
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
    mine = prod[0] if prod else service.Production(me, 0, service.fin_rules.money(0))
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
    )
