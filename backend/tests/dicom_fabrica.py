"""Gera arquivos DICOM pequenos em memória para os testes."""

import io

from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

DX_SOP_CLASS = "1.2.840.10008.5.1.4.1.1.1.1"  # Digital X-Ray Image Storage


def make_dicom(
    *,
    modality: str = "PX",
    patient_name: str = "SILVA^ANA",
    study_date: str = "20261110",
    description: str = "Panoramica",
    seed: int = 0,
) -> bytes:
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = DX_SOP_CLASS
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian

    ds = Dataset()
    ds.file_meta = meta
    ds.preamble = b"\0" * 128
    ds.SOPClassUID = DX_SOP_CLASS
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.StudyInstanceUID = generate_uid()
    ds.SeriesInstanceUID = generate_uid()
    ds.Modality = modality
    ds.PatientName = patient_name
    ds.PatientID = "123"
    ds.StudyDate = study_date
    ds.StudyDescription = description
    ds.Manufacturer = "Fabricante Teste"
    ds.Rows = 2
    ds.Columns = 2
    ds.BitsAllocated = 8
    ds.BitsStored = 8
    ds.HighBit = 7
    ds.SamplesPerPixel = 1
    ds.PixelRepresentation = 0
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.PixelData = bytes([seed % 256, 1, 2, 3])
    buf = io.BytesIO()
    ds.save_as(buf, enforce_file_format=True)
    return buf.getvalue()
