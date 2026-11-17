"""Comandos administrativos.

    python -m app.cli criar-clinica --nome "Clínica Sorriso" --slug sorriso \
        --admin-email admin@sorriso.com.br --admin-nome "Ana Souza"

A senha é pedida no terminal (não fica no histórico do shell).
"""

import argparse
import getpass
import sys

from app import models  # noqa: F401
from app.core.db import get_sessionmaker
from app.modules.identidade.service import create_clinic_with_admin

MIN_PASSWORD = 10


def _criar_clinica(args: argparse.Namespace) -> int:
    password = getpass.getpass("Senha do admin: ")
    if len(password) < MIN_PASSWORD:
        print(f"A senha precisa ter pelo menos {MIN_PASSWORD} caracteres.", file=sys.stderr)
        return 1
    if password != getpass.getpass("Confirme a senha: "):
        print("As senhas não conferem.", file=sys.stderr)
        return 1

    with get_sessionmaker()() as session:
        clinic, user = create_clinic_with_admin(
            session,
            clinic_name=args.nome,
            clinic_slug=args.slug,
            admin_email=args.admin_email,
            admin_name=args.admin_nome,
            admin_password=password,
        )
        session.commit()
    print(f"Clínica criada: {clinic.name} ({clinic.id})")
    print(f"Admin: {user.email}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("criar-clinica", help="cria uma clínica e o usuário admin")
    p.add_argument("--nome", required=True)
    p.add_argument("--slug", required=True)
    p.add_argument("--admin-email", required=True)
    p.add_argument("--admin-nome", required=True)
    p.set_defaults(func=_criar_clinica)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
