import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core import audit
from app.core.context import CurrentUser
from app.core.roles import Role
from app.modules.identidade.deps import get_tenant_db, require_roles
from app.modules.precificacao import service
from app.modules.precificacao.schemas import (
    AssignmentCreate,
    AssignmentOut,
    ItemOut,
    ItemsReplace,
    PublishIn,
    ResolutionOut,
    ResolveIn,
    SnapshotOut,
    TableCreate,
    TableOut,
    TableUpdate,
    VersionOut,
    VersionUpdate,
)

router = APIRouter(prefix="/precificacao", tags=["precificacao"])

# Quem configura tabelas e atribuições.
MANAGE = (Role.ADMIN, Role.GESTOR)
# Quem consulta tabelas e resolve preços (montagem de orçamento).
READ = (Role.ADMIN, Role.GESTOR, Role.DENTISTA, Role.RECEPCAO)


def _http(exc: service.PricingError) -> HTTPException:
    code = status.HTTP_404_NOT_FOUND if isinstance(exc, service.NotFound) else 409
    return HTTPException(status_code=code, detail=exc.message)


# ---------- Tabelas ----------


@router.get("/tabelas", response_model=list[TableOut])
def list_tables(
    _: CurrentUser = Depends(require_roles(*READ)), db: Session = Depends(get_tenant_db)
):
    return service.list_tables(db)


@router.post("/tabelas", response_model=TableOut, status_code=status.HTTP_201_CREATED)
def create_table(
    body: TableCreate,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    try:
        table, _ = service.create_table(db, user, **body.model_dump())
    except service.PricingError as exc:
        raise _http(exc) from None
    audit.record(
        db,
        user,
        "precificacao.tabela_criada",
        entity_type="price_table",
        entity_id=table.id,
        request=request,
    )
    db.commit()
    return table


@router.get("/tabelas/{table_id}", response_model=TableOut)
def get_table(
    table_id: uuid.UUID,
    _: CurrentUser = Depends(require_roles(*READ)),
    db: Session = Depends(get_tenant_db),
):
    try:
        return service.get_table(db, table_id)
    except service.PricingError as exc:
        raise _http(exc) from None


@router.patch("/tabelas/{table_id}", response_model=TableOut)
def update_table(
    table_id: uuid.UUID,
    body: TableUpdate,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    changes = body.model_dump(exclude_unset=True)
    try:
        table = service.update_table(db, service.get_table(db, table_id), changes)
    except service.PricingError as exc:
        raise _http(exc) from None
    audit.record(
        db,
        user,
        "precificacao.tabela_alterada",
        entity_type="price_table",
        entity_id=table.id,
        details={k: str(v) for k, v in changes.items()},
        request=request,
    )
    db.commit()
    return table


# ---------- Versões ----------


@router.get("/tabelas/{table_id}/versoes", response_model=list[VersionOut])
def list_versions(
    table_id: uuid.UUID,
    _: CurrentUser = Depends(require_roles(*READ)),
    db: Session = Depends(get_tenant_db),
):
    try:
        return service.list_versions(db, service.get_table(db, table_id))
    except service.PricingError as exc:
        raise _http(exc) from None


@router.post(
    "/tabelas/{table_id}/versoes", response_model=VersionOut, status_code=status.HTTP_201_CREATED
)
def create_draft(
    table_id: uuid.UUID,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    """Abre um rascunho a partir da última versão publicada."""
    try:
        draft = service.create_draft(db, user, service.get_table(db, table_id))
    except service.PricingError as exc:
        raise _http(exc) from None
    audit.record(
        db,
        user,
        "precificacao.versao_criada",
        entity_type="price_table_version",
        entity_id=draft.id,
        request=request,
    )
    db.commit()
    return draft


@router.patch("/tabelas/{table_id}/versoes/{version_id}", response_model=VersionOut)
def update_draft(
    table_id: uuid.UUID,
    version_id: uuid.UUID,
    body: VersionUpdate,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    changes = body.model_dump(exclude_unset=True)
    try:
        table = service.get_table(db, table_id)
        version = service.update_draft(
            db, table, service.get_version(db, table, version_id), changes
        )
    except service.PricingError as exc:
        raise _http(exc) from None
    audit.record(
        db,
        user,
        "precificacao.versao_alterada",
        entity_type="price_table_version",
        entity_id=version.id,
        details={k: str(v) for k, v in changes.items()},
        request=request,
    )
    db.commit()
    return version


@router.get("/tabelas/{table_id}/versoes/{version_id}/itens", response_model=list[ItemOut])
def list_items(
    table_id: uuid.UUID,
    version_id: uuid.UUID,
    _: CurrentUser = Depends(require_roles(*READ)),
    db: Session = Depends(get_tenant_db),
):
    try:
        table = service.get_table(db, table_id)
        return service.list_items(db, service.get_version(db, table, version_id))
    except service.PricingError as exc:
        raise _http(exc) from None


@router.put("/tabelas/{table_id}/versoes/{version_id}/itens", response_model=list[ItemOut])
def replace_items(
    table_id: uuid.UUID,
    version_id: uuid.UUID,
    body: ItemsReplace,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    """Substitui todos os itens do rascunho."""
    try:
        table = service.get_table(db, table_id)
        version = service.get_version(db, table, version_id)
        items = service.replace_items(db, user, version, [i.model_dump() for i in body.items])
    except service.PricingError as exc:
        raise _http(exc) from None
    audit.record(
        db,
        user,
        "precificacao.itens_substituidos",
        entity_type="price_table_version",
        entity_id=version.id,
        details={"quantidade": len(items)},
        request=request,
    )
    db.commit()
    return items


@router.post("/tabelas/{table_id}/versoes/{version_id}/publicar", response_model=VersionOut)
def publish(
    table_id: uuid.UUID,
    version_id: uuid.UUID,
    body: PublishIn,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    try:
        table = service.get_table(db, table_id)
        version = service.publish(
            db, user, table, service.get_version(db, table, version_id), body.valid_from
        )
    except service.PricingError as exc:
        raise _http(exc) from None
    audit.record(
        db,
        user,
        "precificacao.versao_publicada",
        entity_type="price_table_version",
        entity_id=version.id,
        details={"valid_from": str(version.valid_from)},
        request=request,
    )
    db.commit()
    return version


# ---------- Atribuições ----------


@router.get("/atribuicoes", response_model=list[AssignmentOut])
def list_assignments(
    _: CurrentUser = Depends(require_roles(*READ)), db: Session = Depends(get_tenant_db)
):
    return service.list_assignments(db)


@router.post("/atribuicoes", response_model=AssignmentOut, status_code=status.HTTP_201_CREATED)
def create_assignment(
    body: AssignmentCreate,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    try:
        assignment = service.create_assignment(db, user, **body.model_dump())
    except service.PricingError as exc:
        raise _http(exc) from None
    audit.record(
        db,
        user,
        "precificacao.atribuicao_criada",
        entity_type="price_assignment",
        entity_id=assignment.id,
        details=body.model_dump(mode="json"),
        request=request,
    )
    db.commit()
    return assignment


@router.delete("/atribuicoes/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_assignment(
    assignment_id: uuid.UUID,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    try:
        assignment = service.get_assignment(db, assignment_id)
    except service.PricingError as exc:
        raise _http(exc) from None
    details = {
        "table_id": str(assignment.table_id),
        "scope_type": assignment.scope_type.value,
        "scope_id": str(assignment.scope_id) if assignment.scope_id else None,
    }
    service.delete_assignment(db, assignment)
    audit.record(
        db,
        user,
        "precificacao.atribuicao_removida",
        entity_type="price_assignment",
        entity_id=assignment_id,
        details=details,
        request=request,
    )
    db.commit()


# ---------- Resolução ----------


def _not_found(exc: service.PriceNotFound) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": exc.message, "trace": exc.trace},
    )


@router.post("/resolver", response_model=ResolutionOut)
def resolve(
    body: ResolveIn,
    _: CurrentUser = Depends(require_roles(*READ)),
    db: Session = Depends(get_tenant_db),
):
    """Simula o preço de um procedimento no contexto informado (não grava nada)."""
    try:
        resolution = service.resolve(
            db,
            procedure_code=body.procedure_code,
            dentist_id=body.dentist_id,
            insurer_id=body.insurer_id,
            on=body.effective_on,
        )
    except service.PriceNotFound as exc:
        return _not_found(exc)
    return ResolutionOut(**vars(resolution))


@router.post("/snapshots", response_model=SnapshotOut, status_code=status.HTTP_201_CREATED)
def create_snapshot(
    body: ResolveIn,
    request: Request,
    user: CurrentUser = Depends(require_roles(*READ)),
    db: Session = Depends(get_tenant_db),
):
    """Resolve e congela o preço. É o registro que um orçamento referencia."""
    try:
        resolution = service.resolve(
            db,
            procedure_code=body.procedure_code,
            dentist_id=body.dentist_id,
            insurer_id=body.insurer_id,
            on=body.effective_on,
        )
    except service.PriceNotFound as exc:
        return _not_found(exc)
    try:
        snapshot = service.freeze(
            db, user, resolution, dentist_id=body.dentist_id, insurer_id=body.insurer_id
        )
    except service.PricingError as exc:
        raise _http(exc) from None
    audit.record(
        db,
        user,
        "precificacao.snapshot_criado",
        entity_type="price_snapshot",
        entity_id=snapshot.id,
        details={"procedure_code": snapshot.procedure_code, "price": str(snapshot.price)},
        request=request,
    )
    db.commit()
    return snapshot


@router.get("/snapshots/{snapshot_id}", response_model=SnapshotOut)
def get_snapshot(
    snapshot_id: uuid.UUID,
    _: CurrentUser = Depends(require_roles(*READ)),
    db: Session = Depends(get_tenant_db),
):
    try:
        return service.get_snapshot(db, snapshot_id)
    except service.PricingError as exc:
        raise _http(exc) from None
