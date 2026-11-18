"""Rotas dos exames de imagem (raio-X DICOM) do prontuário.

Conteúdo clínico: recepção não tem acesso. Enviam e classificam: admin, dentista e ASB.
Leem também o gestor. Invalidam: admin e dentista. Toda leitura e escrita é auditada.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi import status as http
from sqlalchemy.orm import Session

from app.core import audit, storage
from app.core.config import get_settings
from app.core.context import CurrentUser
from app.core.roles import Role
from app.modules.identidade.deps import get_tenant_db, require_roles
from app.modules.imagens import service
from app.modules.imagens.models import ImageKind
from app.modules.imagens.schemas import ExamDetail, ExamOut, ExamUpdate, InvalidateIn

router = APIRouter(prefix="/imagens", tags=["imagens"])

READ = (Role.ADMIN, Role.GESTOR, Role.DENTISTA, Role.ASB)
WRITE = (Role.ADMIN, Role.DENTISTA, Role.ASB)
INVALIDATE = (Role.ADMIN, Role.DENTISTA)
DICOM_MEDIA_TYPE = "application/dicom"


def _http(exc: service.ImagingError) -> HTTPException:
    if isinstance(exc, service.Unavailable):
        return HTTPException(status_code=503, detail=exc.message)
    code = 404 if isinstance(exc, service.NotFound) else 422
    return HTTPException(status_code=code, detail=exc.message)


def _parse_teeth(value: str | None) -> list[int] | None:
    if value is None or not value.strip():
        return None
    try:
        return [int(t) for t in value.replace(";", ",").split(",") if t.strip()]
    except ValueError:
        raise HTTPException(422, "Dentes: números FDI separados por vírgula.") from None


def _read_limited(upload: UploadFile) -> bytes:
    limit = get_settings().max_dicom_bytes
    data = upload.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"Arquivo acima de {limit // (1024 * 1024)} MB.")
    if not data:
        raise HTTPException(422, "Arquivo vazio.")
    return data


@router.post(
    "/pacientes/{patient_id}/exames",
    response_model=ExamDetail,
    status_code=http.HTTP_201_CREATED,
)
def upload_exam(
    patient_id: uuid.UUID,
    request: Request,
    arquivo: UploadFile = File(description="Arquivo DICOM (.dcm) de uma imagem."),
    tipo: ImageKind | None = Form(None, description="Padrão: sugerido pela modalidade."),
    dentes: str | None = Form(None, description='Dentes FDI, ex.: "36,37".'),
    data_exame: date | None = Form(None, description="Padrão: a data gravada no DICOM."),
    atendimento_id: uuid.UUID | None = Form(None),
    observacao: str | None = Form(None, max_length=1000),
    user: CurrentUser = Depends(require_roles(*WRITE)),
    db: Session = Depends(get_tenant_db),
):
    data = _read_limited(arquivo)
    fields = {
        "kind": tipo,
        "teeth": _parse_teeth(dentes),
        "exam_date": data_exame,
        "encounter_id": atendimento_id,
        "notes": (observacao or "").strip() or None,
    }
    try:
        patient = service.get_patient(db, patient_id)
        exam = service.upload(db, user, patient, data, arquivo.filename, fields)
    except service.ImagingError as exc:
        raise _http(exc) from None
    try:
        audit.record(
            db,
            user,
            "imagens.exame_anexado",
            entity_type="paciente",
            entity_id=patient_id,
            details={"exame": str(exam.id), "tipo": exam.kind.value, "bytes": exam.size_bytes},
            request=request,
        )
        db.commit()
    except Exception:
        # A transação não valeu: não deixa arquivo órfão. Se nem apagar der, o erro
        # original é o que importa.
        try:
            storage.delete(exam.storage_key)
        except storage.StorageError:
            pass
        raise
    return ExamDetail.model_validate(exam)


@router.get("/pacientes/{patient_id}/exames", response_model=list[ExamOut])
def list_exams(
    patient_id: uuid.UUID,
    request: Request,
    incluir_invalidados: bool = False,
    user: CurrentUser = Depends(require_roles(*READ)),
    db: Session = Depends(get_tenant_db),
):
    try:
        patient = service.get_patient(db, patient_id)
    except service.ImagingError as exc:
        raise _http(exc) from None
    exams = service.list_exams(db, patient, include_invalidated=incluir_invalidados)
    audit.record(
        db,
        user,
        "imagens.exames_listados",
        entity_type="paciente",
        entity_id=patient_id,
        details={"resultados": len(exams)},
        request=request,
    )
    db.commit()
    return exams


def _exam(db: Session, exam_id: uuid.UUID):
    try:
        return service.get_exam(db, exam_id)
    except service.ImagingError as exc:
        raise _http(exc) from None


@router.get("/exames/{exam_id}", response_model=ExamDetail)
def get_exam(
    exam_id: uuid.UUID,
    request: Request,
    user: CurrentUser = Depends(require_roles(*READ)),
    db: Session = Depends(get_tenant_db),
):
    exam = _exam(db, exam_id)
    audit.record(
        db,
        user,
        "imagens.exame_lido",
        entity_type="paciente",
        entity_id=exam.patient_id,
        details={"exame": str(exam.id)},
        request=request,
    )
    db.commit()
    return exam


@router.get(
    "/exames/{exam_id}/arquivo",
    response_class=Response,
    responses={200: {"content": {DICOM_MEDIA_TYPE: {}}}},
)
def download_exam(
    exam_id: uuid.UUID,
    request: Request,
    user: CurrentUser = Depends(require_roles(*READ)),
    db: Session = Depends(get_tenant_db),
):
    """O arquivo DICOM como foi enviado (para abrir num visualizador DICOM)."""
    exam = _exam(db, exam_id)
    try:
        data = service.read_file(exam)
    except service.ImagingError as exc:
        raise _http(exc) from None
    audit.record(
        db,
        user,
        "imagens.exame_baixado",
        entity_type="paciente",
        entity_id=exam.patient_id,
        details={"exame": str(exam.id)},
        request=request,
    )
    db.commit()
    return Response(
        content=data,
        media_type=DICOM_MEDIA_TYPE,
        headers={
            "Content-Disposition": f'attachment; filename="exame-{exam.id}.dcm"',
            "Cache-Control": "no-store",
        },
    )


@router.patch("/exames/{exam_id}", response_model=ExamDetail)
def update_exam(
    exam_id: uuid.UUID,
    body: ExamUpdate,
    request: Request,
    user: CurrentUser = Depends(require_roles(*WRITE)),
    db: Session = Depends(get_tenant_db),
):
    exam = _exam(db, exam_id)
    try:
        changed = service.update(db, exam, body.model_dump(exclude_unset=True))
    except service.ImagingError as exc:
        raise _http(exc) from None
    audit.record(
        db,
        user,
        "imagens.exame_alterado",
        entity_type="paciente",
        entity_id=exam.patient_id,
        details={"exame": str(exam.id), "campos": changed},
        request=request,
    )
    db.commit()
    return exam


@router.post("/exames/{exam_id}/invalidar", response_model=ExamDetail)
def invalidate_exam(
    exam_id: uuid.UUID,
    body: InvalidateIn,
    request: Request,
    user: CurrentUser = Depends(require_roles(*INVALIDATE)),
    db: Session = Depends(get_tenant_db),
):
    """Exame enviado por engano (outro paciente, arquivo errado): sai da listagem padrão,
    mas continua guardado."""
    exam = _exam(db, exam_id)
    try:
        service.invalidate(db, user, exam, body.reason)
    except service.ImagingError as exc:
        raise _http(exc) from None
    audit.record(
        db,
        user,
        "imagens.exame_invalidado",
        entity_type="paciente",
        entity_id=exam.patient_id,
        details={"exame": str(exam.id)},
        request=request,
    )
    db.commit()
    return exam
