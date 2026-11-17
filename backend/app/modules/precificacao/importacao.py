"""Leitura, mapeamento e validação de planilhas de preço (CSV e Excel .xlsx).

Funções puras, sem banco: o service orquestra e grava.

Fluxo: parse_file → suggest_mapping → validate_rows → compute_diff.
Cada linha guarda o número dela na planilha original, para que os erros apontem
exatamente onde corrigir.
"""

import csv
import hashlib
import io
import json
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import PurePath
from typing import Any

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_ROWS = 5000
MAX_PRICE = Decimal("9999999999.99")
CENTS = Decimal("0.01")
MAX_EXTRA_VALUE = 500
MAX_COLUMNS = 100
MAX_CELL_CHARS = 1000
# Um .xlsx é um zip: o limite de 2 MB vale para o arquivo comprimido. Estes limites
# barram "bombas de compressão" antes de o openpyxl descompactar qualquer coisa.
MAX_XLSX_UNCOMPRESSED = 50 * 1024 * 1024
MAX_XLSX_ENTRIES = 500
REPORT_DETAIL_LIMIT = 200  # linhas de erro/diff detalhadas no relatório

FIELDS = ("procedure_code", "description", "price", "category")
REQUIRED_FIELDS = ("procedure_code", "description", "price")
FIELD_LABELS = {
    "procedure_code": "Código",
    "description": "Descrição",
    "price": "Preço",
    "category": "Categoria",
}
FIELD_MAX_LEN = {"procedure_code": 40, "description": 300, "category": 100}

# Cabeçalhos reconhecidos automaticamente (já normalizados: minúsculas, sem acento).
SYNONYMS = {
    "procedure_code": (
        "codigo",
        "cod",
        "code",
        "tuss",
        "codigo do procedimento",
        "cod procedimento",
    ),
    "description": ("descricao", "procedimento", "nome", "nome do procedimento", "servico"),
    "price": ("preco", "valor", "price", "valor r", "preco r", "valor unitario", "honorario"),
    "category": ("categoria", "especialidade", "grupo", "area"),
}


class SpreadsheetError(Exception):
    """Arquivo ilegível ou fora dos limites."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class MappingError(SpreadsheetError):
    """Mapeamento de colunas inválido."""


# ---------- Leitura ----------

# Caracteres de controle: invisíveis, inúteis numa tabela de preços e inválidos no .xlsx.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_text(text: str) -> str:
    return _CONTROL_CHARS.sub("", text).strip()


def clean_filename(filename: str | None) -> str:
    name = clean_text(PurePath(filename or "").name)
    return name[:255] or "planilha"


@dataclass
class ParsedSheet:
    headers: list[str]
    rows: list[dict[str, Any]]  # {"linha": int, "valores": list[str]}
    detected: dict[str, Any] = field(default_factory=dict)


def file_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def parse_file(filename: str, content: bytes, sheet: str | None = None) -> ParsedSheet:
    if len(content) > MAX_FILE_BYTES:
        raise SpreadsheetError(
            f"Arquivo maior que o limite de {MAX_FILE_BYTES // (1024 * 1024)} MB."
        )
    if not content:
        raise SpreadsheetError("Arquivo vazio.")

    ext = PurePath(filename or "").suffix.lower()
    if ext in (".csv", ".txt"):
        raw_rows, detected = _read_csv(content)
    elif ext == ".xlsx":
        raw_rows, detected = _read_xlsx(content, sheet)
    elif ext == ".xls":
        raise SpreadsheetError(
            "Formato .xls (Excel 97-2003) ainda não é aceito. No Excel, use "
            "'Salvar como' e escolha .xlsx ou .csv."
        )
    else:
        raise SpreadsheetError("Formato não suportado. Envie um arquivo .csv ou .xlsx.")

    headers, rows = _split_header(raw_rows)
    detected["linhas"] = len(rows)
    return ParsedSheet(headers=headers, rows=rows, detected=detected)


def _decode(content: bytes) -> tuple[str, str]:
    try:
        return content.decode("utf-8-sig"), "utf-8"
    except UnicodeDecodeError:
        pass
    try:
        # Excel em português costuma salvar CSV em Windows-1252.
        return content.decode("cp1252"), "windows-1252"
    except UnicodeDecodeError:
        return content.decode("latin-1"), "latin-1"


def _read_csv(content: bytes) -> tuple[list[tuple[int, list[str]]], dict[str, Any]]:
    text, encoding = _decode(content)
    sample = text[:20000]
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=";,\t|").delimiter
    except csv.Error:
        delimiter = ";" if sample.count(";") >= sample.count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    collector = _RowCollector()
    try:
        for row in reader:
            collector.add(reader.line_num, [clean_text(c) for c in row])
    except csv.Error:
        raise SpreadsheetError(f"CSV malformado perto da linha {reader.line_num}.") from None
    rows = collector.rows
    names = {";": "ponto e vírgula", ",": "vírgula", "\t": "tabulação", "|": "barra vertical"}
    return rows, {"formato": "csv", "codificacao": encoding, "separador": names[delimiter]}


def _read_xlsx(
    content: bytes, sheet: str | None
) -> tuple[list[tuple[int, list[str]]], dict[str, Any]]:
    from openpyxl import load_workbook  # import tardio: só quem importa xlsx paga o custo

    _check_zip(content)
    invalid = SpreadsheetError("Arquivo .xlsx inválido ou corrompido.")
    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception:  # o parser levanta dezenas de tipos de erro; nenhum deve virar 500
        raise invalid from None
    try:
        names = wb.sheetnames
        if sheet is not None:
            if sheet not in names:
                raise SpreadsheetError(
                    f"Aba '{sheet}' não encontrada. Abas do arquivo: {', '.join(names)}."
                )
            ws = wb[sheet]
        else:
            ws = wb.worksheets[0]
        collector = _RowCollector()
        for idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
            collector.add(idx, [_cell_to_str(v) for v in row])
        return collector.rows, {"formato": "xlsx", "aba": ws.title, "abas": names}
    except SpreadsheetError:
        raise
    except Exception:
        raise invalid from None
    finally:
        wb.close()


def _check_zip(content: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            infos = zf.infolist()
    except zipfile.BadZipFile:
        raise SpreadsheetError("Arquivo .xlsx inválido ou corrompido.") from None
    if len(infos) > MAX_XLSX_ENTRIES:
        raise SpreadsheetError("Arquivo .xlsx com estrutura fora do padrão.")
    # file_size é o tamanho declarado; o zipfile não descompacta além dele.
    if sum(i.file_size for i in infos) > MAX_XLSX_UNCOMPRESSED:
        raise SpreadsheetError(
            "O conteúdo do .xlsx é grande demais. Remova abas e formatações extras, "
            "ou envie como .csv."
        )


class _RowCollector:
    """Guarda só as linhas preenchidas, com o número original, aplicando os limites."""

    def __init__(self) -> None:
        self.rows: list[tuple[int, list[str]]] = []

    def add(self, line: int, cells: list[str]) -> None:
        if len(cells) > MAX_COLUMNS:
            if any(cells[MAX_COLUMNS:]):
                raise SpreadsheetError(
                    f"A linha {line} tem mais de {MAX_COLUMNS} colunas preenchidas."
                )
            cells = cells[:MAX_COLUMNS]  # colunas vazias à direita (formatação) são ignoradas
        if not any(cells):
            return
        if any(len(c) > MAX_CELL_CHARS for c in cells):
            raise SpreadsheetError(
                f"A linha {line} tem uma célula com mais de {MAX_CELL_CHARS} caracteres."
            )
        self.rows.append((line, cells))
        if len(self.rows) > MAX_ROWS + 1:  # +1: cabeçalho
            raise SpreadsheetError(f"A planilha tem mais de {MAX_ROWS} linhas de dados.")


def _cell_to_str(value: Any) -> str:
    """Converte a célula em texto. Números saem com vírgula decimal e sem separador
    de milhar, para que o parser de preço (formato brasileiro) não os confunda."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "sim" if value else "não"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return format(Decimal(repr(value)), "f").replace(".", ",")
    if isinstance(value, Decimal):
        return format(value, "f").replace(".", ",")
    if isinstance(value, datetime | date):
        return value.isoformat()
    return clean_text(str(value))


def _split_header(
    raw_rows: list[tuple[int, list[str]]],
) -> tuple[list[str], list[dict[str, Any]]]:
    non_empty = [(n, r) for n, r in raw_rows if any(c for c in r)]
    if not non_empty:
        raise SpreadsheetError("A planilha está vazia.")

    _, header_row = non_empty[0]
    # Ignora colunas vazias no fim do cabeçalho (comum em planilhas formatadas).
    while header_row and not header_row[-1]:
        header_row = header_row[:-1]
    if not header_row:
        raise SpreadsheetError("A primeira linha preenchida (cabeçalho) está vazia.")

    headers: list[str] = []
    seen: dict[str, int] = {}
    for i, name in enumerate(header_row, start=1):
        base = name or f"Coluna {i}"
        seen[base] = seen.get(base, 0) + 1
        headers.append(base if seen[base] == 1 else f"{base} ({seen[base]})")

    width = len(headers)
    rows = [
        {"linha": n, "valores": (r + [""] * width)[:width]}
        for n, r in non_empty[1:]
        if any(c for c in r[:width])
    ]
    if not rows:
        raise SpreadsheetError("A planilha só tem cabeçalho, sem linhas de dados.")
    if len(rows) > MAX_ROWS:
        raise SpreadsheetError(f"A planilha tem mais de {MAX_ROWS} linhas de dados.")
    return headers, rows


# ---------- Mapeamento ----------


def normalize_header(name: str) -> str:
    text = unicodedata.normalize("NFKD", name)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def suggest_mapping(headers: list[str]) -> dict[str, str | None]:
    """Sugere qual coluna corresponde a cada campo, pelo nome do cabeçalho."""
    normalized = [(h, normalize_header(h)) for h in headers]
    used: set[str] = set()
    mapping: dict[str, str | None] = {}
    for fld in FIELDS:
        choice = None
        for exact in (True, False):
            for header, norm in normalized:
                if header in used:
                    continue
                syns = SYNONYMS[fld]
                if (exact and norm in syns) or (
                    not exact and any(norm.startswith(s + " ") for s in syns)
                ):
                    choice = header
                    break
            if choice:
                break
        mapping[fld] = choice
        if choice:
            used.add(choice)
    return mapping


def check_mapping(
    headers: list[str], column_map: dict[str, str | None], extra_columns: list[str]
) -> dict[str, str]:
    unknown_fields = set(column_map) - set(FIELDS)
    if unknown_fields:
        raise MappingError(
            f"Campos desconhecidos no mapeamento: {', '.join(sorted(unknown_fields))}."
        )
    mapping = {k: v for k, v in column_map.items() if v}
    missing = [FIELD_LABELS[f] for f in REQUIRED_FIELDS if f not in mapping]
    if missing:
        raise MappingError(f"Indique a coluna de: {', '.join(missing)}.")
    for fld, header in mapping.items():
        if header not in headers:
            raise MappingError(f"A coluna '{header}' ({FIELD_LABELS[fld]}) não existe na planilha.")
    used = list(mapping.values())
    if len(used) != len(set(used)):
        raise MappingError("A mesma coluna foi usada para mais de um campo.")
    for header in extra_columns:
        if header not in headers:
            raise MappingError(f"A coluna extra '{header}' não existe na planilha.")
        if header in used:
            raise MappingError(f"A coluna '{header}' já está mapeada para um campo.")
    return mapping


# ---------- Validação ----------


def parse_price(text: str) -> Decimal:
    """Lê preço em formato brasileiro ou internacional.

    Aceita: "150", "150,5", "1.234,56", "R$ 1.234,56", "1,234.56", "150.50".
    Um único ponto seguido de exatamente 3 dígitos é lido como milhar ("1.500" = 1500),
    que é o uso brasileiro; "0.500" continua sendo decimal.
    """
    s = text.strip().replace("R$", "").replace("\xa0", "").replace(" ", "")
    if not s:
        raise ValueError("preço vazio")
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")  # 1.234,56
        else:
            s = s.replace(",", "")  # 1,234.56
    elif "," in s:
        s = s.replace(",", "") if s.count(",") > 1 else s.replace(",", ".")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    elif "." in s:
        whole, frac = s.split(".")
        if len(frac) == 3 and whole.lstrip("-") not in ("", "0"):
            s = whole + frac
    try:
        value = Decimal(s)
    except InvalidOperation:
        raise ValueError(f"preço inválido: '{text}'") from None
    if not value.is_finite():
        raise ValueError(f"preço inválido: '{text}'")
    if value < 0:
        raise ValueError("preço negativo")
    if value != value.quantize(CENTS):
        raise ValueError("preço com mais de duas casas decimais")
    if value > MAX_PRICE:
        raise ValueError("preço acima do limite permitido")
    return value.quantize(CENTS)


@dataclass
class ValidationResult:
    items: list[dict[str, Any]]
    errors: list[dict[str, Any]]
    warnings: list[dict[str, Any]] = field(default_factory=list)


_AMBIGUOUS_THOUSANDS = re.compile(r"^\s*(R\$)?\s*-?[1-9]\d{0,2}\.\d{3}\s*$")


def is_ambiguous_price(text: str) -> bool:
    """'1.500' é lido como mil e quinhentos, mas num sistema com ponto decimal seria 1,5."""
    return bool(_AMBIGUOUS_THOUSANDS.match(text))


def validate_rows(
    headers: list[str],
    rows: list[dict[str, Any]],
    column_map: dict[str, str | None],
    extra_columns: list[str] | None = None,
) -> ValidationResult:
    extra_columns = extra_columns or []
    mapping = check_mapping(headers, column_map, extra_columns)
    index = {h: i for i, h in enumerate(headers)}

    items: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    first_line_of: dict[str, int] = {}

    def err(line: int, fld: str, value: str, message: str) -> None:
        errors.append({"linha": line, "campo": fld, "valor": value[:100], "erro": message})

    for row in rows:
        line, values = row["linha"], row["valores"]
        raw = {fld: values[index[h]].strip() for fld, h in mapping.items()}
        ok = True

        for fld in ("procedure_code", "description", "category"):
            value = raw.get(fld, "")
            if fld in REQUIRED_FIELDS and not value:
                err(line, FIELD_LABELS[fld], value, "campo obrigatório vazio")
                ok = False
            elif len(value) > FIELD_MAX_LEN[fld]:
                err(line, FIELD_LABELS[fld], value, f"mais de {FIELD_MAX_LEN[fld]} caracteres")
                ok = False

        try:
            price = parse_price(raw["price"])
            if is_ambiguous_price(raw["price"]):
                warnings.append(
                    {
                        "linha": line,
                        "campo": FIELD_LABELS["price"],
                        "valor": raw["price"],
                        "aviso": f"lido como {price} (ponto como separador de milhar); confira",
                    }
                )
        except ValueError as exc:
            err(line, FIELD_LABELS["price"], raw["price"], str(exc))
            ok = False

        code = raw.get("procedure_code", "")
        if code:
            if code in first_line_of:
                err(
                    line,
                    FIELD_LABELS["procedure_code"],
                    code,
                    f"código repetido (já aparece na linha {first_line_of[code]})",
                )
                ok = False
            else:
                first_line_of[code] = line

        custom: dict[str, str] = {}
        for header in extra_columns:
            value = values[index[header]].strip()
            if len(value) > MAX_EXTRA_VALUE:
                err(line, header, value, f"mais de {MAX_EXTRA_VALUE} caracteres")
                ok = False
            elif value:
                custom[header] = value

        if ok:
            items.append(
                {
                    "procedure_code": code,
                    "description": raw["description"],
                    "category": raw.get("category") or None,
                    "price": price,
                    "custom_fields": custom or None,
                }
            )
    return ValidationResult(items=items, errors=errors, warnings=warnings)


# ---------- Diferenças ----------


def compute_diff(current: list[dict[str, Any]], new: list[dict[str, Any]]) -> dict[str, Any]:
    """Compara os itens atuais com os importados, por código de procedimento."""
    before = {i["procedure_code"]: i for i in current}
    after = {i["procedure_code"]: i for i in new}

    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed: list[dict[str, Any]] = []
    unchanged = 0
    for code in sorted(set(after) & set(before)):
        changes = []
        for fld in ("description", "category", "price", "custom_fields"):
            old, new_value = before[code].get(fld), after[code].get(fld)
            if fld == "price":
                old, new_value = Decimal(old), Decimal(new_value)
            if old != new_value:
                changes.append(
                    {"campo": fld, "antes": _jsonable(old), "depois": _jsonable(new_value)}
                )
        if changes:
            changed.append({"codigo": code, "mudancas": changes})
        else:
            unchanged += 1

    return {
        "novos": len(added),
        "alterados": len(changed),
        "removidos": len(removed),
        "inalterados": unchanged,
        "detalhe": {
            "novos": added[:REPORT_DETAIL_LIMIT],
            "alterados": changed[:REPORT_DETAIL_LIMIT],
            "removidos": removed[:REPORT_DETAIL_LIMIT],
        },
    }


def items_fingerprint(items: list[dict[str, Any]]) -> str:
    """Hash do conteúdo de uma versão, para detectar edições entre validar e aplicar."""
    canonical = sorted(
        (
            i["procedure_code"],
            i["description"],
            i.get("category") or "",
            str(Decimal(i["price"]).quantize(CENTS)),
            json.dumps(i.get("custom_fields") or {}, sort_keys=True, ensure_ascii=False),
        )
        for i in items
    )
    return hashlib.sha256(json.dumps(canonical, ensure_ascii=False).encode()).hexdigest()


def _jsonable(value: Any) -> Any:
    return str(value) if isinstance(value, Decimal) else value


# ---------- Geração de planilhas ----------


def build_xlsx(headers: list[str], rows: list[list[Any]]) -> bytes:
    """Gera .xlsx. Textos nunca viram fórmula: um código ou descrição começando com '='
    vindo de uma importação não pode executar nada no Excel de quem baixar."""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = "Tabela de preços"
    for c, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=c)
        cell.value = clean_text(str(header))
        cell.data_type = "s"  # cabeçalhos extras vêm de planilhas enviadas: nunca fórmula
        cell.font = Font(bold=True)
    for row in rows:
        ws.append([None] * len(row))
        r = ws.max_row
        for c, value in enumerate(row, start=1):
            cell = ws.cell(row=r, column=c)
            if isinstance(value, Decimal):
                cell.value = value
                cell.number_format = "#,##0.00"
            elif value is None:
                continue
            else:
                cell.value = clean_text(str(value))
                cell.data_type = "s"  # força texto, mesmo começando com '='
    for col, header in enumerate(headers, start=1):
        width = max([len(str(header))] + [len(str(r[col - 1] or "")) for r in rows[:500]])
        ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = min(width + 2, 60)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def template_xlsx() -> bytes:
    return build_xlsx(
        ["Código", "Descrição", "Categoria", "Preço"],
        [
            ["PROFILAXIA", "Profilaxia e polimento", "Prevenção", Decimal("150.00")],
            ["RESTAURACAO-1F", "Restauração em resina - 1 face", "Dentística", Decimal("220.00")],
            ["CANAL-MOLAR", "Tratamento de canal - molar", "Endodontia", Decimal("1200.00")],
        ],
    )
