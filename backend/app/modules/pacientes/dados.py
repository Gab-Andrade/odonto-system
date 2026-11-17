"""Funções puras de normalização e validação de dados pessoais (testáveis sem banco)."""

import re
import unicodedata
from datetime import date

ADULT_AGE = 18


def only_digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def normalize_text(value: str) -> str:
    """Minúsculas, sem acento e com espaços simples — base da busca por nome."""
    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(without_accents.lower().split())


def search_name(full_name: str, social_name: str | None) -> str:
    return normalize_text(f"{full_name} {social_name or ''}")


def is_valid_cpf(cpf: str) -> bool:
    """Confere os dois dígitos verificadores (recebe só dígitos)."""
    if len(cpf) != 11 or not cpf.isdigit() or cpf == cpf[0] * 11:
        return False
    for size in (9, 10):
        total = sum(int(d) * w for d, w in zip(cpf[:size], range(size + 1, 1, -1), strict=True))
        check = (total * 10) % 11 % 10
        if check != int(cpf[size]):
            return False
    return True


def normalize_cpf(value: str) -> str:
    """Devolve o CPF só com dígitos ou levanta ValueError."""
    cpf = only_digits(value)
    if not is_valid_cpf(cpf):
        raise ValueError("CPF inválido.")
    return cpf


def normalize_phone(value: str) -> str:
    """Telefone só com dígitos (8 a 15, cobre fixo, celular, DDD e DDI)."""
    phone = only_digits(value)
    if not 8 <= len(phone) <= 15:
        raise ValueError("Telefone deve ter de 8 a 15 dígitos.")
    return phone


def mask_cpf(cpf: str | None) -> str | None:
    """Mostra só o meio do CPF (***.456.789-**), para listagens."""
    if not cpf:
        return None
    return f"***.{cpf[3:6]}.{cpf[6:9]}-**"


def age_on(birth_date: date, on: date) -> int:
    return on.year - birth_date.year - ((on.month, on.day) < (birth_date.month, birth_date.day))


def is_minor(birth_date: date | None, on: date) -> bool:
    return birth_date is not None and age_on(birth_date, on) < ADULT_AGE


def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
