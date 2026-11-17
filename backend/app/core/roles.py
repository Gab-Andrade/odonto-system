from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    GESTOR = "gestor"
    DENTISTA = "dentista"
    ASB = "asb"  # auxiliar de saúde bucal
    RECEPCAO = "recepcao"
