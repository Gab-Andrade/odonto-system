"""Alertas por regra: calculados na hora, na sessão de tenant (RLS).

Cada regra é uma consulta SQL sobre os dados de outros módulos (agenda, plano de
tratamento, atendimentos, financeiro). O commit e a auditoria ficam com o router.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, exists, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.context import CurrentUser
from app.core.roles import Role
from app.modules.agenda.models import Appointment, AppointmentStatus, EntryKind
from app.modules.financeiro.models import Payment, Receivable
from app.modules.inteligencia import regras
from app.modules.inteligencia.models import AlertDismissal, AlertRuleSetting
from app.modules.odontograma.models import ToothStatus
from app.modules.pacientes.dados import escape_like
from app.modules.pacientes.models import Patient
from app.modules.prontuario.models import Encounter, EncounterStatus
from app.modules.tratamento.models import ItemStatus, PlanStatus, TreatmentPlan, TreatmentPlanItem


class IntelligenceError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFound(IntelligenceError):
    pass


class RuleViolation(IntelligenceError):
    pass


def tz() -> ZoneInfo:
    return ZoneInfo(get_settings().clinic_timezone)


def now() -> datetime:
    return datetime.now(UTC)


def today() -> date:
    return datetime.now(tz()).date()


def _instant(day: date) -> datetime:
    """Início do dia no fuso da clínica."""
    return datetime.combine(day, time.min, tzinfo=tz()).astimezone(UTC)


def _local_date(moment: datetime | None) -> date | None:
    return moment.astimezone(tz()).date() if moment else None


def _br(day: date | None) -> str:
    return day.strftime("%d/%m/%Y") if day else "-"


# ---------- configuração das regras ----------


@dataclass(frozen=True)
class RuleConfig:
    rule: regras.RuleDef
    enabled: bool
    params: dict[str, Any]
    customized: bool  # a clínica já salvou uma configuração
    updated_at: datetime | None
    updated_by: uuid.UUID | None


def rule_configs(db: Session) -> list[RuleConfig]:
    stored = {s.code: s for s in db.scalars(select(AlertRuleSetting))}
    configs = []
    for rule in regras.RULES:
        s = stored.get(rule.code)
        configs.append(
            RuleConfig(
                rule=rule,
                enabled=s.enabled if s else True,
                params=regras.effective_params(rule, s.params if s else None),
                customized=s is not None,
                updated_at=s.updated_at if s else None,
                updated_by=s.updated_by if s else None,
            )
        )
    return configs


def get_config(db: Session, code: str) -> RuleConfig:
    for config in rule_configs(db):
        if config.rule.code == code:
            return config
    raise NotFound("Regra de alerta inexistente.")


def save_rule(
    db: Session,
    user: CurrentUser,
    code: str,
    enabled: bool,
    params: dict[str, Any] | None,
) -> list[str]:
    """Liga/desliga a regra e grava os parâmetros (os omitidos voltam ao padrão).
    Devolve os nomes do que mudou, para a auditoria."""
    if code not in regras.BY_CODE:
        raise NotFound("Regra de alerta inexistente.")
    try:
        rule = regras.get_rule(code)
        clean = regras.validate_params(rule, params)
    except regras.RuleConfigError as exc:
        raise RuleViolation(str(exc)) from None
    setting = db.scalar(
        select(AlertRuleSetting).where(AlertRuleSetting.code == code).with_for_update()
    )
    before = get_config(db, code)
    changed = []
    if before.enabled != enabled:
        changed.append("ativa")
    changed += sorted(k for k in clean if before.params.get(k) != clean[k])
    if setting is None:
        setting = AlertRuleSetting(clinic_id=user.clinic_id, code=code)
        db.add(setting)
    setting.enabled = enabled
    setting.params = clean
    setting.updated_by = user.user_id
    db.flush()
    return changed


# ---------- alertas ----------


@dataclass(frozen=True)
class Alert:
    code: str
    title: str
    severity: str
    category: str
    key: str
    patient_id: uuid.UUID | None
    dentist_id: uuid.UUID | None
    since: date | None
    detail: str
    ref_type: str
    ref_id: uuid.UUID
    patient_name: str | None = None
    patient_phone: str | None = None
    dismissed_until: date | None = None


def _alert(rule: regras.RuleDef, **kwargs) -> Alert:
    return Alert(
        code=rule.code,
        title=rule.title,
        severity=rule.severity,
        category=rule.category,
        **kwargs,
    )


def _has_future_appointment(moment: datetime) -> ColumnElement[bool]:
    return exists().where(
        Appointment.patient_id == Patient.id,
        Appointment.kind == EntryKind.CONSULTA,
        Appointment.status.in_((AppointmentStatus.AGENDADO, AppointmentStatus.CONFIRMADO)),
        Appointment.starts_at >= moment,
    )


def _terms_match(terms: list[str]) -> ColumnElement[bool]:
    text = func.lower(
        TreatmentPlanItem.procedure_code + " " + func.coalesce(TreatmentPlanItem.description, "")
    )
    return or_(*(text.like(f"%{escape_like(t)}%", escape="\\") for t in terms))


def _profilaxia(db: Session, rule, params, day: date, moment: datetime) -> list[Alert]:
    last = (
        select(
            TreatmentPlanItem.patient_id,
            TreatmentPlanItem.performed_at,
            TreatmentPlanItem.performed_by,
            TreatmentPlanItem.id,
        )
        .where(TreatmentPlanItem.status == ItemStatus.REALIZADO, _terms_match(params["termos"]))
        .distinct(TreatmentPlanItem.patient_id)
        .order_by(TreatmentPlanItem.patient_id, TreatmentPlanItem.performed_at.desc())
        .subquery()
    )
    cutoff = _instant(regras.months_before(day, params["meses"]))
    rows = db.execute(
        select(last.c.patient_id, last.c.performed_at, last.c.performed_by, last.c.id)
        .join(Patient, Patient.id == last.c.patient_id)
        .where(
            last.c.performed_at < cutoff,
            Patient.active,
            ~_has_future_appointment(moment),
        )
    ).all()
    return [
        _alert(
            rule,
            key=str(patient_id),
            patient_id=patient_id,
            dentist_id=dentist_id,
            since=_local_date(performed_at),
            detail=f"Última profilaxia em {_br(_local_date(performed_at))}.",
            ref_type="item_plano",
            ref_id=item_id,
        )
        for patient_id, performed_at, dentist_id, item_id in rows
    ]


def _canal(db: Session, rule, params, day: date, moment: datetime) -> list[Alert]:
    endo_ids = select(ToothStatus.id).where(ToothStatus.code == "endodontia")
    later_encounter = exists().where(
        Encounter.patient_id == TreatmentPlanItem.patient_id,
        Encounter.started_at > TreatmentPlanItem.performed_at,
        or_(
            TreatmentPlanItem.encounter_id.is_(None),
            Encounter.id != TreatmentPlanItem.encounter_id,
        ),
    )
    rows = db.execute(
        select(
            TreatmentPlanItem.id,
            TreatmentPlanItem.patient_id,
            TreatmentPlanItem.performed_at,
            TreatmentPlanItem.performed_by,
            TreatmentPlanItem.tooth,
        )
        .join(Patient, Patient.id == TreatmentPlanItem.patient_id)
        .where(
            TreatmentPlanItem.status == ItemStatus.REALIZADO,
            or_(
                TreatmentPlanItem.done_status_id.in_(endo_ids),
                _terms_match(params["termos"]),
            ),
            TreatmentPlanItem.performed_at < moment - timedelta(days=params["dias"]),
            Patient.active,
            ~later_encounter,
            ~_has_future_appointment(moment),
        )
    ).all()
    alerts = []
    for item_id, patient_id, performed_at, dentist_id, tooth in rows:
        where = f"Dente {tooth}, r" if tooth else "R"
        alerts.append(
            _alert(
                rule,
                key=str(item_id),
                patient_id=patient_id,
                dentist_id=dentist_id,
                since=_local_date(performed_at),
                detail=f"{where}ealizado em {_br(_local_date(performed_at))}, sem retorno.",
                ref_type="item_plano",
                ref_id=item_id,
            )
        )
    return alerts


def _aprovado_sem_agenda(db: Session, rule, params, day: date, moment: datetime) -> list[Alert]:
    pending = (
        select(func.count())
        .where(
            TreatmentPlanItem.plan_id == TreatmentPlan.id,
            TreatmentPlanItem.status == ItemStatus.APROVADO,
        )
        .correlate(TreatmentPlan)
        .scalar_subquery()
    )
    rows = db.execute(
        select(
            TreatmentPlan.id,
            TreatmentPlan.patient_id,
            TreatmentPlan.dentist_id,
            TreatmentPlan.decided_at,
            TreatmentPlan.title,
            pending,
        )
        .join(Patient, Patient.id == TreatmentPlan.patient_id)
        .where(
            TreatmentPlan.status == PlanStatus.APROVADO,
            TreatmentPlan.decided_at < moment - timedelta(days=params["dias"]),
            pending > 0,
            Patient.active,
            ~_has_future_appointment(moment),
        )
    ).all()
    return [
        _alert(
            rule,
            key=str(plan_id),
            patient_id=patient_id,
            dentist_id=dentist_id,
            since=_local_date(decided_at),
            detail=(
                f"{title or 'Plano'}: {n} procedimento(s) por fazer, aprovado em "
                f"{_br(_local_date(decided_at))}."
            ),
            ref_type="plano",
            ref_id=plan_id,
        )
        for plan_id, patient_id, dentist_id, decided_at, title, n in rows
    ]


def _sem_resposta(db: Session, rule, params, day: date, moment: datetime) -> list[Alert]:
    rows = db.execute(
        select(
            TreatmentPlan.id,
            TreatmentPlan.patient_id,
            TreatmentPlan.dentist_id,
            TreatmentPlan.issued_at,
            TreatmentPlan.valid_until,
            TreatmentPlan.title,
        )
        .join(Patient, Patient.id == TreatmentPlan.patient_id)
        .where(
            TreatmentPlan.status == PlanStatus.EMITIDO,
            TreatmentPlan.issued_at < moment - timedelta(days=params["dias"]),
            TreatmentPlan.valid_until >= day,
            Patient.active,
        )
    ).all()
    return [
        _alert(
            rule,
            key=str(plan_id),
            patient_id=patient_id,
            dentist_id=dentist_id,
            since=_local_date(issued_at),
            detail=(
                f"{title or 'Orçamento'}: emitido em {_br(_local_date(issued_at))}, "
                f"válido até {_br(valid_until)}."
            ),
            ref_type="plano",
            ref_id=plan_id,
        )
        for plan_id, patient_id, dentist_id, issued_at, valid_until, title in rows
    ]


def _atendimento_aberto(db: Session, rule, params, day: date, moment: datetime) -> list[Alert]:
    rows = db.execute(
        select(Encounter.id, Encounter.patient_id, Encounter.dentist_id, Encounter.started_at)
        .where(
            Encounter.status == EncounterStatus.ABERTO,
            Encounter.started_at < moment - timedelta(days=params["dias"]),
        )
        .order_by(Encounter.started_at)
    ).all()
    return [
        _alert(
            rule,
            key=str(encounter_id),
            patient_id=patient_id,
            dentist_id=dentist_id,
            since=_local_date(started_at),
            detail=f"Aberto desde {_br(_local_date(started_at))}.",
            ref_type="atendimento",
            ref_id=encounter_id,
        )
        for encounter_id, patient_id, dentist_id, started_at in rows
    ]


def _faltas(db: Session, rule, params, day: date, moment: datetime) -> list[Alert]:
    rows = db.execute(
        select(Appointment.patient_id, func.count(), func.max(Appointment.starts_at))
        .join(Patient, Patient.id == Appointment.patient_id)
        .where(
            Appointment.kind == EntryKind.CONSULTA,
            Appointment.status == AppointmentStatus.FALTA,
            Appointment.starts_at >= moment - timedelta(days=params["dias"]),
            Patient.active,
        )
        .group_by(Appointment.patient_id)
        .having(func.count() >= params["faltas"])
    ).all()
    return [
        _alert(
            rule,
            key=str(patient_id),
            patient_id=patient_id,
            dentist_id=None,
            since=_local_date(last),
            detail=f"{n} falta(s) nos últimos {params['dias']} dias; a última em "
            f"{_br(_local_date(last))}.",
            ref_type="paciente",
            ref_id=patient_id,
        )
        for patient_id, n, last in rows
    ]


def _contas(db: Session, rule, params, day: date, moment: datetime) -> list[Alert]:
    # Sem filtro de paciente ativo, de propósito: a dívida continua mesmo com o cadastro
    # desativado (e só papéis do financeiro veem esta regra).
    paid = (
        select(Payment.receivable_id, func.sum(Payment.amount).label("paid"))
        .group_by(Payment.receivable_id)
        .subquery()
    )
    balance = Receivable.amount - func.coalesce(paid.c.paid, 0)
    rows = db.execute(
        select(
            Receivable.patient_id, func.count(), func.sum(balance), func.min(Receivable.due_date)
        )
        .outerjoin(paid, paid.c.receivable_id == Receivable.id)
        .where(
            Receivable.cancelled_at.is_(None),
            Receivable.due_date < day - timedelta(days=params["dias"]),
            balance > 0,
        )
        .group_by(Receivable.patient_id)
    ).all()
    alerts = []
    for patient_id, n, amount, oldest in rows:
        value = Decimal(amount).quantize(Decimal("0.01"))
        alerts.append(
            _alert(
                rule,
                key=str(patient_id),
                patient_id=patient_id,
                dentist_id=None,
                since=oldest,
                detail=f"{n} parcela(s) vencida(s), R$ {value} em aberto; a mais antiga "
                f"venceu em {_br(oldest)}.",
                ref_type="paciente",
                ref_id=patient_id,
            )
        )
    return alerts


Finder = Callable[[Session, regras.RuleDef, dict[str, Any], date, datetime], list[Alert]]

FINDERS: dict[str, Finder] = {
    "profilaxia_atrasada": _profilaxia,
    "canal_sem_retorno": _canal,
    "orcamento_aprovado_sem_agendamento": _aprovado_sem_agenda,
    "orcamento_sem_resposta": _sem_resposta,
    "atendimento_aberto": _atendimento_aberto,
    "faltas_repetidas": _faltas,
    "conta_em_atraso": _contas,
}
assert set(FINDERS) == set(regras.CODES)  # noqa: S101 - toda regra do catálogo tem consulta


def _active_dismissals(db: Session, day: date) -> dict[tuple[str, str], date]:
    latest = (
        select(AlertDismissal.code, AlertDismissal.alert_key, AlertDismissal.until)
        .distinct(AlertDismissal.code, AlertDismissal.alert_key)
        .order_by(AlertDismissal.code, AlertDismissal.alert_key, AlertDismissal.created_at.desc())
        .subquery()
    )
    rows = db.execute(select(latest).where(latest.c.until > day)).all()
    return {(code, key): until for code, key, until in rows}


def compute_alerts(
    db: Session,
    role: Role,
    *,
    codes: set[str] | None = None,
    patient_id: uuid.UUID | None = None,
    dentist_id: uuid.UUID | None = None,
    include_dismissed: bool = False,
) -> list[Alert]:
    """Alertas das regras ligadas que o papel pode ver, dos mais graves para os menos."""
    day, moment = today(), now()
    visible = {r.code for r in regras.visible_rules(role)}
    alerts: list[Alert] = []
    for config in rule_configs(db):
        code = config.rule.code
        if not config.enabled or code not in visible or (codes and code not in codes):
            continue
        alerts += FINDERS[code](db, config.rule, config.params, day, moment)

    if patient_id is not None:
        alerts = [a for a in alerts if a.patient_id == patient_id]
    if dentist_id is not None:
        alerts = [a for a in alerts if a.dentist_id == dentist_id]

    dismissed = _active_dismissals(db, day)
    result = []
    for a in alerts:
        until = dismissed.get((a.code, a.key))
        if until is not None and not include_dismissed:
            continue
        result.append(replace(a, dismissed_until=until))

    ids = {a.patient_id for a in result if a.patient_id}
    patients = {}
    if ids:
        patients = {p.id: p for p in db.scalars(select(Patient).where(Patient.id.in_(ids)))}
    final = []
    for a in result:
        p = patients.get(a.patient_id)
        if p is not None:
            a = replace(a, patient_name=p.social_name or p.full_name, patient_phone=p.phone)
        final.append(a)
    final.sort(
        key=lambda a: (
            regras.SEVERITY_ORDER[a.severity],
            a.since or date.max,
            a.patient_name or "",
        )
    )
    return final


def summary(db: Session, role: Role, dentist_id: uuid.UUID | None = None) -> dict[str, int]:
    """Quantidade de alertas ativos (não dispensados) por regra visível e ligada."""
    counts = {r.code: 0 for r in regras.visible_rules(role)}
    for a in compute_alerts(db, role, dentist_id=dentist_id):
        counts[a.code] += 1
    return counts


def _check_key(db: Session, role: Role, code: str, key: str) -> None:
    try:
        rule = regras.get_rule(code)
    except regras.RuleConfigError as exc:
        raise NotFound(str(exc)) from None
    if role not in rule.roles:
        raise NotFound("Regra de alerta inexistente.")
    try:
        uuid.UUID(key)
    except ValueError:
        raise RuleViolation("Chave de alerta inválida.") from None


def dismiss(
    db: Session,
    user: CurrentUser,
    code: str,
    key: str,
    until: date | None,
    reason: str | None,
) -> AlertDismissal:
    """Esconde um alerta até a data (padrão: 30 dias). Volta sozinho se a condição
    continuar depois disso."""
    _check_key(db, user.role, code, key)
    try:
        until = regras.check_snooze(until, today())
    except regras.RuleConfigError as exc:
        raise RuleViolation(str(exc)) from None
    current = {(a.code, a.key) for a in compute_alerts(db, user.role, codes={code})}
    if (code, key) not in current:
        raise NotFound("Alerta não encontrado (já resolvido ou dispensado).")
    row = AlertDismissal(
        clinic_id=user.clinic_id,
        code=code,
        alert_key=key,
        until=until,
        reason=reason,
        created_by=user.user_id,
    )
    db.add(row)
    db.flush()
    db.refresh(row)
    return row


def restore(db: Session, user: CurrentUser, code: str, key: str) -> AlertDismissal:
    """Volta a mostrar um alerta dispensado (novo registro com validade até hoje)."""
    _check_key(db, user.role, code, key)
    if (code, key) not in _active_dismissals(db, today()):
        raise NotFound("Este alerta não está dispensado.")
    row = AlertDismissal(
        clinic_id=user.clinic_id,
        code=code,
        alert_key=key,
        until=today(),
        reason="voltou a mostrar",
        created_by=user.user_id,
    )
    db.add(row)
    db.flush()
    db.refresh(row)
    return row
