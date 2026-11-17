"""Biblioteca 3D de dentes (genérica, sem dado de clínica nem de paciente).

Os .glb são gerados por `malha3d` e guardados em memória; as respostas têm ETag e podem
ficar no cache do navegador. Exigem login (mesmos papéis que leem o odontograma), mas não
abrem sessão de clínica nem são auditadas: não há dado de paciente aqui. A arcada de um
paciente específico sai de `/odontograma/pacientes/{id}/visualizacao`.
"""

import hashlib

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response

from app.core.context import CurrentUser
from app.modules.identidade.deps import require_roles
from app.modules.odontograma import arcada, malha3d
from app.modules.odontograma.router import READ
from app.modules.odontograma.schemas import LibraryOut

router = APIRouter(prefix="/odontograma/3d", tags=["odontograma"])

GLB_MEDIA_TYPE = "model/gltf-binary"
CACHE = "private, max-age=86400"


def _glb_response(request: Request, data: bytes) -> Response:
    etag = '"' + hashlib.sha256(data).hexdigest()[:32] + '"'
    headers = {"ETag": etag, "Cache-Control": CACHE}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(content=data, media_type=GLB_MEDIA_TYPE, headers=headers)


def parse_teeth(raw: str | None) -> list[int]:
    """`11,12,...` → composição validada (dentição deduzida dos dentes)."""
    if raw is None:
        return arcada.preset(arcada.PERMANENTE, arcada.THIRD_MOLARS)
    try:
        teeth = [int(part) for part in raw.split(",") if part.strip()]
    except ValueError:
        raise HTTPException(422, "Dentes: números FDI separados por vírgula.") from None
    deciduous = [t for t in teeth if t // 10 >= 5]
    if not deciduous:
        dentition = arcada.PERMANENTE
    elif len(deciduous) == len(teeth):
        dentition = arcada.DECIDUA
    else:
        dentition = arcada.MISTA
    try:
        return arcada.validate(dentition, teeth)
    except arcada.ArchRuleError as exc:
        raise HTTPException(422, str(exc)) from None


@router.get("/biblioteca", response_model=LibraryOut)
def library(_: CurrentUser = Depends(require_roles(*READ))):
    return LibraryOut(
        version=malha3d.VERSION,
        units="mm",
        conventions=malha3d.CONVENTIONS,
        teeth=malha3d.library(),
    )


@router.get(
    "/dentes/{tooth}.glb",
    response_class=Response,
    responses={200: {"content": {GLB_MEDIA_TYPE: {}}}, 304: {}},
)
def tooth_model(
    request: Request,
    tooth: int = Path(description="Dente FDI (11–48, 51–85)."),
    _: CurrentUser = Depends(require_roles(*READ)),
):
    try:
        data = malha3d.tooth_glb(tooth)
    except ValueError:
        raise HTTPException(404, "Dente inexistente na numeração FDI.") from None
    return _glb_response(request, data)


@router.get(
    "/arcada.glb",
    response_class=Response,
    responses={200: {"content": {GLB_MEDIA_TYPE: {}}}, 304: {}},
)
def arch_model(
    request: Request,
    dentes: str | None = Query(
        None,
        max_length=400,
        description="Dentes FDI separados por vírgula; vazio: permanente com 32 dentes.",
    ),
    _: CurrentUser = Depends(require_roles(*READ)),
):
    return _glb_response(request, malha3d.arch_glb(tuple(parse_teeth(dentes))))
