"""Comandos administrativos.

    python -m app.cli criar-clinica --nome "Clínica Sorriso" --slug sorriso \
        --admin-email admin@sorriso.com.br --admin-nome "Ana Souza"

A senha é pedida no terminal (não fica no histórico do shell).

    python -m app.cli demo --slug teste     # dados de demonstração (só desenvolvimento)
    python -m app.cli openapi --saida ../frontend/openapi.json
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


def _demo(args: argparse.Namespace) -> int:
    from app import demo

    try:
        report = demo.seed(args.slug)
    except demo.DemoError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Clínica: {report.clinic} (slug {args.slug})")
    for line in report.created:
        print(f"  + {line}")
    for line in report.kept:
        print(f"  = {line}")
    if not report.created:
        print("Nada novo: os dados de demonstração já existiam.")
    print(f"Usuários de demonstração (senha {demo.DEMO_PASSWORD}):")
    for email, name, role, _ in demo.TEAM:
        print(f"  {email:30} {role.value:9} {name}")
    return 0


def _openapi(args: argparse.Namespace) -> int:
    import json

    from app.main import app

    text = json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.saida:
        with open(args.saida, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)
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

    d = sub.add_parser("demo", help="cria dados de demonstração (idempotente; não em produção)")
    d.add_argument("--slug", default="teste", help="clínica existente, ou criada se não houver")
    d.set_defaults(func=_demo)

    o = sub.add_parser("openapi", help="exporta o esquema OpenAPI (para gerar o cliente do front)")
    o.add_argument("--saida", help="arquivo de saída (padrão: terminal)")
    o.set_defaults(func=_openapi)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
