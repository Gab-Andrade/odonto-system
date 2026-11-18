import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

export type Papel = "admin" | "gestor" | "dentista" | "asb" | "recepcao";

export const NOME_PAPEL: Record<Papel, string> = {
  admin: "Administrador",
  gestor: "Gestor",
  dentista: "Dentista",
  asb: "ASB",
  recepcao: "Recepção",
};

interface Usuario {
  id: string;
  nome: string;
  email: string;
}

interface Sessao {
  token: string | null;
  expiraEm: number | null; // epoch ms
  clinica: { id: string; nome: string } | null;
  papel: Papel | null;
  usuario: Usuario | null;
  aviso: string | null; // mensagem mostrada no login (ex.: sessão expirada)
  entrar: (dados: {
    token: string;
    expiraEmSegundos: number;
    clinica: { id: string; nome: string };
    papel: Papel;
  }) => void;
  definirUsuario: (usuario: Usuario) => void;
  sair: (aviso?: string) => void;
}

/**
 * Sessão no sessionStorage: some ao fechar o navegador (tablet compartilhado na clínica).
 * O papel aqui só decide o que aparece no menu; quem autoriza é sempre a API.
 */
export const useSessao = create<Sessao>()(
  persist(
    (set) => ({
      token: null,
      expiraEm: null,
      clinica: null,
      papel: null,
      usuario: null,
      aviso: null,
      entrar: ({ token, expiraEmSegundos, clinica, papel }) =>
        set({
          token,
          expiraEm: Date.now() + expiraEmSegundos * 1000,
          clinica,
          papel,
          aviso: null,
        }),
      definirUsuario: (usuario) => set({ usuario }),
      sair: (aviso) =>
        set({
          token: null,
          expiraEm: null,
          clinica: null,
          papel: null,
          usuario: null,
          aviso: aviso ?? null,
        }),
    }),
    { name: "odonto-sessao", storage: createJSONStorage(() => sessionStorage) },
  ),
);

export function sessaoValida(s: Pick<Sessao, "token" | "expiraEm">): boolean {
  return Boolean(s.token && s.expiraEm && s.expiraEm > Date.now());
}

export function temPapel(papel: Papel | null, ...permitidos: Papel[]): boolean {
  return papel !== null && permitidos.includes(papel);
}

// Grupos usados no menu e nas telas (espelham as regras da API).
export const CLINICOS: Papel[] = ["admin", "gestor", "dentista", "asb"];
export const DENTISTAS: Papel[] = ["admin", "dentista"];
export const GESTAO: Papel[] = ["admin", "gestor"];
export const AGENDA: Papel[] = ["admin", "gestor", "dentista", "asb", "recepcao"];
