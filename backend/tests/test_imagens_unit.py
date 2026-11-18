import uuid
from datetime import date

import pytest
from dicom_fabrica import make_dicom

from app.modules.imagens import dicom


def test_read_extracts_metadata():
    info = dicom.read(make_dicom(modality="PX", study_date="20261110"))
    assert info.modality == "PX"
    assert info.study_date == date(2026, 11, 10)
    assert info.suggested_kind == "panoramica"
    assert info.patient_name == "SILVA^ANA"
    assert info.rows == 2 and info.columns == 2
    assert info.study_uid and info.sop_uid
    assert info.metadata["Manufacturer"] == "Fabricante Teste"
    assert info.transfer_syntax == "1.2.840.10008.1.2.1"


@pytest.mark.parametrize(
    ("modality", "kind"), [("IO", "periapical"), ("CT", "tomografia"), ("XX", "outro")]
)
def test_suggested_kind(modality, kind):
    assert dicom.read(make_dicom(modality=modality)).suggested_kind == kind


def test_rejects_non_dicom():
    with pytest.raises(dicom.DicomError, match="DICM"):
        dicom.read(b"%PDF-1.4 qualquer coisa" * 10)
    with pytest.raises(dicom.DicomError):
        dicom.read(b"\0" * 128 + b"DICM" + b"\xff" * 20)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("20261110", date(2026, 11, 10)),
        ("20261340", None),
        ("", None),
        (None, None),
        ("2026", None),
    ],
)
def test_parse_da(value, expected):
    assert dicom.parse_da(value) == expected


def test_storage_rejects_bad_keys(tmp_path, monkeypatch):
    from app.core import storage

    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    with pytest.raises(storage.StorageError):
        storage.put("../fora.dcm", b"x")
    key = storage.make_key(uuid.uuid4(), uuid.uuid4(), "dcm")
    storage.put(key, b"abc")
    assert storage.get(key) == b"abc"
    storage.delete(key)
    with pytest.raises(storage.StorageError):
        storage.get(key)
