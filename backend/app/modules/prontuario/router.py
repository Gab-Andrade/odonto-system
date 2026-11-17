"""Rotas do prontuário — anamnese.

Acesso ao conteúdo clínico: a recepção não tem acesso; ASB, gestor, dentista e admin leem;
dentista, ASB e admin preenchem; admin e gestor montam e publicam os modelos.

LGPD: toda leitura de anamnese de paciente é auditada (lista, resposta e alertas), assim
como as escritas. Os detalhes de auditoria não levam respostas. Ler os modelos (sem dado de
paciente) não é auditado.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core import audit
from app.core.context import CurrentUser
from app.core.roles import Role
from app.modules.identidade.deps import get_tenant_db, require_roles
from app.modules.prontuario import service
from app.modules.prontuario.models import AnamnesisTemplate, VersionStatus
from app.modules.prontuario.schemas import (
    DraftUpdate,
    PatientAlert,
    ResponseCreate,
    ResponseDetail,
    ResponseSummary,
    TemplateCreate,
    TemplateDetail,
    TemplateOut,
    TemplateUpdate,
    VersionOut,
    VersionSummary,
)

router = APIRouter(prefix="/prontuario", tags=["prontuario"])

READ = (Role.ADMIN, Role.GESTOR, Role.DENTISTA, Role.ASB)
FILL = (Role.ADMIN, Role.DENTISTA, Role.ASB)
MANAGE = (Role.ADMIN, Role.GESTOR)


def _http(exc: service.ProntuarioError) -> HTTPException:
    if isinstance(exc, service.NotFound):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, service.Forbidden):
        code = status.HTTP_403_FORBIDDEN
    else:
        code = status.HTTP_409_CONFLICT
    return HTTPException(status_code=code, detail=exc.message)


def _template_out(db: Session, templates: list[AnamnesisTemplate]) -> list[TemplateOut]:
    versions = service.open_versions(db, [t.id for t in templates])
    out = []
    for t in templates:
        open_ = versions[t.id]
        published = open_.get(VersionStatus.PUBLICADA)
        draft = open_.get(VersionStatus.RASCUNHO)
        out.append(
            TemplateOut(
                id=t.id,
                name=t.name,
                description=t.description,
                active=t.active,
                created_at=t.created_at,
                published=VersionSummary.model_validate(published) if published else None,
                draft=VersionSummary.model_validate(draft) if draft else None,
            )
        )
    return out


def _template_detail(db: Session, template: AnamnesisTemplate) -> TemplateDetail:
    base = _template_out(db, [template])[0]
    versions = [VersionSummary.model_validate(v) for v in service.list_versions(db, template)]
    return TemplateDetail(**base.model_dump(), versions=versions)


def _questions(body) -> list[dict]:
    return [q.model_dump(mode="json", exclude_none=True) for q in body.questions]


# ---------- modelos ----------


@router.get("/anamnese/modelos", response_model=list[TemplateOut])
def list_templates(
    incluir_inativos: bool = False,
    _: CurrentUser = Depends(require_roles(*READ)),
    db: Session = Depends(get_tenant_db),
):
    return _template_out(db, service.list_templates(db, include_inactive=incluir_inativos))


@router.post(
    "/anamnese/modelos", response_model=TemplateDetail, status_code=status.HTTP_201_CREATED
)
def create_template(
    body: TemplateCreate,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    try:
        template, _draft = service.create_template(
            db, user, body.name, body.description, _questions(body)
        )
    except service.ProntuarioError as exc:
        raise _http(exc) from None
    audit.record(
        db, user, "prontuario.modelo_criado", entity_type="anamnesis_template",
        entity_id=template.id, request=request,
    )  # fmt: skip
    db.commit()
    return _template_detail(db, template)


@router.get("/anamnese/modelos/{template_id}", response_model=TemplateDetail)
def get_template(
    template_id: uuid.UUID,
    _: CurrentUser = Depends(require_roles(*READ)),
    db: Session = Depends(get_tenant_db),
):
    try:
        template = service.get_template(db, template_id)
    except service.ProntuarioError as exc:
        raise _http(exc) from None
    return _template_detail(db, template)


@router.patch("/anamnese/modelos/{template_id}", response_model=TemplateDetail)
def update_template(
    template_id: uuid.UUID,
    body: TemplateUpdate,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    try:
        template = service.get_template(db, template_id)
        changed = service.update_template(db, template, body.model_dump(exclude_unset=True))
    except service.ProntuarioError as exc:
        raise _http(exc) from None
    if changed:
        audit.record(
            db, user, "prontuario.modelo_alterado", entity_type="anamnesis_template",
            entity_id=template.id, details={"campos": changed}, request=request,
        )  # fmt: skip
        db.commit()
    return _template_detail(db, template)


@router.post(
    "/anamnese/modelos/{template_id}/rascunho",
    response_model=VersionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_draft(
    template_id: uuid.UUID,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    try:
        template = service.get_template(db, template_id)
        draft = service.create_draft(db, user, template)
    except service.ProntuarioError as exc:
        raise _http(exc) from None
    audit.record(
        db, user, "prontuario.rascunho_criado", entity_type="anamnesis_template_version",
        entity_id=draft.id, details={"modelo": str(template.id), "numero": draft.number},
        request=request,
    )  # fmt: skip
    db.commit()
    return draft


@router.get("/anamnese/versoes/{version_id}", response_model=VersionOut)
def get_version(
    version_id: uuid.UUID,
    _: CurrentUser = Depends(require_roles(*READ)),
    db: Session = Depends(get_tenant_db),
):
    try:
        return service.get_version(db, version_id)
    except service.ProntuarioError as exc:
        raise _http(exc) from None


@router.put("/anamnese/versoes/{version_id}", response_model=VersionOut)
def update_draft(
    version_id: uuid.UUID,
    body: DraftUpdate,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    try:
        version = service.get_version(db, version_id)
        service.update_draft(db, version, _questions(body))
    except service.ProntuarioError as exc:
        raise _http(exc) from None
    audit.record(
        db, user, "prontuario.rascunho_alterado", entity_type="anamnesis_template_version",
        entity_id=version.id, details={"perguntas": len(version.questions)}, request=request,
    )  # fmt: skip
    db.commit()
    return version


@router.delete("/anamnese/versoes/{version_id}", status_code=status.HTTP_204_NO_CONTENT)
def discard_draft(
    version_id: uuid.UUID,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    try:
        version = service.get_version(db, version_id)
        details = {"modelo": str(version.template_id), "numero": version.number}
        service.discard_draft(db, version)
    except service.ProntuarioError as exc:
        raise _http(exc) from None
    audit.record(
        db, user, "prontuario.rascunho_descartado", entity_type="anamnesis_template_version",
        entity_id=version_id, details=details, request=request,
    )  # fmt: skip
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/anamnese/versoes/{version_id}/publicar", response_model=VersionOut)
def publish(
    version_id: uuid.UUID,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    try:
        version = service.get_version(db, version_id)
        previous = service.publish(db, user, version)
    except service.ProntuarioError as exc:
        raise _http(exc) from None
    details = {"modelo": str(version.template_id), "numero": version.number}
    if previous is not None:
        details["substituiu"] = previous.number
    audit.record(
        db, user, "prontuario.versao_publicada", entity_type="anamnesis_template_version",
        entity_id=version.id, details=details, request=request,
    )  # fmt: skip
    db.commit()
    return version


# ---------- respostas do paciente ----------


def _summary(row: service.ResponseRow) -> dict:
    r = row.response
    return {
        "id": r.id,
        "patient_id": r.patient_id,
        "template_id": r.template_id,
        "template_name": row.template_name,
        "version_id": r.version_id,
        "version_number": row.version.number,
        "current": row.current,
        "alerts": r.alerts,
        "filled_by": r.filled_by,
        "created_at": r.created_at,
    }


def _detail(row: service.ResponseRow) -> ResponseDetail:
    return ResponseDetail(
        **_summary(row), questions=row.version.questions, answers=row.response.answers
    )


@router.post(
    "/pacientes/{patient_id}/anamneses",
    response_model=ResponseDetail,
    status_code=status.HTTP_201_CREATED,
)
def record_response(
    patient_id: uuid.UUID,
    body: ResponseCreate,
    request: Request,
    user: CurrentUser = Depends(require_roles(*FILL)),
    db: Session = Depends(get_tenant_db),
):
    try:
        patient = service.get_patient(db, patient_id)
        response = service.record_response(
            db, user, patient, body.template_id, body.version_id, body.answers
        )
    except service.ProntuarioError as exc:
        raise _http(exc) from None
    audit.record(
        db, user, "prontuario.anamnese_registrada", entity_type="anamnesis_response",
        entity_id=response.id,
        details={"paciente": str(patient.id), "modelo": str(body.template_id),
                 "alertas": len(response.alerts)},
        request=request,
    )  # fmt: skip
    db.commit()
    return _detail(service.get_response(db, response.id))


@router.get("/pacientes/{patient_id}/anamneses", response_model=list[ResponseSummary])
def list_responses(
    patient_id: uuid.UUID,
    request: Request,
    user: CurrentUser = Depends(require_roles(*READ)),
    db: Session = Depends(get_tenant_db),
):
    try:
        patient = service.get_patient(db, patient_id)
    except service.ProntuarioError as exc:
        raise _http(exc) from None
    rows = service.list_responses(db, patient)
    audit.record(
        db, user, "prontuario.anamneses_listadas", entity_type="patient", entity_id=patient.id,
        details={"resultados": len(rows)}, request=request,
    )  # fmt: skip
    db.commit()
    return [_summary(r) for r in rows]


@router.get("/pacientes/{patient_id}/alertas", response_model=list[PatientAlert])
def patient_alerts(
    patient_id: uuid.UUID,
    request: Request,
    user: CurrentUser = Depends(require_roles(*READ)),
    db: Session = Depends(get_tenant_db),
):
    """Alertas das anamneses atuais (uma por modelo), para o cabeçalho do paciente."""
    try:
        patient = service.get_patient(db, patient_id)
    except service.ProntuarioError as exc:
        raise _http(exc) from None
    rows = service.patient_alerts(db, patient)
    audit.record(
        db, user, "prontuario.alertas_lidos", entity_type="patient", entity_id=patient.id,
        request=request,
    )  # fmt: skip
    db.commit()
    return [
        PatientAlert(
            **alert,
            template_id=row.response.template_id,
            template_name=row.template_name,
            response_id=row.response.id,
            answered_at=row.response.created_at,
        )
        for row in rows
        for alert in row.response.alerts
    ]


@router.get("/anamneses/{response_id}", response_model=ResponseDetail)
def get_response(
    response_id: uuid.UUID,
    request: Request,
    user: CurrentUser = Depends(require_roles(*READ)),
    db: Session = Depends(get_tenant_db),
):
    try:
        row = service.get_response(db, response_id)
    except service.ProntuarioError as exc:
        raise _http(exc) from None
    audit.record(
        db, user, "prontuario.anamnese_lida", entity_type="anamnesis_response",
        entity_id=response_id, details={"paciente": str(row.response.patient_id)},
        request=request,
    )  # fmt: skip
    db.commit()
    return _detail(row)
