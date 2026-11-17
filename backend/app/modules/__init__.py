"""Módulos de domínio.

Convenção de cada módulo:
    models.py   - tabelas (SQLAlchemy)
    schemas.py  - entrada/saída da API (Pydantic)
    service.py  - regras de negócio (sem dependência de HTTP)
    router.py   - endpoints FastAPI

Um módulo só fala com outro pelo service.py dele, nunca direto pelos models.
"""
