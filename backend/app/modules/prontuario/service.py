"""Regras da anamnese (e erros comuns do prontuário). Commit e auditoria ficam com o router."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.context import CurrentUser
from app.modules.pacientes import service as pacientes_service
from app.modules.pacientes.models import Patient
from app.modules.prontuario import anamnese
from app.modules.prontuario.models import (
    AnamnesisResponse,
    AnamnesisTemplate,
    AnamnesisTemplateVersion,
    VersionStatus,
)

Version = AnamnesisTemplateVersion


class ProntuarioError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFound(ProntuarioError):
    pass


class RuleViolation(ProntuarioError):
    pass


class Forbidden(ProntuarioError):
    """Papel permitido, mas a pessoa não é a autora (ex.: evolução de outro dentista)."""


def get_patient(db: Session, patient_id: uuid.UUID) -> Patient:
    try:
        return pacientes_service.get_patient(db, patient_id)
    except pacientes_service.NotFound as exc:
        raise NotFound(exc.message) from None


# ---------- modelos e versões ----------


def get_template(db: Session, template_id: uuid.UUID) -> AnamnesisTemplate:
    template = db.get(AnamnesisTemplate, template_id)
    if template is None:  # de outra clínica também cai aqui (RLS)
        raise NotFound("Modelo de anamnese não encontrado.")
    return template


def get_version(db: Session, version_id: uuid.UUID) -> Version:
    version = db.get(Version, version_id)
    if version is None:
        raise NotFound("Versão do modelo não encontrada.")
    return version


def _ensure_name_free(db: Session, name: str, exclude_id: uuid.UUID | None = None) -> None:
    query = select(AnamnesisTemplate.id).where(AnamnesisTemplate.name == name)
    if exclude_id is not None:
        query = query.where(AnamnesisTemplate.id != exclude_id)
    if db.scalar(query.limit(1)) is not None:
        raise RuleViolation("Já existe um modelo de anamnese com este nome.")


def open_versions(
    db: Session, template_ids: list[uuid.UUID]
) -> dict[uuid.UUID, dict[VersionStatus, Version]]:
    """Publicada e rascunho de cada modelo (substituídas ficam de fora)."""
    result: dict[uuid.UUID, dict[VersionStatus, Version]] = {t: {} for t in template_ids}
    if not template_ids:
        return result
    rows = db.scalars(
        select(Version).where(
            Version.template_id.in_(template_ids), Version.status != VersionStatus.SUBSTITUIDA
        )
    )
    for v in rows:
        result[v.template_id][v.status] = v
    return result


def list_templates(db: Session, *, include_inactive: bool) -> list[AnamnesisTemplate]:
    query = select(AnamnesisTemplate).order_by(AnamnesisTemplate.name)
    if not include_inactive:
        query = query.where(AnamnesisTemplate.active.is_(True))
    return list(db.scalars(query))


def list_versions(db: Session, template: AnamnesisTemplate) -> list[Version]:
    return list(
        db.scalars(
            select(Version)
            .where(Version.template_id == template.id)
            .order_by(Version.number.desc())
        )
    )


def create_template(
    db: Session,
    user: CurrentUser,
    name: str,
    description: str | None,
    questions: list[dict[str, Any]],
) -> tuple[AnamnesisTemplate, Version]:
    _ensure_name_free(db, name)
    template = AnamnesisTemplate(
        clinic_id=user.clinic_id, name=name, description=description, created_by=user.user_id
    )
    db.add(template)
    db.flush()
    draft = Version(
        clinic_id=user.clinic_id,
        template_id=template.id,
        number=1,
        status=VersionStatus.RASCUNHO,
        questions=questions,
        created_by=user.user_id,
    )
    db.add(draft)
    db.flush()
    return template, draft


def update_template(db: Session, template: AnamnesisTemplate, changes: dict[str, Any]) -> list[str]:
    for name in ("name", "active"):
        if name in changes and changes[name] is None:
            raise RuleViolation(f"O campo {name} não pode ficar vazio.")
    if changes.get("name") and changes["name"] != template.name:
        _ensure_name_free(db, changes["name"], exclude_id=template.id)
    changed = []
    for name, value in changes.items():
        if getattr(template, name) != value:
            setattr(template, name, value)
            changed.append(name)
    db.flush()
    return sorted(changed)


def create_draft(db: Session, user: CurrentUser, template: AnamnesisTemplate) -> Version:
    """Novo rascunho a partir da versão publicada (ou vazio, se não houver)."""
    current = open_versions(db, [template.id])[template.id]
    if VersionStatus.RASCUNHO in current:
        raise RuleViolation("Este modelo já tem um rascunho em edição.")
    published = current.get(VersionStatus.PUBLICADA)
    last = db.scalar(select(func.max(Version.number)).where(Version.template_id == template.id))
    draft = Version(
        clinic_id=user.clinic_id,
        template_id=template.id,
        number=(last or 0) + 1,
        status=VersionStatus.RASCUNHO,
        questions=list(published.questions) if published else [],
        created_by=user.user_id,
    )
    db.add(draft)
    db.flush()
    return draft


def _ensure_draft(version: Version) -> None:
    if version.status is not VersionStatus.RASCUNHO:
        raise RuleViolation("Só o rascunho pode ser alterado; crie um novo rascunho.")


def update_draft(db: Session, version: Version, questions: list[dict[str, Any]]) -> None:
    _ensure_draft(version)
    version.questions = questions
    db.flush()


def discard_draft(db: Session, version: Version) -> None:
    _ensure_draft(version)
    db.delete(version)
    db.flush()


def publish(db: Session, user: CurrentUser, version: Version) -> Version | None:
    """Publica o rascunho; a publicada anterior vira substituída. Devolve a anterior."""
    _ensure_draft(version)
    if not version.questions:
        raise RuleViolation("Inclua ao menos uma pergunta antes de publicar.")
    previous = open_versions(db, [version.template_id])[version.template_id].get(
        VersionStatus.PUBLICADA
    )
    if previous is not None:
        previous.status = VersionStatus.SUBSTITUIDA
        # Antes de publicar a nova: o índice único parcial admite uma publicada por modelo,
        # e o flush não garante a ordem dos UPDATEs.
        db.flush()
    version.status = VersionStatus.PUBLICADA
    version.published_at = datetime.now(UTC)
    version.published_by = user.user_id
    db.flush()
    return previous


# ---------- respostas ----------


def record_response(
    db: Session,
    user: CurrentUser,
    patient: Patient,
    template_id: uuid.UUID,
    version_id: uuid.UUID,
    answers: dict[str, Any],
) -> AnamnesisResponse:
    if not patient.active:
        raise RuleViolation("Paciente inativo: reative o cadastro antes.")
    template = get_template(db, template_id)
    if not template.active:
        raise RuleViolation("Este modelo de anamnese está desativado.")
    published = open_versions(db, [template.id])[template.id].get(VersionStatus.PUBLICADA)
    if published is None:
        raise RuleViolation("Este modelo ainda não tem versão publicada.")
    if published.id != version_id:
        raise RuleViolation("O modelo foi atualizado depois que o formulário abriu; recarregue.")
    try:
        clean = anamnese.validate_answers(published.questions, answers)
    except anamnese.AnamnesisRuleError as exc:
        raise RuleViolation(str(exc)) from None
    response = AnamnesisResponse(
        clinic_id=user.clinic_id,
        patient_id=patient.id,
        template_id=template.id,
        version_id=published.id,
        answers=clean,
        alerts=anamnese.compute_alerts(published.questions, clean),
        filled_by=user.user_id,
    )
    db.add(response)
    db.flush()
    db.refresh(response)  # created_at do servidor
    return response


@dataclass
class ResponseRow:
    response: AnamnesisResponse
    template_name: str
    version: Version
    current: bool


def _newest_first():
    return (AnamnesisResponse.created_at.desc(), AnamnesisResponse.id.desc())


def _current_ids(db: Session, patient_id: uuid.UUID) -> set[uuid.UUID]:
    """A resposta mais recente de cada modelo."""
    query = (
        select(AnamnesisResponse.id)
        .where(AnamnesisResponse.patient_id == patient_id)
        .distinct(AnamnesisResponse.template_id)
        .order_by(AnamnesisResponse.template_id, *_newest_first())
    )
    return set(db.scalars(query))


def _rows(db: Session, query, current: set[uuid.UUID]) -> list[ResponseRow]:
    return [
        ResponseRow(response=r, template_name=name, version=v, current=r.id in current)
        for r, name, v in db.execute(query).all()
    ]


def _base_query():
    return (
        select(AnamnesisResponse, AnamnesisTemplate.name, Version)
        .join(AnamnesisTemplate, AnamnesisTemplate.id == AnamnesisResponse.template_id)
        .join(Version, Version.id == AnamnesisResponse.version_id)
    )


def list_responses(db: Session, patient: Patient) -> list[ResponseRow]:
    query = (
        _base_query().where(AnamnesisResponse.patient_id == patient.id).order_by(*_newest_first())
    )
    return _rows(db, query, _current_ids(db, patient.id))


def get_response(db: Session, response_id: uuid.UUID) -> ResponseRow:
    rows = _rows(db, _base_query().where(AnamnesisResponse.id == response_id), set())
    if not rows:
        raise NotFound("Anamnese não encontrada.")
    row = rows[0]
    row.current = response_id in _current_ids(db, row.response.patient_id)
    return row


def patient_alerts(db: Session, patient: Patient) -> list[ResponseRow]:
    """Respostas atuais (uma por modelo) que têm alertas."""
    current = _current_ids(db, patient.id)
    if not current:
        return []
    query = (
        _base_query()
        .where(
            AnamnesisResponse.id.in_(current),
            func.jsonb_array_length(AnamnesisResponse.alerts) > 0,
        )
        .order_by(AnamnesisTemplate.name)
    )
    return _rows(db, query, current)
