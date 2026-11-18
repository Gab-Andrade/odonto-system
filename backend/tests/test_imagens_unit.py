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

    monkeypatch.setattr(storage, "backend", lambda: storage.LocalBackend(tmp_path))
    with pytest.raises(storage.StorageError):
        storage.put("../fora.dcm", b"x")
    key = storage.make_key(uuid.uuid4(), uuid.uuid4(), "dcm")
    storage.put(key, b"abc")
    assert storage.get(key) == b"abc"
    storage.delete(key)
    with pytest.raises(storage.StorageError):
        storage.get(key)


class _FakeS3:
    """Imita o cliente boto3 só no que o backend usa."""

    class NoSuchKey(Exception):
        pass

    def __init__(self):
        self.objects = {}
        self.calls = []

    def put_object(self, **kw):
        self.calls.append(kw)
        self.objects[(kw["Bucket"], kw["Key"])] = kw["Body"]

    def get_object(self, Bucket, Key):  # noqa: N803 - nomes do boto3
        if (Bucket, Key) not in self.objects:
            raise self.NoSuchKey("NoSuchKey")
        data = self.objects[(Bucket, Key)]

        class _Body:
            def read(self):
                return data

        return {"Body": _Body()}

    def delete_object(self, Bucket, Key):  # noqa: N803
        self.objects.pop((Bucket, Key), None)


def test_s3_backend_uses_prefix_encryption_and_same_keys():
    from app.core import storage

    fake = _FakeS3()
    s3 = storage.S3Backend(fake, "bucket", prefix="/producao/")
    key = storage.make_key(uuid.uuid4(), uuid.uuid4(), "dcm")
    s3.put(key, b"dicom")
    assert ("bucket", f"producao/{key}") in fake.objects
    assert fake.calls[0]["ServerSideEncryption"] == "AES256"
    assert s3.get(key) == b"dicom"
    s3.delete(key)
    with pytest.raises(storage.StorageError):
        s3.get(key)
    with pytest.raises(storage.StorageError):
        s3.put("../fora.dcm", b"x")


def test_s3_requires_bucket():
    from app.core.config import Settings

    with pytest.raises(ValueError, match="S3_BUCKET"):
        Settings(storage_backend="s3", s3_bucket=None)
    assert Settings(storage_backend="s3", s3_bucket="b").s3_bucket == "b"


def test_s3_failures_become_storage_unavailable():
    from app.core import storage

    class _Quebrado(_FakeS3):
        def put_object(self, **kw):
            raise RuntimeError("AccessDenied")

        def get_object(self, Bucket, Key):  # noqa: N803
            raise RuntimeError("EndpointConnectionError")

    s3 = storage.S3Backend(_Quebrado(), "bucket")
    key = storage.make_key(uuid.uuid4(), uuid.uuid4(), "dcm")
    with pytest.raises(storage.StorageUnavailable):
        s3.put(key, b"x")
    with pytest.raises(storage.StorageUnavailable):
        s3.get(key)
