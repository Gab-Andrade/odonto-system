"""Rotas da agenda.

A agenda não traz conteúdo clínico (só nome do paciente, horário e procedimento previsto),
então a leitura não é auditada; criação, remarcação e mudança de status são.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import AwareDatetime
from sqlalchemy.orm import Session

from app.core import audit
from app.core.context import CurrentUser
from app.core.roles import Role
from app.modules.agenda import service
from app.modules.agenda.models import Appointment, EntryKind
from app.modules.agenda.schemas import (
    AppointmentCreate,
    BlockCreate,
    ChairCreate,
    ChairOut,
    ChairUpdate,
    EntryDetail,
    EntryOut,
    EntryUpdate,
    EventOut,
    StatusChange,
)
from app.modules.identidade.deps import get_tenant_db, require_roles

router = APIRouter(prefix="/agenda", tags=["agenda"])

# Toda a equipe consulta e marca; cadeiras são configuração da clínica.
TEAM = (Role.ADMIN, Role.GESTOR, Role.DENTISTA, Role.ASB, Role.RECEPCAO)
MANAGE = (Role.ADMIN, Role.GESTOR)


def _http(exc: service.AgendaError) -> HTTPException:
    code = status.HTTP_404_NOT_FOUND if isinstance(exc, service.NotFound) else 409
    return HTTPException(status_code=code, detail=exc.message)


def _out(entry: Appointment, patient_name: str | None = None) -> EntryOut:
    out = EntryOut.model_validate(entry)
    out.patient_name = patient_name
    return out


def _entity(entry: Appointment) -> str:
    return "agendamento" if entry.kind == EntryKind.CONSULTA else "bloqueio"


# ---------- Cadeiras ----------


@router.get("/cadeiras", response_model=list[ChairOut])
def list_chairs(
    incluir_inativas: bool = False,
    _: CurrentUser = Depends(require_roles(*TEAM)),
    db: Session = Depends(get_tenant_db),
):
    return service.list_chairs(db, include_inactive=incluir_inativas)


@router.post("/cadeiras", response_model=ChairOut, status_code=status.HTTP_201_CREATED)
def create_chair(
    body: ChairCreate,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    try:
        chair = service.create_chair(db, user, body.name)
    except service.AgendaError as exc:
        raise _http(exc) from None
    audit.record(
        db, user, "agenda.cadeira_criada", entity_type="chair", entity_id=chair.id,
        request=request,
    )  # fmt: skip
    db.commit()
    return chair


@router.patch("/cadeiras/{chair_id}", response_model=ChairOut)
def update_chair(
    chair_id: uuid.UUID,
    body: ChairUpdate,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    try:
        chair = service.update_chair(
            db, service.get_chair(db, chair_id), body.model_dump(exclude_unset=True)
        )
    except service.AgendaError as exc:
        raise _http(exc) from None
    audit.record(
        db, user, "agenda.cadeira_alterada", entity_type="chair", entity_id=chair.id,
        details={"ativa": chair.active}, request=request,
    )  # fmt: skip
    db.commit()
    return chair


# ---------- Agendamentos e bloqueios ----------


@router.get("/agendamentos", response_model=list[EntryOut])
def list_entries(
    inicio: AwareDatetime | None = Query(None, description="Obrigatório sem paciente_id."),
    fim: AwareDatetime | None = Query(None, description="Até 62 dias depois do início."),
    dentista_id: uuid.UUID | None = None,
    cadeira_id: uuid.UUID | None = None,
    paciente_id: uuid.UUID | None = None,
    incluir_cancelados: bool = True,
    _: CurrentUser = Depends(require_roles(*TEAM)),
    db: Session = Depends(get_tenant_db),
):
    """Consultas e bloqueios que cruzam o período, em ordem de início."""
    try:
        rows = service.list_entries(
            db,
            start=inicio,
            end=fim,
            dentist_id=dentista_id,
            chair_id=cadeira_id,
            patient_id=paciente_id,
            include_cancelled=incluir_cancelados,
        )
    except service.AgendaError as exc:
        raise _http(exc) from None
    return [_out(r.entry, r.patient_name) for r in rows]


@router.post("/agendamentos", response_model=EntryOut, status_code=status.HTTP_201_CREATED)
def create_appointment(
    body: AppointmentCreate,
    request: Request,
    user: CurrentUser = Depends(require_roles(*TEAM)),
    db: Session = Depends(get_tenant_db),
):
    try:
        entry = service.create_appointment(db, user, body.model_dump())
    except service.AgendaError as exc:
        raise _http(exc) from None
    audit.record(
        db, user, "agenda.agendamento_criado", entity_type="appointment", entity_id=entry.id,
        details={"paciente": str(entry.patient_id)}, request=request,
    )  # fmt: skip
    db.commit()
    return _out(entry)


@router.post("/bloqueios", response_model=EntryOut, status_code=status.HTTP_201_CREATED)
def create_block(
    body: BlockCreate,
    request: Request,
    user: CurrentUser = Depends(require_roles(*TEAM)),
    db: Session = Depends(get_tenant_db),
):
    """Horário indisponível de um dentista e/ou de uma cadeira (almoço, férias, manutenção)."""
    try:
        entry = service.create_block(db, user, body.model_dump())
    except service.AgendaError as exc:
        raise _http(exc) from None
    audit.record(
        db, user, "agenda.bloqueio_criado", entity_type="appointment", entity_id=entry.id,
        request=request,
    )  # fmt: skip
    db.commit()
    return _out(entry)


@router.get("/agendamentos/{entry_id}", response_model=EntryDetail)
def get_entry(
    entry_id: uuid.UUID,
    _: CurrentUser = Depends(require_roles(*TEAM)),
    db: Session = Depends(get_tenant_db),
):
    try:
        entry = service.get_entry(db, entry_id)
    except service.AgendaError as exc:
        raise _http(exc) from None
    return EntryDetail(
        **_out(entry).model_dump(),
        historico=[EventOut.model_validate(e) for e in service.list_events(db, entry)],
    )


@router.patch("/agendamentos/{entry_id}", response_model=EntryOut)
def update_entry(
    entry_id: uuid.UUID,
    body: EntryUpdate,
    request: Request,
    user: CurrentUser = Depends(require_roles(*TEAM)),
    db: Session = Depends(get_tenant_db),
):
    """Remarca (horário, dentista, cadeira) ou altera procedimento e observações."""
    try:
        entry = service.get_entry(db, entry_id)
        changed = service.update_entry(db, user, entry, body.model_dump(exclude_unset=True))
    except service.AgendaError as exc:
        raise _http(exc) from None
    if changed:
        audit.record(
            db, user, f"agenda.{_entity(entry)}_alterado", entity_type="appointment",
            entity_id=entry.id, details={"campos": changed}, request=request,
        )  # fmt: skip
    db.commit()
    return _out(entry)


@router.post("/agendamentos/{entry_id}/status", response_model=EntryOut)
def change_status(
    entry_id: uuid.UUID,
    body: StatusChange,
    request: Request,
    user: CurrentUser = Depends(require_roles(*TEAM)),
    db: Session = Depends(get_tenant_db),
):
    """Confirma, marca atendido ou falta, ou cancela. Falta e cancelamento liberam o horário."""
    try:
        entry = service.change_status(
            db, user, service.get_entry(db, entry_id), body.status, body.motivo
        )
    except service.AgendaError as exc:
        raise _http(exc) from None
    audit.record(
        db, user, "agenda.status_alterado", entity_type="appointment", entity_id=entry.id,
        details={"status": entry.status.value}, request=request,
    )  # fmt: skip
    db.commit()
    return _out(entry)
