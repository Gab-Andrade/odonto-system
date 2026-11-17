"""Rotas do financeiro.

Papéis: caixa (contas a receber, parcelamento, recebimentos, extrato) — admin, gestor e
recepção; cancelar conta, estornar e contas a pagar — admin e gestor. Dentista e ASB não
acessam o financeiro (a produção do dentista entra no repasse e no painel).

LGPD: extrato e listas de contas de paciente são auditados, além das escritas.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core import audit
from app.core.context import CurrentUser
from app.core.roles import Role
from app.modules.financeiro import service
from app.modules.financeiro.models import PayableStatus
from app.modules.financeiro.schemas import (
    InstallmentPlanIn,
    PayableCreate,
    PayableOut,
    PayablePay,
    PaymentIn,
    PaymentOut,
    ReasonIn,
    ReceivableCreate,
    ReceivableOut,
    StatementOut,
)
from app.modules.identidade.deps import get_tenant_db, require_roles

router = APIRouter(prefix="/financeiro", tags=["financeiro"])

CASHIER = (Role.ADMIN, Role.GESTOR, Role.RECEPCAO)
MANAGE = (Role.ADMIN, Role.GESTOR)


def _http(exc: service.FinanceError) -> HTTPException:
    code = status.HTTP_404_NOT_FOUND if isinstance(exc, service.NotFound) else 409
    return HTTPException(status_code=code, detail=exc.message)


def _out(row: service.ReceivableRow) -> ReceivableOut:
    return ReceivableOut.model_validate(row.receivable).model_copy(
        update={"paid": row.paid, "balance": row.balance, "status": row.status}
    )


def _record(db, user, action, request, *, entity_type, entity_id=None, **details):
    audit.record(
        db, user, f"financeiro.{action}", entity_type=entity_type, entity_id=entity_id,
        details=details or None, request=request,
    )  # fmt: skip


# ---------- contas a receber ----------


@router.get("/receber", response_model=list[ReceivableOut])
def list_receivables(
    request: Request,
    paciente_id: uuid.UUID | None = None,
    vencimento_de: date | None = None,
    vencimento_ate: date | None = None,
    incluir_canceladas: bool = False,
    limit: int = Query(200, ge=1, le=service.MAX_LIST),
    user: CurrentUser = Depends(require_roles(*CASHIER)),
    db: Session = Depends(get_tenant_db),
):
    rows = service.list_receivables(
        db,
        patient_id=paciente_id,
        due_from=vencimento_de,
        due_to=vencimento_ate,
        include_cancelled=incluir_canceladas,
        limit=limit,
    )
    _record(db, user, "contas_listadas", request, entity_type="receivable",
            resultados=len(rows), paciente=str(paciente_id) if paciente_id else None)  # fmt: skip
    db.commit()
    return [_out(r) for r in rows]


@router.post("/receber", response_model=ReceivableOut, status_code=status.HTTP_201_CREATED)
def create_receivable(
    body: ReceivableCreate,
    request: Request,
    user: CurrentUser = Depends(require_roles(*CASHIER)),
    db: Session = Depends(get_tenant_db),
):
    try:
        receivable = service.create_receivable(db, user, body.model_dump())
    except service.FinanceError as exc:
        raise _http(exc) from None
    _record(db, user, "conta_criada", request, entity_type="receivable",
            entity_id=receivable.id, paciente=str(receivable.patient_id))  # fmt: skip
    db.commit()
    return _out(service.rows_for(db, [receivable])[0])


@router.post(
    "/planos/{plan_id}/parcelamento",
    response_model=list[ReceivableOut],
    status_code=status.HTTP_201_CREATED,
)
def installment_plan(
    plan_id: uuid.UUID,
    body: InstallmentPlanIn,
    request: Request,
    user: CurrentUser = Depends(require_roles(*CASHIER)),
    db: Session = Depends(get_tenant_db),
):
    try:
        rows = service.installment_plan(
            db, user, plan_id, body.down_payment, body.installments,
            body.down_payment_date, body.first_due_date,
        )  # fmt: skip
    except service.FinanceError as exc:
        raise _http(exc) from None
    _record(db, user, "parcelamento_criado", request, entity_type="treatment_plan",
            entity_id=plan_id, paciente=str(rows[0].patient_id), contas=len(rows))  # fmt: skip
    db.commit()
    return [_out(r) for r in service.rows_for(db, rows)]


@router.post("/planos/{plan_id}/parcelamento/cancelar")
def cancel_installment_plan(
    plan_id: uuid.UUID,
    body: ReasonIn,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    try:
        count = service.cancel_plan_installments(db, plan_id, body.reason)
    except service.FinanceError as exc:
        raise _http(exc) from None
    _record(db, user, "parcelamento_cancelado", request, entity_type="treatment_plan",
            entity_id=plan_id, contas=count, motivo=body.reason)  # fmt: skip
    db.commit()
    return {"canceladas": count}


@router.post("/receber/{receivable_id}/cancelar", response_model=ReceivableOut)
def cancel_receivable(
    receivable_id: uuid.UUID,
    body: ReasonIn,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    try:
        receivable = service.get_receivable(db, receivable_id, lock=True)
        service.cancel_receivable(db, receivable, body.reason)
    except service.FinanceError as exc:
        raise _http(exc) from None
    _record(db, user, "conta_cancelada", request, entity_type="receivable",
            entity_id=receivable.id, motivo=body.reason)  # fmt: skip
    db.commit()
    return _out(service.rows_for(db, [receivable])[0])


@router.post(
    "/receber/{receivable_id}/pagamentos",
    response_model=PaymentOut,
    status_code=status.HTTP_201_CREATED,
)
def register_payment(
    receivable_id: uuid.UUID,
    body: PaymentIn,
    request: Request,
    user: CurrentUser = Depends(require_roles(*CASHIER)),
    db: Session = Depends(get_tenant_db),
):
    try:
        receivable = service.get_receivable(db, receivable_id, lock=True)
        payment = service.register_payment(
            db, user, receivable, body.amount, body.method, body.fee_pct, body.paid_on,
            body.notes,
        )  # fmt: skip
    except service.FinanceError as exc:
        raise _http(exc) from None
    _record(db, user, "recebimento_registrado", request, entity_type="payment",
            entity_id=payment.id, conta=str(receivable.id), valor=str(payment.amount),
            forma=payment.method.value)  # fmt: skip
    db.commit()
    return payment


@router.post("/pagamentos/{payment_id}/estornar", response_model=PaymentOut, status_code=201)
def reverse_payment(
    payment_id: uuid.UUID,
    body: ReasonIn,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    try:
        payment = service.get_payment(db, payment_id)
        service.get_receivable(db, payment.receivable_id, lock=True)
        reversal = service.reverse_payment(db, user, payment, body.reason)
    except service.FinanceError as exc:
        raise _http(exc) from None
    _record(db, user, "recebimento_estornado", request, entity_type="payment",
            entity_id=reversal.id, estornado=str(payment.id), motivo=body.reason)  # fmt: skip
    db.commit()
    return reversal


@router.get("/pacientes/{patient_id}/extrato", response_model=StatementOut)
def statement(
    patient_id: uuid.UUID,
    request: Request,
    user: CurrentUser = Depends(require_roles(*CASHIER)),
    db: Session = Depends(get_tenant_db),
):
    try:
        patient = service.get_patient(db, patient_id)
    except service.FinanceError as exc:
        raise _http(exc) from None
    st = service.statement(db, patient)
    _record(db, user, "extrato_lido", request, entity_type="patient", entity_id=patient.id)
    db.commit()
    return StatementOut(
        patient_id=patient.id,
        total=st.total,
        paid=st.paid,
        balance=st.total - st.paid,
        overdue=st.overdue,
        receivables=[_out(r) for r in st.receivables],
        payments=[PaymentOut.model_validate(p) for p in st.payments],
    )


# ---------- contas a pagar ----------


def _payable_out(p) -> PayableOut:
    out = PayableOut.model_validate(p)
    out.overdue = p.status is PayableStatus.ABERTA and p.due_date < service.today()
    return out


@router.get("/pagar", response_model=list[PayableOut])
def list_payables(
    vencimento_de: date | None = None,
    vencimento_ate: date | None = None,
    situacao: PayableStatus | None = None,
    limit: int = Query(200, ge=1, le=service.MAX_LIST),
    _: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    rows = service.list_payables(
        db, due_from=vencimento_de, due_to=vencimento_ate, status=situacao, limit=limit
    )
    return [_payable_out(p) for p in rows]


@router.post("/pagar", response_model=PayableOut, status_code=status.HTTP_201_CREATED)
def create_payable(
    body: PayableCreate,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    payable = service.create_payable(db, user, body.model_dump())
    _record(db, user, "conta_pagar_criada", request, entity_type="payable", entity_id=payable.id)
    db.commit()
    return _payable_out(payable)


@router.post("/pagar/{payable_id}/pagar", response_model=PayableOut)
def pay_payable(
    payable_id: uuid.UUID,
    body: PayablePay,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    try:
        payable = service.get_payable(db, payable_id)
        service.pay_payable(db, payable, body.method, body.paid_on)
    except service.FinanceError as exc:
        raise _http(exc) from None
    _record(db, user, "conta_pagar_paga", request, entity_type="payable", entity_id=payable.id)
    db.commit()
    return _payable_out(payable)


@router.post("/pagar/{payable_id}/cancelar", response_model=PayableOut)
def cancel_payable(
    payable_id: uuid.UUID,
    body: ReasonIn,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    try:
        payable = service.get_payable(db, payable_id)
        service.cancel_payable(db, payable, body.reason)
    except service.FinanceError as exc:
        raise _http(exc) from None
    _record(db, user, "conta_pagar_cancelada", request, entity_type="payable",
            entity_id=payable.id, motivo=body.reason)  # fmt: skip
    db.commit()
    return _payable_out(payable)
