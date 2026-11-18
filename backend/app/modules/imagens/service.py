"""Regras dos exames de imagem. O commit e a auditoria ficam com o router."""

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import storage
from app.core.context import CurrentUser
from app.modules.imagens import dicom
from app.modules.imagens.models import ImageKind, ImagingExam
from app.modules.odontograma import regras as odonto_rules
from app.modules.pacientes import service as pacientes
from app.modules.pacientes.models import Patient
from app.modules.prontuario.models import Encounter

MAX_FILE_NAME = 255


class ImagingError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFound(ImagingError):
    pass


class RuleViolation(ImagingError):
    pass


class Unavailable(ImagingError):
    """Armazenamento fora do ar (ex.: S3)."""


def get_patient(db: Session, patient_id: uuid.UUID) -> Patient:
    try:
        return pacientes.get_patient(db, patient_id)
    except pacientes.NotFound as exc:
        raise NotFound(exc.message) from None


def get_exam(db: Session, exam_id: uuid.UUID) -> ImagingExam:
    exam = db.get(ImagingExam, exam_id)
    if exam is None:
        raise NotFound("Exame não encontrado.")
    return exam


def check_teeth(teeth: list[int] | None) -> list[int] | None:
    if not teeth:
        return None
    bad = [t for t in teeth if not odonto_rules.is_valid_tooth(t)]
    if bad:
        raise RuleViolation(f"Dente fora da numeração FDI: {bad[0]}.")
    if len(set(teeth)) != len(teeth):
        raise RuleViolation("Dente repetido na lista.")
    return sorted(teeth)


def _clean_name(name: str | None) -> str:
    name = (name or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    return (name or "exame.dcm")[:MAX_FILE_NAME]


def upload(
    db: Session,
    user: CurrentUser,
    patient: Patient,
    data: bytes,
    file_name: str | None,
    fields: dict[str, Any],
) -> ImagingExam:
    """Lê os metadados, grava o arquivo e cria o registro. Devolve o exame (com a chave de
    armazenamento já gravada; se o commit falhar, quem chama apaga o arquivo)."""
    if not patient.active:
        raise RuleViolation("Paciente inativo: reative o cadastro antes.")
    try:
        info = dicom.read(data)
    except dicom.DicomError as exc:
        raise RuleViolation(str(exc)) from None

    digest = hashlib.sha256(data).hexdigest()
    duplicate = db.scalar(
        select(ImagingExam.id).where(
            ImagingExam.patient_id == patient.id, ImagingExam.sha256 == digest
        )
    )
    if duplicate is not None:
        raise RuleViolation("Este arquivo já foi anexado a este paciente.")

    encounter_id = fields.get("encounter_id")
    if encounter_id is not None:
        encounter = db.get(Encounter, encounter_id)
        if encounter is None or encounter.patient_id != patient.id:
            raise RuleViolation("Atendimento não encontrado para este paciente.")

    exam_id = uuid.uuid4()
    key = storage.make_key(user.clinic_id, exam_id, "dcm")
    exam = ImagingExam(
        id=exam_id,
        clinic_id=user.clinic_id,
        patient_id=patient.id,
        encounter_id=encounter_id,
        kind=fields.get("kind") or ImageKind(info.suggested_kind),
        teeth=check_teeth(fields.get("teeth")),
        exam_date=fields.get("exam_date") or info.study_date,
        notes=fields.get("notes"),
        file_name=_clean_name(file_name),
        size_bytes=len(data),
        sha256=digest,
        storage_key=key,
        modality=info.modality and info.modality[:16],
        study_uid=info.study_uid and info.study_uid[:64],
        series_uid=info.series_uid and info.series_uid[:64],
        sop_uid=info.sop_uid and info.sop_uid[:64],
        study_date=info.study_date,
        study_description=info.study_description,
        series_description=info.series_description,
        body_part=info.body_part and info.body_part[:64],
        manufacturer=info.manufacturer,
        rows=info.rows,
        columns=info.columns,
        dicom_patient_name=info.patient_name,
        dicom_metadata={**info.metadata, "TransferSyntaxUID": info.transfer_syntax},
        uploaded_by=user.user_id,
    )
    db.add(exam)
    db.flush()
    try:
        storage.put(key, data)
    except storage.StorageError as exc:
        raise Unavailable(str(exc)) from None
    return exam


def list_exams(
    db: Session, patient: Patient, *, include_invalidated: bool = False
) -> list[ImagingExam]:
    query = select(ImagingExam).where(ImagingExam.patient_id == patient.id)
    if not include_invalidated:
        query = query.where(ImagingExam.invalidated_at.is_(None))
    return list(
        db.scalars(
            query.order_by(ImagingExam.exam_date.desc().nulls_last(), ImagingExam.created_at.desc())
        )
    )


def _ensure_valid(exam: ImagingExam) -> None:
    if exam.invalidated_at is not None:
        raise RuleViolation("Exame invalidado não pode ser alterado.")


def update(db: Session, exam: ImagingExam, changes: dict[str, Any]) -> list[str]:
    """Muda só a classificação clínica (tipo, dentes, data, observação)."""
    _ensure_valid(exam)
    if "kind" in changes and changes["kind"] is None:
        raise RuleViolation("Informe o tipo do exame.")
    if "teeth" in changes:
        changes["teeth"] = check_teeth(changes["teeth"])
    changed = [k for k, v in changes.items() if getattr(exam, k) != v]
    for key in changed:
        setattr(exam, key, changes[key])
    db.flush()
    return sorted(changed)


def invalidate(db: Session, user: CurrentUser, exam: ImagingExam, reason: str) -> None:
    _ensure_valid(exam)
    exam.invalidated_at = datetime.now(UTC)
    exam.invalidated_by = user.user_id
    exam.invalidation_reason = reason
    db.flush()


def read_file(exam: ImagingExam) -> bytes:
    # Defesa em profundidade: a chave é gerada pelo servidor na pasta da clínica.
    if not exam.storage_key.startswith(f"{exam.clinic_id}/"):
        raise NotFound("Arquivo não encontrado no armazenamento.")
    try:
        return storage.get(exam.storage_key)
    except storage.StorageUnavailable as exc:
        raise Unavailable(str(exc)) from None
    except storage.StorageError as exc:
        raise NotFound(str(exc)) from None
