"""Leitura e validação de planilhas (sem banco)."""

import io
import zipfile
from decimal import Decimal

import pytest
from openpyxl import Workbook, load_workbook

from app.modules.precificacao import importacao as imp


def _xlsx(rows, title="Plan1", extra_sheet=None) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = title
    for r in rows:
        ws.append(r)
    if extra_sheet:
        wb.create_sheet(extra_sheet).append(["x"])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


# ---------- preço ----------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("150", "150.00"),
        ("150,5", "150.50"),
        ("1.234,56", "1234.56"),
        ("R$ 1.234,56", "1234.56"),
        ("R$\xa0980,00", "980.00"),
        ("1,234.56", "1234.56"),
        ("150.50", "150.50"),
        ("1.500", "1500.00"),  # milhar no uso brasileiro
        ("0.500", "0.50"),  # mas zero-ponto é decimal
        ("1.234.567,89", "1234567.89"),
        ("0", "0.00"),
    ],
)
def test_parse_price_accepts(text, expected):
    assert imp.parse_price(text) == Decimal(expected)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "vazio"),
        ("abc", "inválido"),
        ("-10", "negativo"),
        ("10,123", "duas casas"),
        ("99999999999,00", "limite"),
        ("NaN", "inválido"),
    ],
)
def test_parse_price_rejects(text, message):
    with pytest.raises(ValueError, match=message):
        imp.parse_price(text)


# ---------- leitura ----------


def test_csv_semicolon_windows1252():
    content = "Código;Procedimento;Valor\nPROF;Profilaxia;R$ 150,00\nREST;Restauração;1.200,00\n"
    parsed = imp.parse_file("tabela.csv", content.encode("cp1252"))
    assert parsed.headers == ["Código", "Procedimento", "Valor"]
    assert parsed.detected["codificacao"] == "windows-1252"
    assert parsed.detected["separador"] == "ponto e vírgula"
    assert parsed.rows[1] == {"linha": 3, "valores": ["REST", "Restauração", "1.200,00"]}


def test_csv_comma_utf8_bom_and_blank_lines():
    content = "﻿codigo,descricao,preco\n\nA,Item A,10.50\n,,\nB,Item B,20\n"
    parsed = imp.parse_file("t.csv", content.encode("utf-8"))
    assert parsed.headers == ["codigo", "descricao", "preco"]
    assert parsed.detected["codificacao"] == "utf-8"
    assert [r["linha"] for r in parsed.rows] == [3, 5]  # números da planilha original


def test_xlsx_numbers_are_not_misread_as_thousands():
    content = _xlsx([["Código", "Descrição", "Preço"], ["A", "Item", 1.234], ["B", "Item", 1500]])
    parsed = imp.parse_file("t.xlsx", content)
    assert parsed.rows[0]["valores"][2] == "1,234"
    result = imp.validate_rows(
        parsed.headers,
        parsed.rows,
        {"procedure_code": "Código", "description": "Descrição", "price": "Preço"},
    )
    # 1.234 (float do Excel) não vira 1234: vira erro de casas decimais.
    assert result.errors[0]["erro"] == "preço com mais de duas casas decimais"
    assert result.items[0]["price"] == Decimal("1500.00")


def test_xlsx_sheet_selection():
    content = _xlsx([["a"], ["1"]], title="Precos", extra_sheet="Outra")
    assert imp.parse_file("t.xlsx", content, sheet="Precos").detected["aba"] == "Precos"
    with pytest.raises(imp.SpreadsheetError, match="Abas do arquivo: Precos, Outra"):
        imp.parse_file("t.xlsx", content, sheet="Nao existe")


@pytest.mark.parametrize(
    ("filename", "content", "message"),
    [
        ("t.xls", b"x", "97-2003"),
        ("t.pdf", b"x", "Formato não suportado"),
        ("t.csv", b"", "vazio"),
        ("t.xlsx", b"nao e zip", "inválido ou corrompido"),
        ("t.csv", b"so;cabecalho\n", "sem linhas de dados"),
        ("t.csv", b"x" * (imp.MAX_FILE_BYTES + 1), "limite"),
    ],
)
def test_parse_file_rejects(filename, content, message):
    with pytest.raises(imp.SpreadsheetError, match=message):
        imp.parse_file(filename, content)


def test_too_many_rows():
    content = "c;d;p\n" + "".join(f"C{i};D;1\n" for i in range(imp.MAX_ROWS + 1))
    with pytest.raises(imp.SpreadsheetError, match="mais de 5000 linhas"):
        imp.parse_file("t.csv", content.encode())


def test_duplicate_and_empty_headers_get_unique_names():
    parsed = imp.parse_file("t.csv", b"Valor;;Valor\n1;2;3\n")
    assert parsed.headers == ["Valor", "Coluna 2", "Valor (2)"]


# ---------- mapeamento ----------


def test_suggest_mapping_by_synonyms():
    headers = ["Cód. TUSS", "Nome do procedimento", "Valor (R$)", "Especialidade", "Tempo"]
    assert imp.suggest_mapping(["Código", "Procedimento", "Preço", "Categoria"]) == {
        "procedure_code": "Código",
        "description": "Procedimento",
        "price": "Preço",
        "category": "Categoria",
    }
    assert imp.suggest_mapping(headers) == {
        "procedure_code": "Cód. TUSS",
        "description": "Nome do procedimento",
        "price": "Valor (R$)",
        "category": "Especialidade",
    }


@pytest.mark.parametrize(
    ("column_map", "extra", "message"),
    [
        ({"procedure_code": "A", "description": "B"}, [], "Preço"),
        ({"procedure_code": "A", "description": "B", "price": "X"}, [], "não existe"),
        ({"procedure_code": "A", "description": "A", "price": "C"}, [], "mais de um campo"),
        (
            {"procedure_code": "A", "description": "B", "price": "C", "foo": "A"},
            [],
            "desconhecidos",
        ),
        ({"procedure_code": "A", "description": "B", "price": "C"}, ["A"], "já está mapeada"),
    ],
)
def test_check_mapping_errors(column_map, extra, message):
    with pytest.raises(imp.MappingError, match=message):
        imp.check_mapping(["A", "B", "C"], column_map, extra)


# ---------- validação ----------

MAP = {"procedure_code": "Código", "description": "Descrição", "price": "Preço", "category": "Cat"}
HEADERS = ["Código", "Descrição", "Preço", "Cat", "Tempo"]


def _rows(*values):
    return [{"linha": i + 2, "valores": list(v)} for i, v in enumerate(values)]


def test_validate_rows_reports_each_error_with_line():
    rows = _rows(
        ("A", "Item A", "100", "", "30 min"),
        ("", "Sem código", "10", "", ""),
        ("C", "", "abc", "", ""),
        ("A", "Repetido", "5", "", ""),
        ("D", "Item D", "1.234,5", "Geral", ""),
    )
    result = imp.validate_rows(HEADERS, rows, MAP, ["Tempo"])
    assert [i["procedure_code"] for i in result.items] == ["A", "D"]
    assert result.items[0]["custom_fields"] == {"Tempo": "30 min"}
    assert result.items[0]["category"] is None
    assert result.items[1]["price"] == Decimal("1234.50")
    assert [(e["linha"], e["campo"]) for e in result.errors] == [
        (3, "Código"),
        (4, "Descrição"),
        (4, "Preço"),
        (5, "Código"),
    ]
    assert "linha 2" in result.errors[3]["erro"]


def test_validate_rows_length_limits():
    rows = _rows(("X" * 41, "ok", "1", "", ""))
    result = imp.validate_rows(HEADERS, rows, MAP)
    assert result.errors[0]["erro"] == "mais de 40 caracteres"


# ---------- diferenças ----------


def test_compute_diff():
    current = [
        {"procedure_code": "A", "description": "A", "category": None, "price": Decimal("10.00")},
        {"procedure_code": "B", "description": "B", "category": None, "price": Decimal("20.00")},
        {"procedure_code": "C", "description": "C", "category": None, "price": Decimal("30.00")},
    ]
    new = [
        {"procedure_code": "A", "description": "A", "category": None, "price": Decimal("10.00")},
        {
            "procedure_code": "B",
            "description": "B novo",
            "category": None,
            "price": Decimal("25.00"),
        },
        {"procedure_code": "D", "description": "D", "category": None, "price": Decimal("40.00")},
    ]
    diff = imp.compute_diff(current, new)
    assert (diff["novos"], diff["alterados"], diff["removidos"], diff["inalterados"]) == (
        1,
        1,
        1,
        1,
    )
    assert diff["detalhe"]["novos"] == ["D"]
    assert diff["detalhe"]["removidos"] == ["C"]
    changes = {
        c["campo"]: (c["antes"], c["depois"]) for c in diff["detalhe"]["alterados"][0]["mudancas"]
    }
    assert changes == {"description": ("B", "B novo"), "price": ("20.00", "25.00")}


# ---------- geração ----------


def test_build_xlsx_never_writes_formulas():
    content = imp.build_xlsx(
        ["Código", "Descrição", "Preço"],
        [['=HYPERLINK("http://x")', "+cmd", Decimal("10.50")], ["@SUM(A1)", None, Decimal("1")]],
    )
    ws = load_workbook(io.BytesIO(content)).active
    assert ws["A2"].value == '=HYPERLINK("http://x")'
    assert ws["A2"].data_type == "s"
    assert ws["B2"].data_type == "s"
    assert ws["A3"].data_type == "s"
    assert ws["C2"].value == 10.5 and ws["C2"].number_format == "#,##0.00"


def test_template_roundtrips_through_import():
    parsed = imp.parse_file("modelo.xlsx", imp.template_xlsx())
    mapping = imp.suggest_mapping(parsed.headers)
    result = imp.validate_rows(parsed.headers, parsed.rows, mapping)
    assert result.errors == []
    assert [i["price"] for i in result.items] == [
        Decimal("150.00"),
        Decimal("220.00"),
        Decimal("1200.00"),
    ]


def test_ambiguous_thousands_become_warnings():
    rows = _rows(
        ("A", "a", "1.500", "", ""), ("B", "b", "1.500,00", "", ""), ("C", "c", "0.500", "", "")
    )
    result = imp.validate_rows(HEADERS, rows, MAP)
    assert [i["price"] for i in result.items] == [
        Decimal("1500.00"),
        Decimal("1500.00"),
        Decimal("0.50"),
    ]
    assert [(w["linha"], w["valor"]) for w in result.warnings] == [(2, "1.500")]
    assert "confira" in result.warnings[0]["aviso"]


# ---------- limites e arquivos hostis (revisão) ----------


def test_export_header_from_extra_column_is_never_a_formula():
    content = imp.build_xlsx(["Código", "=1+1"], [["A", "x"]])
    ws = load_workbook(io.BytesIO(content)).active
    assert ws["B1"].value == "=1+1" and ws["B1"].data_type == "s"


def test_control_characters_are_removed():
    parsed = imp.parse_file("t.csv", "c;d;p\nA\x00B;Desc\x07rição;10\n".encode())
    assert parsed.rows[0]["valores"] == ["AB", "Descrição", "10"]
    # E a exportação não quebra com eles.
    imp.build_xlsx(["c"], [["x\x01y"]])


def test_clean_filename():
    assert imp.clean_filename("../../etc/tabela\x00.csv") == "tabela.csv"
    assert imp.clean_filename("") == "planilha"


def test_corrupted_xlsx_xml_is_a_clean_error():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types><broken")
        zf.writestr("xl/workbook.xml", "<<<")
    with pytest.raises(imp.SpreadsheetError, match="inválido ou corrompido"):
        imp.parse_file("t.xlsx", buf.getvalue())


def test_zip_bomb_is_rejected_before_parsing():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("xl/sharedStrings.xml", b" " * (imp.MAX_XLSX_UNCOMPRESSED + 1))
    assert len(buf.getvalue()) < imp.MAX_FILE_BYTES  # comprimido é pequeno
    with pytest.raises(imp.SpreadsheetError, match="grande demais"):
        imp.parse_file("t.xlsx", buf.getvalue())


def test_too_many_filled_columns():
    header = ";".join(f"c{i}" for i in range(imp.MAX_COLUMNS + 1))
    with pytest.raises(imp.SpreadsheetError, match="mais de 100 colunas"):
        imp.parse_file("t.csv", f"{header}\n".encode())


def test_trailing_empty_columns_are_ignored():
    parsed = imp.parse_file("t.csv", ("a;b" + ";" * 300 + "\n1;2\n").encode())
    assert parsed.headers == ["a", "b"]


def test_cell_too_long():
    with pytest.raises(imp.SpreadsheetError, match="linha 2 tem uma célula"):
        imp.parse_file("t.csv", ("c;d\nA;" + "x" * (imp.MAX_CELL_CHARS + 1) + "\n").encode())


def test_blank_rows_do_not_truncate_the_data():
    content = "c;d;p\n" + ";;\n" * 10000 + "A;Item;10\n"
    parsed = imp.parse_file("t.csv", content.encode())
    assert [r["valores"][0] for r in parsed.rows] == ["A"]


def test_fingerprint_changes_with_content():
    a = [{"procedure_code": "A", "description": "a", "price": Decimal("1.00")}]
    b = [{"procedure_code": "A", "description": "a", "price": Decimal("1.01")}]
    assert imp.items_fingerprint(a) == imp.items_fingerprint([dict(a[0], price="1")])
    assert imp.items_fingerprint(a) != imp.items_fingerprint(b)


def test_request_body_limit_rejects_before_auth():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        resp = client.post(
            "/precificacao/importacoes",
            files={"arquivo": ("t.csv", b"x" * (4 * 1024 * 1024), "text/csv")},
            data={"table_id": "00000000-0000-0000-0000-000000000000"},
        )
    assert resp.status_code == 413
