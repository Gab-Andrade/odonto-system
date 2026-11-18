"""Leitura de metadados DICOM com pydicom (puro, testável sem banco).

Só o cabeçalho é lido (`stop_before_pixels`): não há visualizador por enquanto, e a
imagem fica guardada como veio. Arquivos sem o preâmbulo "DICM" são recusados.
"""

import io
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pydicom
from pydicom.errors import InvalidDicomError

# Tipos de exame do prontuário (PLANO 4.6).
KINDS = ("periapical", "interproximal", "panoramica", "tomografia", "outro")

# Modalidade DICOM → tipo sugerido (o usuário pode trocar).
MODALITY_KIND = {
    "PX": "panoramica",  # radiografia panorâmica
    "IO": "periapical",  # intraoral (periapical ou interproximal: o padrão é periapical)
    "CT": "tomografia",
    "DX": "outro",
    "CR": "outro",
}

# Tags guardadas no JSON de metadados (nomes do dicionário DICOM).
KEPT_TAGS = (
    "SOPClassUID",
    "Modality",
    "StudyDate",
    "StudyTime",
    "StudyDescription",
    "SeriesDescription",
    "SeriesNumber",
    "InstanceNumber",
    "BodyPartExamined",
    "ImageLaterality",
    "ViewPosition",
    "Manufacturer",
    "ManufacturerModelName",
    "StationName",
    "InstitutionName",
    "Rows",
    "Columns",
    "BitsStored",
    "PixelSpacing",
    "ImagerPixelSpacing",
    "PhotometricInterpretation",
    "KVP",
    "ExposureTime",
    "XRayTubeCurrent",
    "NumberOfFrames",
)

MAX_TEXT = 200


class DicomError(ValueError):
    pass


@dataclass
class DicomInfo:
    modality: str | None = None
    study_uid: str | None = None
    series_uid: str | None = None
    sop_uid: str | None = None
    study_date: date | None = None
    study_description: str | None = None
    series_description: str | None = None
    body_part: str | None = None
    manufacturer: str | None = None
    rows: int | None = None
    columns: int | None = None
    patient_name: str | None = None  # para conferir se o arquivo é mesmo deste paciente
    transfer_syntax: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def suggested_kind(self) -> str:
        return MODALITY_KIND.get(self.modality or "", "outro")


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().replace("\x00", "")
    return text[:MAX_TEXT] or None


def _int(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def parse_da(value: Any) -> date | None:
    """Data DICOM (DA, "AAAAMMDD"); inválida ou vazia vira None."""
    text = _text(value)
    if not text or len(text) != 8 or not text.isdigit():
        return None
    try:
        return date(int(text[:4]), int(text[4:6]), int(text[6:]))
    except ValueError:
        return None


def _jsonable(value: Any) -> Any:
    if isinstance(value, (list, tuple)) or type(value).__name__ == "MultiValue":
        return [_jsonable(v) for v in value]
    if isinstance(value, (int, float)):
        return value
    return _text(value)


def read(data: bytes) -> DicomInfo:
    if len(data) < 132 or data[128:132] != b"DICM":
        raise DicomError("O arquivo não é DICOM (falta o cabeçalho 'DICM').")
    try:
        ds = pydicom.dcmread(io.BytesIO(data), stop_before_pixels=True)
    except (InvalidDicomError, ValueError, TypeError, EOFError, OSError, KeyError) as exc:
        raise DicomError("Arquivo DICOM inválido ou corrompido.") from exc

    # Um arquivo truncado ou "DICOM vazio" é lido pelo pydicom só com avisos: exige ao
    # menos a identificação da imagem.
    if not _text(ds.get("SOPInstanceUID")):
        raise DicomError("Arquivo DICOM inválido: falta a identificação da imagem (SOP UID).")

    metadata = {}
    for tag in KEPT_TAGS:
        try:
            value = ds.get(tag)
        except (ValueError, TypeError, KeyError):
            continue
        if value is not None and value != "":
            metadata[tag] = _jsonable(value)

    meta = getattr(ds, "file_meta", None)
    return DicomInfo(
        modality=_text(ds.get("Modality")),
        study_uid=_text(ds.get("StudyInstanceUID")),
        series_uid=_text(ds.get("SeriesInstanceUID")),
        sop_uid=_text(ds.get("SOPInstanceUID")),
        study_date=parse_da(ds.get("StudyDate")),
        study_description=_text(ds.get("StudyDescription")),
        series_description=_text(ds.get("SeriesDescription")),
        body_part=_text(ds.get("BodyPartExamined")),
        manufacturer=_text(ds.get("Manufacturer")),
        rows=_int(ds.get("Rows")),
        columns=_int(ds.get("Columns")),
        patient_name=_text(ds.get("PatientName")),
        transfer_syntax=_text(meta.get("TransferSyntaxUID")) if meta is not None else None,
        metadata=metadata,
    )
