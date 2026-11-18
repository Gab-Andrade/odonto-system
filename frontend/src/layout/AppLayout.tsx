import { useState } from "react";
import { Navigate, NavLink, Outlet, useLocation } from "react-router-dom";

import {
  AGENDA,
  CLINICOS,
  GESTAO,
  NOME_PAPEL,
  sessaoValida,
  temPapel,
  useSessao,
  type Papel,
} from "../auth/sessao";
import { useQueryClient } from "@tanstack/react-query";
import { type Tema, useTema } from "../lib/tema";

interface ItemMenu {
  para: string;
  rotulo: string;
  icone: string;
  papeis: Papel[];
}

const TEMAS: { id: Tema; rotulo: string; icone: string; dica: string }[] = [
  { id: "claro", rotulo: "Claro", icone: "☀", dica: "Tema claro" },
  { id: "sistema", rotulo: "Auto", icone: "◐", dica: "Segue o tema do aparelho" },
  { id: "escuro", rotulo: "Escuro", icone: "☾", dica: "Tema escuro" },
];

const MENU: ItemMenu[] = [
  { para: "/", rotulo: "Início", icone: "⌂", papeis: AGENDA },
  { para: "/pacientes", rotulo: "Pacientes", icone: "☺", papeis: AGENDA },
  { para: "/agenda", rotulo: "Agenda", icone: "▦", papeis: AGENDA },
  { para: "/alertas", rotulo: "Alertas", icone: "!", papeis: AGENDA },
  { para: "/gestao", rotulo: "Gestão", icone: "▲", papeis: [...GESTAO, "dentista"] },
  { para: "/estoque", rotulo: "Estoque", icone: "▤", papeis: CLINICOS },
  { para: "/financeiro", rotulo: "Financeiro", icone: "¤", papeis: [...GESTAO, "dentista"] },
  { para: "/precificacao", rotulo: "Precificação", icone: "$", papeis: GESTAO },
  { para: "/configuracoes", rotulo: "Configurações", icone: "⚙", papeis: GESTAO },
];

export default function AppLayout() {
  const sessao = useSessao();
  const local = useLocation();
  const cliente = useQueryClient();
  const [menuAberto, setMenuAberto] = useState(false);
  const [tema, setTema] = useTema();

  if (!sessaoValida(sessao)) {
    return <Navigate to="/login" replace state={{ de: local.pathname }} />;
  }

  const itens = MENU.filter((i) => temPapel(sessao.papel, ...i.papeis));

  function sair() {
    cliente.clear(); // nada de dado de paciente em memória depois de sair
    sessao.sair();
  }

  return (
    <div className="flex min-h-full">
      {/* Menu lateral: fixo no tablet na horizontal, gaveta no celular/retrato. */}
      <nav
        aria-label="Menu principal"
        className={`nao-imprimir fixed inset-y-0 left-0 z-30 flex w-60 flex-col border-r border-borda bg-painel p-3 transition-transform lg:static lg:translate-x-0 ${
          menuAberto ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="mb-4 flex items-center gap-2 px-2 py-1">
          <img src="/icone.svg" alt="" className="size-9" />
          <div className="min-w-0">
            <p className="truncate text-sm font-bold">{sessao.clinica?.nome}</p>
            <p className="text-xs text-texto-suave">{sessao.papel && NOME_PAPEL[sessao.papel]}</p>
          </div>
        </div>
        <ul className="flex flex-1 flex-col gap-1">
          {itens.map((i) => (
            <li key={i.para}>
              <NavLink
                to={i.para}
                end={i.para === "/"}
                onClick={() => setMenuAberto(false)}
                className={({ isActive }) =>
                  `flex min-h-12 items-center gap-3 rounded-lg px-3 text-sm font-semibold ${
                    isActive ? "bg-marca-suave text-marca" : "text-texto hover:bg-fundo"
                  }`
                }
              >
                <span aria-hidden className="w-5 text-center text-lg">
                  {i.icone}
                </span>
                {i.rotulo}
              </NavLink>
            </li>
          ))}
        </ul>
        <div className="border-t border-borda pt-3">
          <div role="radiogroup" aria-label="Tema" className="mb-3 flex rounded-lg border border-borda p-1">
            {TEMAS.map((t) => (
              <button
                key={t.id}
                type="button"
                role="radio"
                aria-checked={tema === t.id}
                title={t.dica}
                onClick={() => setTema(t.id)}
                className={`flex min-h-9 flex-1 items-center justify-center gap-1 rounded-md text-xs font-semibold ${
                  tema === t.id ? "bg-marca-suave text-marca" : "text-texto-suave hover:text-texto"
                }`}
              >
                <span aria-hidden>{t.icone}</span>
                {t.rotulo}
              </button>
            ))}
          </div>
          <p className="truncate px-3 text-xs text-texto-suave">{sessao.usuario?.nome}</p>
          <button
            type="button"
            onClick={sair}
            className="mt-1 flex min-h-11 w-full items-center rounded-lg px-3 text-sm font-semibold text-perigo hover:bg-perigo-suave"
          >
            Sair
          </button>
        </div>
      </nav>
      {menuAberto && (
        <button
          type="button"
          aria-label="Fechar menu"
          className="fixed inset-0 z-20 bg-black/40 lg:hidden"
          onClick={() => setMenuAberto(false)}
        />
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="nao-imprimir sticky top-0 z-10 flex items-center gap-3 border-b border-borda bg-painel/90 px-4 py-2 backdrop-blur lg:hidden">
          <button
            type="button"
            aria-label="Abrir menu"
            onClick={() => setMenuAberto(true)}
            className="flex size-11 items-center justify-center rounded-lg text-2xl hover:bg-fundo"
          >
            ☰
          </button>
          <span className="truncate font-semibold">{sessao.clinica?.nome}</span>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 p-4 lg:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
