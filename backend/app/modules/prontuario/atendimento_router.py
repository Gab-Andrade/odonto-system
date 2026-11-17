"""Rotas do prontuário — atendimento e evolução clínica.

Abrir e fechar atendimento, registrar evolução e adendo: dentista ou admin (o
dono-dentista), e só o autor (ver atendimento_service). Transferir atendimento aberto
para outro dentista: só admin. Leitura: ASB, gestor, dentista e
admin; a recepção não tem acesso. Toda leitura é auditada (LGPD), sem o texto clínico nos
detalhes. Não há rota de alteração nem de exclusão: evolução é imutável.
"""

import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.core import audit
from app.core.context import CurrentUser
from app.core.roles import Role
from app.modules.identidade.deps import get_tenant_db, require_roles
from app.modules.prontuario import atendimento_service as atendimento
from app.modules.prontuario import service
from app.modules.prontuario.models import ClinicalNote, Encounter
from app.modules.prontuario.router import READ, _http
from app.modules.prontuario.schemas import (
    AddendumCreate,
    EncounterCreate,
    EncounterDetail,
    EncounterOut,
    EncounterSummary,
    NoteCreate,
    NoteOut,
    SignatureOut,
    TransferIn,
    TransferOut,
)

router = APIRouter(prefix="/prontuario", tags=["prontuario"])

CLINICIAN = (Role.ADMIN, Role.DENTISTA)


def _notes_out(db: Session, notes: list[ClinicalNote]) -> list[NoteOut]:
    signatures = atendimento.signatures_by_note(db, notes)
    return [
        NoteOut.model_validate(n).model_copy(
            update={"signatures": [SignatureOut.model_validate(s) for s in signatures[n.id]]}
        )
        for n in notes
    ]


def _encounter_detail(db: Session, encounter: Encounter) -> EncounterDetail:
    notes = _notes_out(db, atendimento.encounter_notes(db, encounter))
    transfers = [TransferOut.model_validate(t) for t in atendimento.list_transfers(db, encounter)]
    return EncounterDetail(
        **EncounterOut.model_validate(encounter).model_dump(), notes=notes, transfers=transfers
    )


@router.post("/atendimentos", response_model=EncounterDetail, status_code=status.HTTP_201_CREATED)
def open_encounter(
    body: EncounterCreate,
    request: Request,
    user: CurrentUser = Depends(require_roles(*CLINICIAN)),
    db: Session = Depends(get_tenant_db),
):
    try:
        encounter = atendimento.open_encounter(
            db, user, body.patient_id, body.appointment_id, body.started_at
        )
    except service.ProntuarioError as exc:
        raise _http(exc) from None
    details = {"paciente": str(encounter.patient_id)}
    if encounter.appointment_id:
        details["agendamento"] = str(encounter.appointment_id)
    audit.record(
        db, user, "prontuario.atendimento_aberto", entity_type="encounter",
        entity_id=encounter.id, details=details, request=request,
    )  # fmt: skip
    db.commit()
    return _encounter_detail(db, encounter)


@router.get("/atendimentos/{encounter_id}", response_model=EncounterDetail)
def get_encounter(
    encounter_id: uuid.UUID,
    request: Request,
    user: CurrentUser = Depends(require_roles(*READ)),
    db: Session = Depends(get_tenant_db),
):
    try:
        encounter = atendimento.get_encounter(db, encounter_id)
    except service.ProntuarioError as exc:
        raise _http(exc) from None
    out = _encounter_detail(db, encounter)
    audit.record(
        db, user, "prontuario.atendimento_lido", entity_type="encounter",
        entity_id=encounter.id, details={"paciente": str(encounter.patient_id)},
        request=request,
    )  # fmt: skip
    db.commit()
    return out


@router.post("/atendimentos/{encounter_id}/fechar", response_model=EncounterDetail)
def close_encounter(
    encounter_id: uuid.UUID,
    request: Request,
    user: CurrentUser = Depends(require_roles(*CLINICIAN)),
    db: Session = Depends(get_tenant_db),
):
    try:
        encounter = atendimento.get_encounter(db, encounter_id)
        atendimento.close_encounter(db, user, encounter)
    except service.ProntuarioError as exc:
        raise _http(exc) from None
    audit.record(
        db, user, "prontuario.atendimento_fechado", entity_type="encounter",
        entity_id=encounter.id, details={"paciente": str(encounter.patient_id)},
        request=request,
    )  # fmt: skip
    db.commit()
    return _encounter_detail(db, encounter)


@router.post("/atendimentos/{encounter_id}/transferir", response_model=EncounterDetail)
def transfer_encounter(
    encounter_id: uuid.UUID,
    body: TransferIn,
    request: Request,
    user: CurrentUser = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_tenant_db),
):
    """Admin passa um atendimento aberto para outro dentista (ex.: o dentista saiu)."""
    try:
        encounter = atendimento.get_encounter(db, encounter_id)
        transfer = atendimento.transfer_encounter(db, user, encounter, body.dentist_id, body.reason)
    except service.ProntuarioError as exc:
        raise _http(exc) from None
    audit.record(
        db, user, "prontuario.atendimento_transferido", entity_type="encounter",
        entity_id=encounter.id,
        details={"paciente": str(encounter.patient_id), "de": str(transfer.from_dentist_id),
                 "para": str(transfer.to_dentist_id)},
        request=request,
    )  # fmt: skip
    db.commit()
    return _encounter_detail(db, encounter)


@router.post(
    "/atendimentos/{encounter_id}/evolucoes",
    response_model=NoteOut,
    status_code=status.HTTP_201_CREATED,
)
def add_note(
    encounter_id: uuid.UUID,
    body: NoteCreate,
    request: Request,
    user: CurrentUser = Depends(require_roles(*CLINICIAN)),
    db: Session = Depends(get_tenant_db),
):
    try:
        encounter = atendimento.get_encounter(db, encounter_id)
        note = atendimento.add_note(db, user, encounter, body.content, body.performed_at)
    except service.ProntuarioError as exc:
        raise _http(exc) from None
    audit.record(
        db, user, "prontuario.evolucao_registrada", entity_type="clinical_note",
        entity_id=note.id,
        details={"paciente": str(note.patient_id), "atendimento": str(encounter.id),
                 "data_informada": body.performed_at is not None},
        request=request,
    )  # fmt: skip
    db.commit()
    return _notes_out(db, [note])[0]


@router.post(
    "/evolucoes/{note_id}/adendos", response_model=NoteOut, status_code=status.HTTP_201_CREATED
)
def add_addendum(
    note_id: uuid.UUID,
    body: AddendumCreate,
    request: Request,
    user: CurrentUser = Depends(require_roles(*CLINICIAN)),
    db: Session = Depends(get_tenant_db),
):
    try:
        note = atendimento.get_note(db, note_id)
        addendum = atendimento.add_addendum(db, user, note, body.content)
    except service.ProntuarioError as exc:
        raise _http(exc) from None
    audit.record(
        db, user, "prontuario.adendo_registrado", entity_type="clinical_note",
        entity_id=addendum.id,
        details={"paciente": str(addendum.patient_id), "evolucao": str(note.id)},
        request=request,
    )  # fmt: skip
    db.commit()
    return _notes_out(db, [addendum])[0]


@router.get("/pacientes/{patient_id}/atendimentos", response_model=list[EncounterSummary])
def list_encounters(
    patient_id: uuid.UUID,
    request: Request,
    limit: int = Query(100, ge=1, le=atendimento.MAX_PAGE),
    offset: int = Query(0, ge=0),
    user: CurrentUser = Depends(require_roles(*READ)),
    db: Session = Depends(get_tenant_db),
):
    try:
        patient = service.get_patient(db, patient_id)
    except service.ProntuarioError as exc:
        raise _http(exc) from None
    out = [
        EncounterSummary(**EncounterOut.model_validate(r.encounter).model_dump(), notes=r.notes)
        for r in atendimento.list_encounters(db, patient, limit=limit, offset=offset)
    ]
    audit.record(
        db, user, "prontuario.atendimentos_listados", entity_type="patient",
        entity_id=patient.id, details={"resultados": len(out)}, request=request,
    )  # fmt: skip
    db.commit()
    return out


@router.get("/pacientes/{patient_id}/evolucoes", response_model=list[NoteOut])
def patient_notes(
    patient_id: uuid.UUID,
    request: Request,
    limit: int = Query(100, ge=1, le=atendimento.MAX_PAGE),
    offset: int = Query(0, ge=0),
    user: CurrentUser = Depends(require_roles(*READ)),
    db: Session = Depends(get_tenant_db),
):
    """Linha do tempo de evoluções e adendos do paciente (mais recente primeiro)."""
    try:
        patient = service.get_patient(db, patient_id)
    except service.ProntuarioError as exc:
        raise _http(exc) from None
    out = _notes_out(db, atendimento.patient_notes(db, patient, limit=limit, offset=offset))
    audit.record(
        db, user, "prontuario.evolucoes_lidas", entity_type="patient", entity_id=patient.id,
        details={"resultados": len(out)}, request=request,
    )  # fmt: skip
    db.commit()
    return out
