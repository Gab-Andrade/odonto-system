"""Rotas do repasse de dentistas.

Papéis: regras, prévia e fechamento — admin e gestor. O dentista vê só os próprios
fechamentos e a própria prévia ("meu repasse"). Recepção e ASB não acessam.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core import audit
from app.core.context import CurrentUser
from app.core.roles import Role
from app.modules.identidade.deps import get_tenant_db, require_roles
from app.modules.repasse import service
from app.modules.repasse.schemas import (
    CloseIn,
    LineOut,
    PreviewOut,
    RuleIn,
    RuleOut,
    SettlementDetail,
    SettlementOut,
)

router = APIRouter(prefix="/repasse", tags=["repasse"])

MANAGE = (Role.ADMIN, Role.GESTOR)
VIEW = (Role.ADMIN, Role.GESTOR, Role.DENTISTA)


def _http(exc: service.CommissionError) -> HTTPException:
    code = status.HTTP_404_NOT_FOUND if isinstance(exc, service.NotFound) else 409
    return HTTPException(status_code=code, detail=exc.message)


def _scope(user: CurrentUser, dentist_id: uuid.UUID | None) -> uuid.UUID | None:
    """Dentista só enxerga o próprio repasse."""
    if user.role in MANAGE:
        return dentist_id
    if dentist_id is not None and dentist_id != user.user_id:
        raise HTTPException(status_code=403, detail="Sem permissão")
    return user.user_id


def _preview_out(p: service.Preview) -> PreviewOut:
    return PreviewOut(
        dentist_id=p.dentist_id,
        period_start=p.period_start,
        period_end=p.period_end,
        total=p.total,
        missing_rule=p.missing_rule,
        lines=[
            LineOut(
                plan_item_id=line.item.id,
                procedure_code=line.item.procedure_code,
                base_amount=line.line.base,
                fee_deduction=line.line.fee_deduction,
                material_deduction=line.line.material_deduction,
                rule_id=line.rule.id,
                commission=line.line.commission,
            )
            for line in p.lines
        ],
    )


@router.get("/regras", response_model=list[RuleOut])
def list_rules(
    dentista_id: uuid.UUID | None = None,
    user: CurrentUser = Depends(require_roles(*VIEW)),
    db: Session = Depends(get_tenant_db),
):
    return service.list_rules(db, _scope(user, dentista_id))


@router.post("/regras", response_model=RuleOut, status_code=status.HTTP_201_CREATED)
def create_rule(
    body: RuleIn,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    try:
        rule = service.create_rule(db, user, body.model_dump())
    except service.CommissionError as exc:
        raise _http(exc) from None
    audit.record(
        db, user, "repasse.regra_criada", entity_type="commission_rule", entity_id=rule.id,
        details=body.model_dump(mode="json"), request=request,
    )  # fmt: skip
    db.commit()
    return rule


@router.get("/previa", response_model=PreviewOut)
def preview(
    ate: date,
    dentista_id: uuid.UUID | None = None,
    user: CurrentUser = Depends(require_roles(*VIEW)),
    db: Session = Depends(get_tenant_db),
):
    """Quanto o dentista receberia num fechamento até `ate` (não grava nada)."""
    dentist_id = _scope(user, dentista_id)
    if dentist_id is None:
        raise HTTPException(status_code=422, detail="Informe o dentista.")
    try:
        if user.role in MANAGE:
            service.ensure_dentist(db, user, dentist_id)
        return _preview_out(service.compute(db, dentist_id, ate))
    except service.CommissionError as exc:
        raise _http(exc) from None


@router.post("/fechamentos", response_model=SettlementDetail, status_code=201)
def close(
    body: CloseIn,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    try:
        settlement, preview = service.close(db, user, body.dentist_id, body.period_end, body.notes)
    except service.CommissionError as exc:
        raise _http(exc) from None
    audit.record(
        db, user, "repasse.fechamento", entity_type="commission_settlement",
        entity_id=settlement.id,
        details={"dentista": str(body.dentist_id), "ate": str(body.period_end),
                 "total": str(settlement.total), "itens": len(preview.lines)},
        request=request,
    )  # fmt: skip
    db.commit()
    out = _preview_out(preview)
    return SettlementDetail(
        **SettlementOut.model_validate(settlement).model_dump(), lines=out.lines
    )


@router.get("/fechamentos", response_model=list[SettlementOut])
def list_settlements(
    dentista_id: uuid.UUID | None = None,
    user: CurrentUser = Depends(require_roles(*VIEW)),
    db: Session = Depends(get_tenant_db),
):
    return service.list_settlements(db, _scope(user, dentista_id))


@router.get("/fechamentos/{settlement_id}", response_model=SettlementDetail)
def get_settlement(
    settlement_id: uuid.UUID,
    user: CurrentUser = Depends(require_roles(*VIEW)),
    db: Session = Depends(get_tenant_db),
):
    try:
        settlement = service.get_settlement(db, settlement_id)
    except service.CommissionError as exc:
        raise _http(exc) from None
    _scope(user, settlement.dentist_id)
    lines = [
        LineOut.model_validate(line, from_attributes=True)
        for line in service.settlement_lines(db, settlement)
    ]
    return SettlementDetail(**SettlementOut.model_validate(settlement).model_dump(), lines=lines)
