import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.core import audit
from app.core.context import CurrentUser
from app.core.roles import Role
from app.modules.identidade.deps import get_tenant_db, require_roles
from app.modules.precificacao import formulas, importacao, service
from app.modules.precificacao.schemas import (
    AssignmentCreate,
    AssignmentOut,
    CalculationOut,
    FormulaOut,
    FormulaStep,
    FormulaTestIn,
    ImportApplyIn,
    ImportApplyOut,
    ImportJobOut,
    ImportJobSummary,
    ImportValidateIn,
    ItemCalcOut,
    ItemOut,
    ItemsReplace,
    ProfileCreate,
    ProfileOut,
    PublishIn,
    RecalcOut,
    ResolutionOut,
    ResolveIn,
    SheetIn,
    SheetItemOut,
    SheetOut,
    SnapshotOut,
    TableCreate,
    TableOut,
    TableUpdate,
    VariableIn,
    VariableOut,
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
        service.ensure_manual_items(table)
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
            db,
            user,
            table,
            service.get_version(db, table, version_id),
            body.valid_from,
            confirm_errors=body.confirmar_erros,
        )
    except service.CalcErrorsNotConfirmed as exc:
        # 409 com a lista dos procedimentos que ficariam de fora, para a tela confirmar.
        return JSONResponse(status_code=409, content={"detail": exc.message, "erros": exc.errors})
    except service.PricingError as exc:
        raise _http(exc) from None
    details: dict[str, object] = {"valid_from": str(version.valid_from)}
    if version.calc_errors:
        details["erros_confirmados"] = [e["procedimento"] for e in version.calc_errors]
    audit.record(
        db,
        user,
        "precificacao.versao_publicada",
        entity_type="price_table_version",
        entity_id=version.id,
        details=details,
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


# ---------- Importação de planilhas ----------

XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx(content: bytes, filename: str) -> Response:
    return Response(
        content=content,
        media_type=XLSX_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _job_out(job) -> ImportJobOut:
    out = ImportJobOut.model_validate(job)
    out.amostra = job.rows[:10]
    return out


@router.get("/importacoes/modelo", response_class=Response)
def download_template(_: CurrentUser = Depends(require_roles(*MANAGE))):
    """Planilha-modelo com as colunas esperadas e exemplos."""
    return _xlsx(importacao.template_xlsx(), "modelo-tabela-de-precos.xlsx")


@router.get("/importacoes", response_model=list[ImportJobSummary])
def list_imports(
    _: CurrentUser = Depends(require_roles(*MANAGE)), db: Session = Depends(get_tenant_db)
):
    return service.list_imports(db)


@router.post("/importacoes", response_model=ImportJobOut, status_code=status.HTTP_201_CREATED)
def create_import(
    request: Request,
    arquivo: UploadFile = File(..., description=".csv ou .xlsx, até 2 MB"),
    table_id: uuid.UUID = Form(...),
    aba: str | None = Form(None, description="Aba do Excel. Padrão: a primeira."),
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    """Lê a planilha e sugere o mapeamento de colunas. Não altera a tabela."""
    content = arquivo.file.read(importacao.MAX_FILE_BYTES + 1)
    try:
        job = service.create_import(
            db, user, table_id=table_id, filename=arquivo.filename or "", content=content, sheet=aba
        )
    except service.PricingError as exc:
        raise _http(exc) from None
    audit.record(
        db,
        user,
        "precificacao.importacao_criada",
        entity_type="import_job",
        entity_id=job.id,
        details={"arquivo": job.filename, "sha256": job.file_sha256, "linhas": len(job.rows)},
        request=request,
    )
    db.commit()
    return _job_out(job)


@router.get("/importacoes/{job_id}", response_model=ImportJobOut)
def get_import(
    job_id: uuid.UUID,
    _: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    try:
        return _job_out(service.get_import(db, job_id))
    except service.PricingError as exc:
        raise _http(exc) from None


@router.post("/importacoes/{job_id}/validar", response_model=ImportJobOut)
def validate_import(
    job_id: uuid.UUID,
    body: ImportValidateIn,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    """Aplica o mapeamento, valida linha a linha e mostra as diferenças. Não altera a tabela."""
    try:
        job = service.validate_import(
            db,
            service.get_import(db, job_id, lock=True),
            column_map=body.column_map,
            extra_columns=body.extra_columns,
            profile_id=body.profile_id,
        )
    except service.PricingError as exc:
        raise _http(exc) from None
    audit.record(
        db,
        user,
        "precificacao.importacao_validada",
        entity_type="import_job",
        entity_id=job.id,
        details={"erros": job.report["total_erros"], "validas": job.report["linhas_validas"]},
        request=request,
    )
    db.commit()
    return _job_out(job)


@router.post("/importacoes/{job_id}/aplicar", response_model=ImportApplyOut)
def apply_import(
    job_id: uuid.UUID,
    body: ImportApplyIn,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    """Grava as linhas válidas no rascunho da tabela. A publicação é um passo à parte."""
    try:
        job = service.get_import(db, job_id, lock=True)
        version = service.apply_import(db, user, job, ignore_errors=body.ignorar_erros)
    except service.PricingError as exc:
        raise _http(exc) from None
    audit.record(
        db,
        user,
        "precificacao.importacao_aplicada",
        entity_type="import_job",
        entity_id=job.id,
        details={"versao_id": str(version.id), "ignorou_erros": body.ignorar_erros},
        request=request,
    )
    db.commit()
    return ImportApplyOut(
        importacao=ImportJobSummary.model_validate(job), versao=VersionOut.model_validate(version)
    )


@router.get("/tabelas/{table_id}/versoes/{version_id}/exportar", response_class=Response)
def export_version(
    table_id: uuid.UUID,
    version_id: uuid.UUID,
    _: CurrentUser = Depends(require_roles(*READ)),
    db: Session = Depends(get_tenant_db),
):
    """Baixa a versão em Excel, no mesmo formato aceito pela importação."""
    try:
        table = service.get_table(db, table_id)
        version = service.get_version(db, table, version_id)
    except service.PricingError as exc:
        raise _http(exc) from None
    return _xlsx(service.export_version_xlsx(db, version), f"tabela-v{version.version}.xlsx")


# ---------- Perfis de importação ----------


@router.get("/perfis-importacao", response_model=list[ProfileOut])
def list_profiles(
    _: CurrentUser = Depends(require_roles(*MANAGE)), db: Session = Depends(get_tenant_db)
):
    return service.list_profiles(db)


@router.post("/perfis-importacao", response_model=ProfileOut, status_code=status.HTTP_201_CREATED)
def create_profile(
    body: ProfileCreate,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    try:
        profile = service.create_profile(db, user, **body.model_dump())
    except service.PricingError as exc:
        raise _http(exc) from None
    audit.record(
        db,
        user,
        "precificacao.perfil_criado",
        entity_type="import_profile",
        entity_id=profile.id,
        request=request,
    )
    db.commit()
    return profile


@router.delete("/perfis-importacao/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(
    profile_id: uuid.UUID,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    try:
        profile = service.get_profile(db, profile_id)
    except service.PricingError as exc:
        raise _http(exc) from None
    name = profile.name
    service.delete_profile(db, profile)
    audit.record(
        db,
        user,
        "precificacao.perfil_removido",
        entity_type="import_profile",
        entity_id=profile_id,
        details={"nome": name},
        request=request,
    )
    db.commit()


# ---------- Fórmulas e tabelas calculadas ----------
# Tudo aqui expõe custos e margens: só administrador e gestor.


@router.get("/formulas/padrao", response_model=FormulaOut)
def default_formula(_: CurrentUser = Depends(require_roles(*MANAGE))):
    """Fórmula padrão ("preço por dentro"), entradas do sistema e funções disponíveis."""
    return FormulaOut(
        formula=formulas.DEFAULT_FORMULA,
        entradas_do_sistema=formulas.SYSTEM_INPUTS,
        funcoes=formulas.FUNCTIONS,
        variaveis_sugeridas=formulas.DEFAULT_VARIABLES,
    )


@router.post("/formulas/testar", response_model=CalculationOut)
def try_formula(
    body: FormulaTestIn,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    """Calcula um procedimento com a fórmula informada, sem gravar nada."""
    try:
        calc = service.try_formula(
            db,
            procedure_code=body.procedure_code,
            steps=[s.model_dump() for s in body.formula] if body.formula else None,
            dentist_id=body.dentist_id,
            user=user,
        )
    except service.PricingError as exc:
        raise _http(exc) from None
    return CalculationOut(
        procedure_code=calc.procedure_code,
        description=calc.description,
        price=calc.price,
        trace=calc.trace,
    )


@router.get("/tabelas/{table_id}/versoes/{version_id}/formula", response_model=list[FormulaStep])
def get_formula(
    table_id: uuid.UUID,
    version_id: uuid.UUID,
    _: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    try:
        table = service.get_table(db, table_id)
        version = service.get_version(db, table, version_id)
    except service.PricingError as exc:
        raise _http(exc) from None
    if version.formula is None:
        raise HTTPException(status_code=404, detail="Esta tabela não é calculada.")
    return version.formula


@router.post("/tabelas/{table_id}/versoes/{version_id}/recalcular", response_model=RecalcOut)
def recalculate(
    table_id: uuid.UUID,
    version_id: uuid.UUID,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    """Gera os preços do rascunho a partir das fichas técnicas, custos e variáveis."""
    try:
        table = service.get_table(db, table_id)
        version = service.get_version(db, table, version_id)
        report = service.recalculate(db, user, table, version)
    except service.PricingError as exc:
        raise _http(exc) from None
    audit.record(
        db, user, "precificacao.versao_recalculada",
        entity_type="price_table_version", entity_id=version.id,
        details={"calculados": report["calculados"], "erros": len(report["erros"])},
        request=request,
    )  # fmt: skip
    db.commit()
    return RecalcOut(versao=VersionOut.model_validate(version), **report)


@router.get(
    "/tabelas/{table_id}/versoes/{version_id}/itens/{item_id}/calculo",
    response_model=ItemCalcOut,
)
def item_calculation(
    table_id: uuid.UUID,
    version_id: uuid.UUID,
    item_id: uuid.UUID,
    _: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    """Memória de cálculo de um item (custos, variáveis e passos da fórmula)."""
    try:
        table = service.get_table(db, table_id)
        version = service.get_version(db, table, version_id)
        return service.get_item(db, version, item_id)
    except service.PricingError as exc:
        raise _http(exc) from None


# ---------- Fichas técnicas ----------


def _sheet_out(db: Session, sheet, items=None) -> SheetOut:
    out = SheetOut.model_validate(sheet)
    if items is None:
        items = service.sheet_items(db, sheet)
    out.items = [SheetItemOut.model_validate(i) for i in items]
    return out


@router.get("/fichas", response_model=list[SheetOut])
def list_sheets(
    _: CurrentUser = Depends(require_roles(*MANAGE)), db: Session = Depends(get_tenant_db)
):
    grouped = service.items_by_sheet(db)  # uma consulta para os itens de todas as fichas
    return [_sheet_out(db, s, grouped.get(s.id, [])) for s in service.list_sheets(db)]


@router.post("/fichas", response_model=SheetOut, status_code=status.HTTP_201_CREATED)
def create_sheet(
    body: SheetIn,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    data = body.model_dump()
    try:
        sheet = service.save_sheet(db, user, None, **data)
    except service.PricingError as exc:
        raise _http(exc) from None
    audit.record(
        db, user, "precificacao.ficha_criada",
        entity_type="cost_sheet", entity_id=sheet.id,
        details={"procedimento": sheet.procedure_code}, request=request,
    )  # fmt: skip
    db.commit()
    return _sheet_out(db, sheet)


@router.get("/fichas/{sheet_id}", response_model=SheetOut)
def get_sheet(
    sheet_id: uuid.UUID,
    _: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    try:
        return _sheet_out(db, service.get_sheet(db, sheet_id))
    except service.PricingError as exc:
        raise _http(exc) from None


@router.put("/fichas/{sheet_id}", response_model=SheetOut)
def replace_sheet(
    sheet_id: uuid.UUID,
    body: SheetIn,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    """Substitui a ficha inteira (tempo e materiais)."""
    try:
        sheet = service.save_sheet(db, user, service.get_sheet(db, sheet_id), **body.model_dump())
    except service.PricingError as exc:
        raise _http(exc) from None
    audit.record(
        db, user, "precificacao.ficha_alterada",
        entity_type="cost_sheet", entity_id=sheet.id,
        details={"procedimento": sheet.procedure_code}, request=request,
    )  # fmt: skip
    db.commit()
    return _sheet_out(db, sheet)


@router.delete("/fichas/{sheet_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sheet(
    sheet_id: uuid.UUID,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    try:
        sheet = service.get_sheet(db, sheet_id)
    except service.PricingError as exc:
        raise _http(exc) from None
    code = sheet.procedure_code
    service.delete_sheet(db, sheet)
    audit.record(
        db, user, "precificacao.ficha_removida",
        entity_type="cost_sheet", entity_id=sheet_id, details={"procedimento": code},
        request=request,
    )  # fmt: skip
    db.commit()


# ---------- Variáveis ----------


@router.get("/variaveis", response_model=list[VariableOut])
def list_variables(
    _: CurrentUser = Depends(require_roles(*MANAGE)), db: Session = Depends(get_tenant_db)
):
    return service.list_variables(db)


@router.put("/variaveis", response_model=VariableOut)
def set_variable(
    body: VariableIn,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    """Cria ou atualiza o valor (padrão da clínica, ou do dentista se dentist_id vier)."""
    try:
        variable = service.set_variable(db, user, **body.model_dump())
    except service.PricingError as exc:
        raise _http(exc) from None
    audit.record(
        db, user, "precificacao.variavel_definida",
        entity_type="pricing_variable", entity_id=variable.id,
        details=body.model_dump(mode="json"), request=request,
    )  # fmt: skip
    db.commit()
    return variable


@router.delete("/variaveis/{variable_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_variable(
    variable_id: uuid.UUID,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    try:
        variable = service.get_variable(db, variable_id)
    except service.PricingError as exc:
        raise _http(exc) from None
    details = {"key": variable.key, "dentist_id": str(variable.dentist_id or "")}
    service.delete_variable(db, variable)
    audit.record(
        db, user, "precificacao.variavel_removida",
        entity_type="pricing_variable", entity_id=variable_id, details=details,
        request=request,
    )  # fmt: skip
    db.commit()
