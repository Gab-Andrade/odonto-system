"""Anamnese: estrutura do formulário, validação de respostas e alertas (sem banco)."""

import pytest
from pydantic import ValidationError

from app.modules.prontuario.anamnese import AnamnesisRuleError, compute_alerts, validate_answers
from app.modules.prontuario.schemas import DraftUpdate, Question

QUESTIONS = [
    {"id": "alergia", "text": "Tem alergia?", "type": "sim_nao", "required": True, "alert": True},
    {"id": "qual_alergia", "text": "Qual?", "type": "texto", "alert": True},
    {
        "id": "doencas",
        "text": "Doenças",
        "type": "multipla",
        "options": ["Diabetes", "Hipertensão", "Nenhuma"],
        "alert": True,
        "alert_options": ["Diabetes", "Hipertensão"],
    },
    {"id": "fuma", "text": "Fuma?", "type": "escolha_unica", "options": ["Sim", "Não"]},
    {"id": "peso", "text": "Peso (kg)", "type": "numero"},
    {"id": "ultima_consulta", "text": "Última consulta", "type": "data"},
]


# ---------- estrutura ----------


def test_valid_question_and_defaults():
    q = Question(id="pa", text=" Pressão alta? ", type="sim_nao")
    assert q.text == "Pressão alta?" and q.required is False and q.alert is False


@pytest.mark.parametrize(
    "fields",
    [
        {"id": "Com Espaço", "type": "texto"},
        {"id": "x", "type": "escolha_unica", "options": ["Só uma"]},
        {"id": "x", "type": "multipla", "options": ["A", "a"]},
        {"id": "x", "type": "texto", "options": ["A", "B"]},
        {"id": "x", "type": "escolha_unica", "options": ["A", "B"], "alert_options": ["A"]},
        {
            "id": "x",
            "type": "escolha_unica",
            "options": ["A", "B"],
            "alert": True,
            "alert_options": ["C"],
        },
        {"id": "x", "type": "sim_nao", "alert": True, "alert_options": ["A"]},
        {"id": "x", "type": "desconhecido"},
        {"id": "x", "type": "texto", "extra": 1},
    ],
)
def test_invalid_questions(fields):
    with pytest.raises(ValidationError):
        Question(text="Pergunta", **fields)


def test_duplicated_question_ids_rejected():
    q = {"id": "a", "text": "A", "type": "texto"}
    with pytest.raises(ValidationError):
        DraftUpdate(questions=[q, q])


# ---------- respostas ----------


def test_valid_answers_are_normalized():
    clean = validate_answers(
        QUESTIONS,
        {
            "alergia": True,
            "qual_alergia": "  dipirona ",
            "doencas": ["Nenhuma", "Diabetes", "Diabetes"],
            "fuma": "Não",
            "peso": 72.5,
            "ultima_consulta": "2026-01-31",
        },
    )
    assert clean["qual_alergia"] == "dipirona"
    assert clean["doencas"] == ["Diabetes", "Nenhuma"]  # ordem do formulário, sem repetir


def test_blank_answers_are_dropped():
    clean = validate_answers(QUESTIONS, {"alergia": False, "qual_alergia": "   ", "doencas": []})
    assert clean == {"alergia": False}


@pytest.mark.parametrize(
    "answers",
    [
        {},  # obrigatória faltando
        {"alergia": None},
        {"alergia": "sim"},
        {"alergia": 1},
        {"alergia": True, "fuma": "Talvez"},
        {"alergia": True, "doencas": "Diabetes"},
        {"alergia": True, "doencas": ["Asma"]},
        {"alergia": True, "peso": True},
        {"alergia": True, "peso": "70"},
        {"alergia": True, "peso": float("inf")},
        {"alergia": True, "ultima_consulta": "2026-02-30"},
        {"alergia": True, "ultima_consulta": "31/01/2026"},
        {"alergia": True, "qual_alergia": "x" * 2001},
        {"alergia": True, "inexistente": "x"},
    ],
)
def test_invalid_answers(answers):
    with pytest.raises(AnamnesisRuleError):
        validate_answers(QUESTIONS, answers)


def test_alerts():
    answers = validate_answers(
        QUESTIONS,
        {"alergia": True, "qual_alergia": "Dipirona", "doencas": ["Diabetes", "Nenhuma"]},
    )
    alerts = compute_alerts(QUESTIONS, answers)
    assert alerts == [
        {"question_id": "alergia", "text": "Tem alergia?", "answer": True},
        {"question_id": "qual_alergia", "text": "Qual?", "answer": "Dipirona"},
        {"question_id": "doencas", "text": "Doenças", "answer": ["Diabetes"]},
    ]


def test_no_alerts_for_negative_answers():
    answers = validate_answers(QUESTIONS, {"alergia": False, "doencas": ["Nenhuma"]})
    assert compute_alerts(QUESTIONS, answers) == []
