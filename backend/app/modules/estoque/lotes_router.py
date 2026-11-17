"""Rotas de lotes, movimentos e alertas do estoque.

Papéis: dar entrada e saída — admin, gestor e ASB (quem repõe e confere o material);
ajuste de inventário — admin e gestor; consultar saldos, lotes e alertas — admin, gestor,
dentista e ASB. O custo de lote só aparece para admin e gestor. A baixa por procedimento é
automática (ao realizar um item do plano de tratamento).

LGPD: o rastreio por paciente (que lote foi usado em quem) é auditado.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core import audit
from app.core.context import CurrentUser
from app.core.roles import Role
from app.modules.estoque import lotes_service as lots
from app.modules.estoque import regras
from app.modules.estoque.schemas import (
    AdjustIn,
    EntryIn,
    ExitIn,
    LotOut,
    MovementOut,
    StockOut,
    TraceOut,
)
from app.modules.estoque.service import NotFound, StockError
from app.modules.identidade.deps import get_tenant_db, require_roles
from app.modules.pacientes import service as pacientes_service

router = APIRouter(prefix="/estoque", tags=["estoque"])

READ = (Role.ADMIN, Role.GESTOR, Role.DENTISTA, Role.ASB)
MOVE = (Role.ADMIN, Role.GESTOR, Role.ASB)
MANAGE = (Role.ADMIN, Role.GESTOR)


def _http(exc: StockError) -> HTTPException:
    code = status.HTTP_404_NOT_FOUND if isinstance(exc, NotFound) else 409
    return HTTPException(status_code=code, detail=exc.message)


def _lot_out(user: CurrentUser, lot, balance) -> LotOut:
    out = LotOut.model_validate(lot).model_copy(
        update={
            "balance": balance,
            "expiry": regras.expiry_status(lot.expires_on, lots.today()),
            "unit_cost": lot.unit_cost if user.role in MANAGE else None,
        }
    )
    return out


def _record(db, user, action, request, **fields):
    audit.record(db, user, f"estoque.{action}", request=request, **fields)


@router.post("/entradas", response_model=LotOut, status_code=status.HTTP_201_CREATED)
def register_entry(
    body: EntryIn,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MOVE)),
    db: Session = Depends(get_tenant_db),
):
    try:
        lot = lots.register_entry(db, user, body.model_dump(), can_set_cost=user.role in MANAGE)
    except StockError as exc:
        raise _http(exc) from None
    details = {
        "material": str(lot.material_id),
        "quantidade": str(body.quantity),
        "custo_unitario": str(lot.unit_cost),
    }
    _record(db, user, "entrada", request, entity_type="stock_lot", entity_id=lot.id,
            details=details)  # fmt: skip
    db.commit()
    return _lot_out(user, lot, lots.lot_balance(db, lot))


@router.post("/saidas", response_model=MovementOut, status_code=status.HTTP_201_CREATED)
def register_exit(
    body: ExitIn,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MOVE)),
    db: Session = Depends(get_tenant_db),
):
    try:
        lot = lots.get_lot(db, body.lot_id)
        movement = lots.register_exit(db, user, lot, body.quantity, body.reason)
    except StockError as exc:
        raise _http(exc) from None
    _record(db, user, "saida", request, entity_type="stock_lot", entity_id=lot.id,
            details={"quantidade": str(body.quantity), "motivo": body.reason})  # fmt: skip
    db.commit()
    return movement


@router.post("/ajustes", response_model=MovementOut | None)
def register_adjustment(
    body: AdjustIn,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    """Ajusta o lote para a quantidade contada. Sem diferença, não grava nada (null)."""
    try:
        lot = lots.get_lot(db, body.lot_id)
        movement = lots.register_adjustment(db, user, lot, body.counted_quantity, body.reason)
    except StockError as exc:
        raise _http(exc) from None
    if movement is None:
        return None
    _record(db, user, "ajuste", request, entity_type="stock_lot", entity_id=lot.id,
            details={"diferenca": str(movement.quantity), "motivo": body.reason})  # fmt: skip
    db.commit()
    return movement


@router.get("/saldos", response_model=list[StockOut])
def stock(
    incluir_inativos: bool = False,
    somente_alertas: bool = Query(
        False, description="Só materiais abaixo do mínimo ou com lote vencido/vencendo."
    ),
    user: CurrentUser = Depends(require_roles(*READ)),
    db: Session = Depends(get_tenant_db),
):
    out = []
    day = lots.today()
    for row in lots.stock(db, include_inactive=incluir_inativos):
        lot_outs = [_lot_out(user, lot, bal) for lot, bal in row.lots if bal > 0]
        if somente_alertas:
            expiring = any(
                regras.expiry_status(lot.expires_on, day) in ("vencido", "vence_em_breve")
                for lot in lot_outs
            )
            if not (row.below_minimum or expiring):
                continue
        out.append(
            StockOut(
                material_id=row.material.id,
                name=row.material.name,
                unit=row.material.unit,
                balance=row.balance,
                min_quantity=row.material.min_quantity,
                below_minimum=row.below_minimum,
                lots=lot_outs,
            )
        )
    return out


@router.get("/movimentos", response_model=list[MovementOut])
def list_movements(
    request: Request,
    material_id: uuid.UUID | None = None,
    lote_id: uuid.UUID | None = None,
    limit: int = Query(200, ge=1, le=lots.MAX_LIST),
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    """Movimentos (consumos trazem o paciente: leitura auditada)."""
    rows = lots.movements(db, material_id=material_id, lot_id=lote_id, limit=limit)
    _record(db, user, "movimentos_lidos", request, entity_type="stock_movement",
            details={"resultados": len(rows)})  # fmt: skip
    db.commit()
    return rows


@router.get("/pacientes/{patient_id}/rastreio", response_model=list[TraceOut])
def patient_trace(
    patient_id: uuid.UUID,
    request: Request,
    user: CurrentUser = Depends(require_roles(*READ)),
    db: Session = Depends(get_tenant_db),
):
    """Materiais e lotes usados no paciente (ex.: implante: qual lote, qual validade)."""
    try:
        patient = pacientes_service.get_patient(db, patient_id)
    except pacientes_service.NotFound as exc:
        raise HTTPException(status_code=404, detail=exc.message) from None
    rows = lots.patient_trace(db, patient.id)
    out = [
        TraceOut(
            **MovementOut.model_validate(m).model_dump(),
            material_name=name,
            lot_code=code,
            expires_on=expires,
        )
        for m, name, code, expires in rows
    ]
    _record(db, user, "rastreio_lido", request, entity_type="patient", entity_id=patient.id,
            details={"resultados": len(out)})  # fmt: skip
    db.commit()
    return out
