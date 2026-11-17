"""Painel: limites de dia e mês no fuso da clínica (sem banco)."""

from datetime import date, timedelta

from app.modules.painel.service import day_bounds, month_bounds, tz


def test_month_bounds():
    assert month_bounds(date(2026, 11, 17)) == (date(2026, 11, 1), date(2026, 12, 1))
    assert month_bounds(date(2026, 12, 5)) == (date(2026, 12, 1), date(2027, 1, 1))


def test_day_bounds_use_clinic_timezone():
    start, end = day_bounds(date(2026, 11, 17))
    local = start.astimezone(tz())
    assert (local.date(), local.hour, local.minute) == (date(2026, 11, 17), 0, 0)
    assert end.astimezone(tz()).date() == date(2026, 11, 18)
    assert timedelta(hours=23) <= end - start <= timedelta(hours=25)
