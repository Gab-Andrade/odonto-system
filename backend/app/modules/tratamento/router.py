"""Rotas do plano de tratamento e orçamento.

Papéis:
- montar o plano (itens, responsável): dentista e admin;
- desconto, emitir, registrar a decisão do paciente e cancelar: dentista, admin, gestor e
  recepção (desconto acima do limite da clínica: só admin e gestor);
- realizar item: o dentista do atendimento; cancelar item aprovado: dentista, admin, gestor;
- ler: toda a equipe (a recepção negocia o orçamento). Leitura de plano é auditada (LGPD).
- configuração (validade e desconto máximo): admin e gestor.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core import audit
from app.core.context import CurrentUser
from app.core.roles import Role
from app.modules.identidade.deps import get_tenant_db, require_roles
from app.modules.tratamento import regras, service
from app.modules.tratamento.models import PlanStatus, TreatmentPlan
from app.modules.tratamento.schemas import (
    DecisionIn,
    DiscountIn,
    ItemIn,
    ItemOut,
    ItemUpdate,
    PerformIn,
    PlanCreate,
    PlanOut,
    PlanSummary,
    PlanUpdate,
    ReasonIn,
    SettingsIn,
    SettingsOut,
    TotalsOut,
)

router = APIRouter(prefix="/tratamento", tags=["tratamento"])

ALL = (Role.ADMIN, Role.GESTOR, Role.DENTISTA, Role.ASB, Role.RECEPCAO)
PLAN = (Role.ADMIN, Role.DENTISTA)
SELL = (Role.ADMIN, Role.GESTOR, Role.DENTISTA, Role.RECEPCAO)
MANAGE = (Role.ADMIN, Role.GESTOR)
CANCEL_ITEM = (Role.ADMIN, Role.GESTOR, Role.DENTISTA)


def _http(exc: service.TreatmentError) -> HTTPException:
    if isinstance(exc, service.NotFound):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, service.Forbidden):
        code = status.HTTP_403_FORBIDDEN
    else:
        code = status.HTTP_409_CONFLICT
    return HTTPException(status_code=code, detail=exc.message)


def _plan_out(db: Session, plan: TreatmentPlan) -> PlanOut:
    items = service.plan_items(db, plan)
    out_items = []
    for item in items:
        out = ItemOut.model_validate(item)
        if plan.status is PlanStatus.RASCUNHO:
            resolution, error = service.estimate(db, plan, item)
            out.estimated_price = resolution.price if resolution else None
            out.estimate_error = error
        out_items.append(out)
    t = regras.totals(((i.status, i.unit_price) for i in items), plan.discount_pct)
    base = {
        name: getattr(plan, name)
        for name in PlanOut.model_fields
        if name not in ("items", "totals", "expired", "warnings")
    }
    return PlanOut(
        **base,
        items=out_items,
        totals=TotalsOut(**t.__dict__),
        expired=regras.is_expired(plan.status, plan.valid_until, service.today()),
    )


def _audit(db, user, action, plan, request, **details):
    audit.record(
        db, user, f"tratamento.{action}", entity_type="treatment_plan", entity_id=plan.id,
        details={"paciente": str(plan.patient_id), **details}, request=request,
    )  # fmt: skip


def _load(db: Session, plan_id: uuid.UUID) -> TreatmentPlan:
    # Trava o plano: emissão, decisão e execução não correm em paralelo no mesmo plano.
    return service.get_plan(db, plan_id, lock=True)


# ---------- configuração ----------


@router.get("/configuracao", response_model=SettingsOut)
def get_settings_(
    _: CurrentUser = Depends(require_roles(*ALL)),
    db: Session = Depends(get_tenant_db),
):
    s = service.get_clinic_settings(db)
    return SettingsOut(validity_days=s.validity_days, max_discount_pct=s.max_discount_pct)


@router.put("/configuracao", response_model=SettingsOut)
def put_settings(
    body: SettingsIn,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    service.save_settings(db, user, body.validity_days, body.max_discount_pct)
    audit.record(
        db, user, "tratamento.configuracao_alterada", entity_type="treatment_settings",
        details=body.model_dump(mode="json"), request=request,
    )  # fmt: skip
    db.commit()
    return body


# ---------- plano ----------


@router.post("/planos", response_model=PlanOut, status_code=status.HTTP_201_CREATED)
def create_plan(
    body: PlanCreate,
    request: Request,
    user: CurrentUser = Depends(require_roles(*PLAN)),
    db: Session = Depends(get_tenant_db),
):
    try:
        plan = service.create_plan(db, user, body.model_dump())
    except service.TreatmentError as exc:
        raise _http(exc) from None
    _audit(db, user, "plano_criado", plan, request)
    db.commit()
    return _plan_out(db, plan)


@router.get("/pacientes/{patient_id}/planos", response_model=list[PlanSummary])
def list_plans(
    patient_id: uuid.UUID,
    request: Request,
    user: CurrentUser = Depends(require_roles(*ALL)),
    db: Session = Depends(get_tenant_db),
):
    try:
        patient = service.get_patient(db, patient_id)
    except service.TreatmentError as exc:
        raise _http(exc) from None
    plans = service.list_plans(db, patient)
    today = service.today()
    out = [
        PlanSummary.model_validate(p).model_copy(
            update={"expired": regras.is_expired(p.status, p.valid_until, today)}
        )
        for p in plans
    ]
    audit.record(
        db, user, "tratamento.planos_listados", entity_type="patient", entity_id=patient.id,
        details={"resultados": len(out)}, request=request,
    )  # fmt: skip
    db.commit()
    return out


@router.get("/planos/{plan_id}", response_model=PlanOut)
def get_plan(
    plan_id: uuid.UUID,
    request: Request,
    user: CurrentUser = Depends(require_roles(*ALL)),
    db: Session = Depends(get_tenant_db),
):
    try:
        plan = service.get_plan(db, plan_id)
    except service.TreatmentError as exc:
        raise _http(exc) from None
    out = _plan_out(db, plan)
    _audit(db, user, "plano_lido", plan, request)
    db.commit()
    return out


@router.patch("/planos/{plan_id}", response_model=PlanOut)
def update_plan(
    plan_id: uuid.UUID,
    body: PlanUpdate,
    request: Request,
    user: CurrentUser = Depends(require_roles(*PLAN)),
    db: Session = Depends(get_tenant_db),
):
    try:
        plan = _load(db, plan_id)
        changed = service.update_plan(db, user, plan, body.model_dump(exclude_unset=True))
    except service.TreatmentError as exc:
        raise _http(exc) from None
    if changed:
        _audit(db, user, "plano_alterado", plan, request, campos=changed)
        db.commit()
    return _plan_out(db, plan)


@router.post("/planos/{plan_id}/desconto", response_model=PlanOut)
def set_discount(
    plan_id: uuid.UUID,
    body: DiscountIn,
    request: Request,
    user: CurrentUser = Depends(require_roles(*SELL)),
    db: Session = Depends(get_tenant_db),
):
    try:
        plan = _load(db, plan_id)
        service.set_discount(db, user, plan, body.discount_pct)
    except service.TreatmentError as exc:
        raise _http(exc) from None
    _audit(db, user, "desconto_definido", plan, request, percentual=str(body.discount_pct))
    db.commit()
    return _plan_out(db, plan)


@router.post("/planos/{plan_id}/itens", response_model=PlanOut, status_code=201)
def add_item(
    plan_id: uuid.UUID,
    body: ItemIn,
    request: Request,
    user: CurrentUser = Depends(require_roles(*PLAN)),
    db: Session = Depends(get_tenant_db),
):
    try:
        plan = _load(db, plan_id)
        item = service.add_item(db, user, plan, body.model_dump())
    except service.TreatmentError as exc:
        raise _http(exc) from None
    _audit(db, user, "item_incluido", plan, request, item=str(item.id))
    db.commit()
    return _plan_out(db, plan)


def _plan_and_item(db: Session, item_id: uuid.UUID):
    item = service.get_item(db, item_id)
    plan = _load(db, item.plan_id)
    db.refresh(item)  # estado do item depois de obter o lock do plano
    return plan, item


@router.put("/itens/{item_id}", response_model=PlanOut)
def update_item(
    item_id: uuid.UUID,
    body: ItemUpdate,
    request: Request,
    user: CurrentUser = Depends(require_roles(*PLAN)),
    db: Session = Depends(get_tenant_db),
):
    try:
        plan, item = _plan_and_item(db, item_id)
        service.update_item(db, plan, item, body.model_dump())
    except service.TreatmentError as exc:
        raise _http(exc) from None
    _audit(db, user, "item_alterado", plan, request, item=str(item.id))
    db.commit()
    return _plan_out(db, plan)


@router.delete("/itens/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(
    item_id: uuid.UUID,
    request: Request,
    user: CurrentUser = Depends(require_roles(*PLAN)),
    db: Session = Depends(get_tenant_db),
):
    try:
        plan, item = _plan_and_item(db, item_id)
        service.delete_item(db, plan, item)
    except service.TreatmentError as exc:
        raise _http(exc) from None
    _audit(db, user, "item_removido", plan, request, item=str(item_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/planos/{plan_id}/emitir", response_model=PlanOut)
def issue(
    plan_id: uuid.UUID,
    request: Request,
    user: CurrentUser = Depends(require_roles(*SELL)),
    db: Session = Depends(get_tenant_db),
):
    try:
        plan = _load(db, plan_id)
        service.issue(db, user, plan)
    except service.TreatmentError as exc:
        raise _http(exc) from None
    _audit(db, user, "orcamento_emitido", plan, request)
    db.commit()
    return _plan_out(db, plan)


@router.post("/planos/{plan_id}/decisao", response_model=PlanOut)
def decide(
    plan_id: uuid.UUID,
    body: DecisionIn,
    request: Request,
    user: CurrentUser = Depends(require_roles(*SELL)),
    db: Session = Depends(get_tenant_db),
):
    try:
        plan = _load(db, plan_id)
        service.decide(db, user, plan, body.approved_item_ids)
    except service.TreatmentError as exc:
        raise _http(exc) from None
    _audit(db, user, "decisao_registrada", plan, request,
           aprovados=len(set(body.approved_item_ids)))  # fmt: skip
    db.commit()
    return _plan_out(db, plan)


@router.post("/planos/{plan_id}/cancelar", response_model=PlanOut)
def cancel_plan(
    plan_id: uuid.UUID,
    body: ReasonIn,
    request: Request,
    user: CurrentUser = Depends(require_roles(*SELL)),
    db: Session = Depends(get_tenant_db),
):
    try:
        plan = _load(db, plan_id)
        service.cancel_plan(db, plan, body.reason)
    except service.TreatmentError as exc:
        raise _http(exc) from None
    _audit(db, user, "plano_cancelado", plan, request, motivo=body.reason)
    db.commit()
    return _plan_out(db, plan)


@router.post("/planos/{plan_id}/duplicar", response_model=PlanOut, status_code=201)
def duplicate(
    plan_id: uuid.UUID,
    request: Request,
    user: CurrentUser = Depends(require_roles(*PLAN)),
    db: Session = Depends(get_tenant_db),
):
    try:
        plan = service.get_plan(db, plan_id)
        copy = service.duplicate(db, user, plan)
    except service.TreatmentError as exc:
        raise _http(exc) from None
    _audit(db, user, "plano_criado", copy, request, duplicado_de=str(plan.id))
    db.commit()
    return _plan_out(db, copy)


@router.post("/itens/{item_id}/realizar", response_model=PlanOut)
def perform_item(
    item_id: uuid.UUID,
    body: PerformIn,
    request: Request,
    user: CurrentUser = Depends(require_roles(*PLAN)),
    db: Session = Depends(get_tenant_db),
):
    try:
        plan, item = _plan_and_item(db, item_id)
        marks, warnings = service.perform_item(db, user, plan, item, body.encounter_id)
    except service.TreatmentError as exc:
        raise _http(exc) from None
    _audit(db, user, "item_realizado", plan, request, item=str(item.id),
           atendimento=str(body.encounter_id), odontograma=marks,
           faltas_estoque=len(warnings))  # fmt: skip
    db.commit()
    return _plan_out(db, plan).model_copy(update={"warnings": warnings})


@router.post("/itens/{item_id}/cancelar", response_model=PlanOut)
def cancel_item(
    item_id: uuid.UUID,
    body: ReasonIn,
    request: Request,
    user: CurrentUser = Depends(require_roles(*CANCEL_ITEM)),
    db: Session = Depends(get_tenant_db),
):
    try:
        plan, item = _plan_and_item(db, item_id)
        service.cancel_item(db, plan, item, body.reason)
    except service.TreatmentError as exc:
        raise _http(exc) from None
    _audit(db, user, "item_cancelado", plan, request, item=str(item.id), motivo=body.reason)
    db.commit()
    return _plan_out(db, plan)
