"""Rotas de alertas por regra (inteligência clínica, fase 1).

- `/inteligencia/regras`: catálogo com a configuração da clínica; admin e gestor alteram.
- `/inteligencia/alertas`: alertas calculados na hora, filtrados pelo papel de quem pede
  (ex.: recepção não vê "canal sem retorno"; dentista e ASB não veem contas em atraso).
  A listagem traz nome e telefone do paciente, por isso é auditada (sem os nomes).
- `/inteligencia/alertas/resumo`: só contagens, sem dado de paciente (não auditado).
- Dispensar/voltar a mostrar: append-only e auditado.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core import audit
from app.core.context import CurrentUser
from app.core.roles import Role
from app.modules.identidade.deps import get_tenant_db, require_roles
from app.modules.inteligencia import regras, service
from app.modules.inteligencia.schemas import (
    AlertOut,
    DismissalOut,
    DismissIn,
    ParamOut,
    RestoreIn,
    RuleIn,
    RuleOut,
    SummaryOut,
)

router = APIRouter(prefix="/inteligencia", tags=["inteligência"])

ALL = tuple(Role)
MANAGE = (Role.ADMIN, Role.GESTOR)


def _http(exc: service.IntelligenceError) -> HTTPException:
    code = 404 if isinstance(exc, service.NotFound) else 422
    return HTTPException(status_code=code, detail=exc.message)


def _param_out(p: regras.Param) -> ParamOut:
    if isinstance(p, regras.IntParam):
        return ParamOut(
            name=p.name,
            label=p.label,
            type="inteiro",
            default=p.default,
            minimum=p.minimum,
            maximum=p.maximum,
        )
    return ParamOut(name=p.name, label=p.label, type="termos", default=list(p.default))


def _rule_out(config: service.RuleConfig) -> RuleOut:
    rule = config.rule
    return RuleOut(
        code=rule.code,
        title=rule.title,
        description=rule.description,
        category=rule.category,
        severity=rule.severity,
        roles=sorted(r.value for r in rule.roles),
        enabled=config.enabled,
        params=config.params,
        param_spec=[_param_out(p) for p in rule.params],
        customized=config.customized,
        updated_at=config.updated_at,
        updated_by=config.updated_by,
    )


@router.get("/regras", response_model=list[RuleOut])
def list_rules(
    _: CurrentUser = Depends(require_roles(*ALL)),
    db: Session = Depends(get_tenant_db),
):
    return [_rule_out(c) for c in service.rule_configs(db)]


@router.put("/regras/{code}", response_model=RuleOut)
def save_rule(
    code: str,
    body: RuleIn,
    request: Request,
    user: CurrentUser = Depends(require_roles(*MANAGE)),
    db: Session = Depends(get_tenant_db),
):
    try:
        changed = service.save_rule(db, user, code, body.enabled, body.params)
        config = service.get_config(db, code)
    except service.IntelligenceError as exc:
        raise _http(exc) from None
    audit.record(
        db,
        user,
        "inteligencia.regra_alterada",
        entity_type="regra_alerta",
        entity_id=code,
        details={"campos": changed, "ativa": body.enabled},
        request=request,
    )
    db.commit()
    return _rule_out(config)


@router.get("/alertas", response_model=list[AlertOut])
def list_alerts(
    request: Request,
    regra: list[str] | None = Query(None, description="Uma ou mais regras (padrão: todas)."),
    paciente_id: uuid.UUID | None = None,
    dentista_id: uuid.UUID | None = Query(
        None, description="Só os alertas em que o dentista é o responsável."
    ),
    incluir_dispensados: bool = False,
    user: CurrentUser = Depends(require_roles(*ALL)),
    db: Session = Depends(get_tenant_db),
):
    unknown = sorted(set(regra or ()) - set(regras.CODES))
    if unknown:
        raise HTTPException(status_code=422, detail="Regra de alerta inexistente.")
    alerts = service.compute_alerts(
        db,
        user.role,
        codes=set(regra) if regra else None,
        patient_id=paciente_id,
        dentist_id=dentista_id,
        include_dismissed=incluir_dispensados,
    )
    audit.record(
        db,
        user,
        "inteligencia.alertas_listados",
        entity_type="paciente" if paciente_id else None,
        entity_id=paciente_id,
        details={"resultados": len(alerts), "regras": sorted(regra) if regra else None},
        request=request,
    )
    db.commit()
    return [AlertOut(**a.__dict__) for a in alerts]


@router.get("/alertas/resumo", response_model=SummaryOut)
def alerts_summary(
    dentista_id: uuid.UUID | None = None,
    user: CurrentUser = Depends(require_roles(*ALL)),
    db: Session = Depends(get_tenant_db),
):
    counts = service.summary(db, user.role, dentista_id)
    return SummaryOut(total=sum(counts.values()), by_rule=counts)


@router.post("/alertas/dispensar", response_model=DismissalOut, status_code=status.HTTP_201_CREATED)
def dismiss(
    body: DismissIn,
    request: Request,
    user: CurrentUser = Depends(require_roles(*ALL)),
    db: Session = Depends(get_tenant_db),
):
    try:
        row = service.dismiss(db, user, body.code, body.key, body.until, body.reason)
    except service.IntelligenceError as exc:
        raise _http(exc) from None
    audit.record(
        db,
        user,
        "inteligencia.alerta_dispensado",
        entity_type="regra_alerta",
        entity_id=body.code,
        details={"chave": body.key, "ate": row.until.isoformat()},
        request=request,
    )
    db.commit()
    return DismissalOut(
        code=row.code, key=row.alert_key, until=row.until, created_at=row.created_at
    )


@router.post("/alertas/reativar", response_model=DismissalOut, status_code=status.HTTP_201_CREATED)
def restore(
    body: RestoreIn,
    request: Request,
    user: CurrentUser = Depends(require_roles(*ALL)),
    db: Session = Depends(get_tenant_db),
):
    try:
        row = service.restore(db, user, body.code, body.key)
    except service.IntelligenceError as exc:
        raise _http(exc) from None
    audit.record(
        db,
        user,
        "inteligencia.alerta_reativado",
        entity_type="regra_alerta",
        entity_id=body.code,
        details={"chave": body.key},
        request=request,
    )
    db.commit()
    return DismissalOut(
        code=row.code, key=row.alert_key, until=row.until, created_at=row.created_at
    )
