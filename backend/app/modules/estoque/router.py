import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core import audit
from app.core.context import CurrentUser
from app.core.roles import Role
from app.modules.estoque import service
from app.modules.estoque.schemas import (
    MaterialCostOut,
    MaterialCreate,
    MaterialOut,
    MaterialUpdate,
)
from app.modules.identidade.deps import get_tenant_db, require_roles

router = APIRouter(prefix="/estoque", tags=["estoque"])

# Cadastram materiais e veem custos.
MANAGE = (Role.ADMIN, Role.GESTOR)
# Consultam o cadastro (sem custo): quem usa e repõe material no dia a dia.
READ = (Role.ADMIN, Role.GESTOR, Role.DENTISTA, Role.ASB)


def _http(exc: service.StockError) -> HTTPException:
    code = status.HTTP_404_NOT_FOUND if isinstance(exc, service.NotFound) else 409
    return HTTPException(status_code=code, detail=exc.message)


def _out(user: CurrentUser, material) -> MaterialOut:
    schema = MaterialCostOut if user.role in MANAGE else MaterialOut
    return schema.model_validate(material)


@router.get("/materiais", response_model=list[MaterialCostOut] | list[MaterialOut])
def list_materials(
    incluir_inativos: bool = Query(False),
    user: CurrentUser = Depends(require_roles(*READ)),
    db: Session = Depends(get_tenant_db),
):
    """Custo unitário só aparece para administrador e gestor."""
    return [_out(user, m) for m in service.list_materials(db, include_inactive=incluir_inativos)]


@router.post("/materiais", response_model=MaterialCostOut, status_code=status.HTTP_201_CREATED)
def create_material(
    body: MaterialCreate,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    try:
        material = service.create_material(db, user, **body.model_dump())
    except service.StockError as exc:
        raise _http(exc) from None
    audit.record(
        db, user, "estoque.material_criado",
        entity_type="material", entity_id=material.id,
        details={"unit_cost": str(material.unit_cost)}, request=request,
    )  # fmt: skip
    db.commit()
    return material


@router.get("/materiais/{material_id}", response_model=MaterialCostOut | MaterialOut)
def get_material(
    material_id: uuid.UUID,
    user: CurrentUser = Depends(require_roles(*READ)),
    db: Session = Depends(get_tenant_db),
):
    try:
        return _out(user, service.get_material(db, material_id))
    except service.StockError as exc:
        raise _http(exc) from None


@router.patch("/materiais/{material_id}", response_model=MaterialCostOut)
def update_material(
    material_id: uuid.UUID,
    body: MaterialUpdate,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    """Desative (active=false) em vez de excluir: fichas técnicas podem usar o material."""
    changes = body.model_dump(exclude_unset=True)
    try:
        material = service.update_material(db, service.get_material(db, material_id), changes)
    except service.StockError as exc:
        raise _http(exc) from None
    audit.record(
        db, user, "estoque.material_alterado",
        entity_type="material", entity_id=material.id,
        details={k: str(v) for k, v in changes.items()}, request=request,
    )  # fmt: skip
    db.commit()
    return material
