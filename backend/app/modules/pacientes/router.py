"""Rotas de pacientes.

LGPD: além das escritas, a leitura também é auditada — abrir a ficha grava
`pacientes.ficha_lida` e cada busca grava `pacientes.busca` com a quantidade de resultados
(o termo não é guardado, porque pode ser um CPF ou telefone). Os detalhes de auditoria
levam só nomes de campos, nunca os valores.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core import audit
from app.core.context import CurrentUser
from app.core.roles import Role
from app.modules.identidade.deps import get_tenant_db, require_roles
from app.modules.pacientes import dados, service
from app.modules.pacientes.schemas import (
    ConsentIn,
    ConsentOut,
    ConsentsOut,
    PatientCreate,
    PatientOut,
    PatientSummary,
    PatientUpdate,
)

router = APIRouter(prefix="/pacientes", tags=["pacientes"])

# Cadastro: toda a equipe da clínica. Conteúdo clínico (anamnese, evolução, odontograma)
# tem regras próprias nos módulos do prontuário.
CADASTRO = (Role.ADMIN, Role.GESTOR, Role.DENTISTA, Role.ASB, Role.RECEPCAO)


def _http(exc: service.PatientError) -> HTTPException:
    code = status.HTTP_404_NOT_FOUND if isinstance(exc, service.NotFound) else 409
    return HTTPException(status_code=code, detail=exc.message)


@router.get("", response_model=list[PatientSummary])
def search_patients(
    request: Request,
    busca: str | None = Query(None, max_length=200, description="Nome, CPF ou telefone."),
    incluir_inativos: bool = False,
    limit: int = Query(20, ge=1, le=service.MAX_SEARCH_RESULTS),
    offset: int = Query(0, ge=0),
    user: CurrentUser = Depends(require_roles(*CADASTRO)),
    db: Session = Depends(get_tenant_db),
):
    patients = service.search_patients(
        db, busca, include_inactive=incluir_inativos, limit=limit, offset=offset
    )
    audit.record(
        db, user, "pacientes.busca", entity_type="patient",
        details={"resultados": len(patients), "com_termo": bool(busca and busca.strip())},
        request=request,
    )  # fmt: skip
    db.commit()
    return [
        PatientSummary(
            id=p.id,
            full_name=p.full_name,
            social_name=p.social_name,
            birth_date=p.birth_date,
            cpf_mascarado=dados.mask_cpf(p.cpf),
            phone=p.phone,
            active=p.active,
        )
        for p in patients
    ]


@router.post("", response_model=PatientOut, status_code=status.HTTP_201_CREATED)
def create_patient(
    body: PatientCreate,
    request: Request,
    user: CurrentUser = Depends(require_roles(*CADASTRO)),
    db: Session = Depends(get_tenant_db),
):
    try:
        patient = service.create_patient(db, user, body.model_dump())
    except service.PatientError as exc:
        raise _http(exc) from None
    audit.record(
        db, user, "pacientes.cadastrado", entity_type="patient", entity_id=patient.id,
        request=request,
    )  # fmt: skip
    db.commit()
    return patient


@router.get("/{patient_id}", response_model=PatientOut)
def get_patient(
    patient_id: uuid.UUID,
    request: Request,
    user: CurrentUser = Depends(require_roles(*CADASTRO)),
    db: Session = Depends(get_tenant_db),
):
    try:
        patient = service.get_patient(db, patient_id)
    except service.PatientError as exc:
        raise _http(exc) from None
    audit.record(
        db, user, "pacientes.ficha_lida", entity_type="patient", entity_id=patient.id,
        request=request,
    )  # fmt: skip
    db.commit()
    return patient


@router.patch("/{patient_id}", response_model=PatientOut)
def update_patient(
    patient_id: uuid.UUID,
    body: PatientUpdate,
    request: Request,
    user: CurrentUser = Depends(require_roles(*CADASTRO)),
    db: Session = Depends(get_tenant_db),
):
    try:
        patient = service.get_patient(db, patient_id)
        changed = service.update_patient(db, patient, body.model_dump(exclude_unset=True))
    except service.PatientError as exc:
        raise _http(exc) from None
    if changed:
        audit.record(
            db, user, "pacientes.ficha_alterada", entity_type="patient", entity_id=patient.id,
            details={"campos": changed}, request=request,
        )  # fmt: skip
    db.commit()
    return patient


@router.get("/{patient_id}/consentimentos", response_model=ConsentsOut)
def list_consents(
    patient_id: uuid.UUID,
    request: Request,
    user: CurrentUser = Depends(require_roles(*CADASTRO)),
    db: Session = Depends(get_tenant_db),
):
    try:
        patient = service.get_patient(db, patient_id)
    except service.PatientError as exc:
        raise _http(exc) from None
    history = service.list_consents(db, patient)
    audit.record(
        db, user, "pacientes.consentimentos_lidos", entity_type="patient", entity_id=patient.id,
        request=request,
    )  # fmt: skip
    db.commit()
    return ConsentsOut(
        atuais={
            k: ConsentOut.model_validate(v) if v else None
            for k, v in service.current_consents(history).items()
        },
        historico=[ConsentOut.model_validate(c) for c in history],
    )


@router.post(
    "/{patient_id}/consentimentos",
    response_model=ConsentOut,
    status_code=status.HTTP_201_CREATED,
)
def record_consent(
    patient_id: uuid.UUID,
    body: ConsentIn,
    request: Request,
    user: CurrentUser = Depends(require_roles(*CADASTRO)),
    db: Session = Depends(get_tenant_db),
):
    try:
        patient = service.get_patient(db, patient_id)
        consent = service.record_consent(db, user, patient, body.model_dump())
    except service.PatientError as exc:
        raise _http(exc) from None
    audit.record(
        db, user, "pacientes.consentimento_registrado", entity_type="patient",
        entity_id=patient.id,
        details={"finalidade": consent.purpose.value, "aceito": consent.granted},
        request=request,
    )  # fmt: skip
    db.commit()
    return consent
