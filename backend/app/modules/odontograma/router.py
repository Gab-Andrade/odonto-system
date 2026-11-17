"""Rotas do odontograma.

Papéis: ler (legenda, odontograma e histórico) — admin, gestor, dentista e ASB; marcar —
admin, dentista e ASB; editar a legenda — admin e gestor. A recepção não tem acesso.

LGPD: leitura do odontograma e do histórico de um paciente é auditada; a legenda (sem dado
de paciente) não.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import AwareDatetime
from sqlalchemy.orm import Session

from app.core import audit
from app.core.context import CurrentUser
from app.core.roles import Role
from app.modules.identidade.deps import get_tenant_db, require_roles
from app.modules.odontograma import arcada, regras, service
from app.modules.odontograma.models import OdontogramEvent, ToothStatus
from app.modules.odontograma.schemas import (
    ArchIn,
    ArchOut,
    EventOut,
    EventsIn,
    MarkOut,
    OdontogramOut,
    StatusCreate,
    StatusOut,
    StatusUpdate,
    ToothOut,
)

router = APIRouter(prefix="/odontograma", tags=["odontograma"])

READ = (Role.ADMIN, Role.GESTOR, Role.DENTISTA, Role.ASB)
MARK = (Role.ADMIN, Role.DENTISTA, Role.ASB)
MANAGE = (Role.ADMIN, Role.GESTOR)


def _http(exc: service.OdontogramError) -> HTTPException:
    code = status.HTTP_404_NOT_FOUND if isinstance(exc, service.NotFound) else 409
    return HTTPException(status_code=code, detail=exc.message)


def _event_out(e: OdontogramEvent) -> EventOut:
    out = EventOut.model_validate(e)
    if e.face:
        out.face_label = regras.face_label(e.tooth, e.face)
    return out


# ---------- legenda ----------


@router.get("/legenda", response_model=list[StatusOut])
def list_legend(
    incluir_inativos: bool = False,
    user: CurrentUser = Depends(require_roles(*READ)),
    db: Session = Depends(get_tenant_db),
):
    service.ensure_default_legend(db, user.clinic_id)
    db.commit()
    return service.list_statuses(db, include_inactive=incluir_inativos)


@router.post("/legenda", response_model=StatusOut, status_code=status.HTTP_201_CREATED)
def create_status(
    body: StatusCreate,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    try:
        item = service.create_status(db, user, body.model_dump())
    except service.OdontogramError as exc:
        raise _http(exc) from None
    audit.record(
        db, user, "odontograma.legenda_criada", entity_type="tooth_status", entity_id=item.id,
        request=request,
    )  # fmt: skip
    db.commit()
    return item


@router.patch("/legenda/{status_id}", response_model=StatusOut)
def update_status(
    status_id: uuid.UUID,
    body: StatusUpdate,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    try:
        item: ToothStatus = service.get_status(db, status_id)
        changed = service.update_status(db, item, body.model_dump(exclude_unset=True))
    except service.OdontogramError as exc:
        raise _http(exc) from None
    if changed:
        audit.record(
            db, user, "odontograma.legenda_alterada", entity_type="tooth_status",
            entity_id=item.id, details={"campos": changed}, request=request,
        )  # fmt: skip
        db.commit()
    return item


# ---------- odontograma do paciente ----------


@router.get("/pacientes/{patient_id}", response_model=OdontogramOut)
def get_odontogram(
    patient_id: uuid.UUID,
    request: Request,
    em: AwareDatetime | None = Query(None, description="Odontograma como estava neste momento."),
    user: CurrentUser = Depends(require_roles(*READ)),
    db: Session = Depends(get_tenant_db),
):
    try:
        patient = service.get_patient(db, patient_id)
    except service.OdontogramError as exc:
        raise _http(exc) from None
    at: datetime = em or service.now()
    marks = service.current_marks(db, patient, at)
    statuses = {s.id: s for s in service.list_statuses(db)}

    teeth: dict[int, ToothOut] = {}
    for tooth, face, status_id in sorted(marks, key=lambda k: (k[0], k[1] or "", str(k[2]))):
        s = statuses[status_id]
        mark = MarkOut(status_id=s.id, code=s.code, name=s.name, color=s.color, kind=s.kind)
        entry = teeth.setdefault(
            tooth,
            ToothOut(tooth=tooth, deciduous=regras.is_deciduous(tooth), whole=[], faces={}),
        )
        if face is None:
            entry.whole.append(mark)
        else:
            entry.faces.setdefault(regras.face_label(tooth, face), []).append(mark)

    audit.record(
        db, user, "odontograma.lido", entity_type="patient", entity_id=patient.id,
        details={"em": em.isoformat()} if em else None, request=request,
    )  # fmt: skip
    db.commit()
    return OdontogramOut(patient_id=patient.id, at=at, teeth=list(teeth.values()))


@router.post(
    "/pacientes/{patient_id}/eventos",
    response_model=list[EventOut],
    status_code=status.HTTP_201_CREATED,
)
def record_events(
    patient_id: uuid.UUID,
    body: EventsIn,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MARK)),
    db: Session = Depends(get_tenant_db),
):
    try:
        patient = service.get_patient(db, patient_id)
        rows = service.record_events(
            db, user, patient, body.encounter_id, [e.model_dump() for e in body.events]
        )
    except service.OdontogramError as exc:
        raise _http(exc) from None
    details = {"eventos": len(rows)}
    if body.encounter_id:
        details["atendimento"] = str(body.encounter_id)
    audit.record(
        db, user, "odontograma.marcado", entity_type="patient", entity_id=patient.id,
        details=details, request=request,
    )  # fmt: skip
    db.commit()
    return [_event_out(r) for r in rows]


@router.get("/pacientes/{patient_id}/historico", response_model=list[EventOut])
def history(
    patient_id: uuid.UUID,
    request: Request,
    limit: int = Query(100, ge=1, le=service.MAX_HISTORY),
    offset: int = Query(0, ge=0),
    user: CurrentUser = Depends(require_roles(*READ)),
    db: Session = Depends(get_tenant_db),
):
    try:
        patient = service.get_patient(db, patient_id)
    except service.OdontogramError as exc:
        raise _http(exc) from None
    out = [_event_out(e) for e in service.history(db, patient, limit=limit, offset=offset)]
    audit.record(
        db, user, "odontograma.historico_lido", entity_type="patient", entity_id=patient.id,
        details={"resultados": len(out)}, request=request,
    )  # fmt: skip
    db.commit()
    return out


# ---------- arcada ----------


def _arch_out(patient_id: uuid.UUID, arch: service.Arch) -> ArchOut:
    c = arch.config
    return ArchOut(
        patient_id=patient_id,
        source=arch.source,
        dentition=arch.dentition,
        teeth=arch.teeth,
        third_molars=[t for t in arch.teeth if t in arcada.THIRD_MOLARS],
        id=c.id if c else None,
        notes=c.notes if c else None,
        recorded_by=c.recorded_by if c else None,
        created_at=c.created_at if c else None,
    )


@router.get("/pacientes/{patient_id}/arcada", response_model=ArchOut)
def get_arch(
    patient_id: uuid.UUID,
    request: Request,
    em: AwareDatetime | None = Query(None, description="Arcada vigente neste momento."),
    user: CurrentUser = Depends(require_roles(*READ)),
    db: Session = Depends(get_tenant_db),
):
    try:
        patient = service.get_patient(db, patient_id)
    except service.OdontogramError as exc:
        raise _http(exc) from None
    arch = service.effective_arch(db, patient, em)
    audit.record(
        db, user, "odontograma.arcada_lida", entity_type="patient", entity_id=patient.id,
        details={"em": em.isoformat()} if em else None, request=request,
    )  # fmt: skip
    db.commit()
    return _arch_out(patient.id, arch)


@router.post(
    "/pacientes/{patient_id}/arcada", response_model=ArchOut, status_code=status.HTTP_201_CREATED
)
def record_arch(
    patient_id: uuid.UUID,
    body: ArchIn,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MARK)),
    db: Session = Depends(get_tenant_db),
):
    try:
        patient = service.get_patient(db, patient_id)
        config = service.record_arch(db, user, patient, body.model_dump())
    except service.OdontogramError as exc:
        raise _http(exc) from None
    audit.record(
        db, user, "odontograma.arcada_registrada", entity_type="patient", entity_id=patient.id,
        details={"denticao": config.dentition.value, "dentes": len(config.teeth)},
        request=request,
    )  # fmt: skip
    db.commit()
    arch = service.Arch(config.dentition.value, arcada.sort_teeth(config.teeth), config)
    return _arch_out(patient.id, arch)
