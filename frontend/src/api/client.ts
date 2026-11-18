import createClient, { type Middleware } from "openapi-fetch";

import { useSessao } from "../auth/sessao";
import type { components, paths } from "./schema";

export type Schemas = components["schemas"];

/** Base da API: em dev o Vite repassa /api para http://localhost:8000. */
export const API_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? "/api";

const autenticacao: Middleware = {
  onRequest({ request }) {
    const token = useSessao.getState().token;
    if (token) request.headers.set("Authorization", `Bearer ${token}`);
    return request;
  },
  onResponse({ response }) {
    // Token vencido ou acesso revogado: volta para o login.
    if (response.status === 401 && useSessao.getState().token) {
      useSessao.getState().sair("Sua sessão expirou. Entre de novo.");
    }
    return response;
  },
};

export const api = createClient<paths>({ baseUrl: API_URL });
api.use(autenticacao);

/** Mensagem legível de um erro da API (FastAPI: detail texto ou lista de validação). */
export function mensagemErro(erro: unknown, padrao = "Não foi possível concluir."): string {
  if (!erro) return padrao;
  if (typeof erro === "string") return erro;
  if (erro instanceof Error) return erro.message || padrao;
  const detail = (erro as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    return detail
      .map((d: { msg?: string; loc?: unknown[] }) => {
        const campo = Array.isArray(d.loc) ? d.loc.slice(1).join(".") : "";
        const msg = (d.msg ?? "").replace(/^Value error, /, "");
        return campo ? `${campo}: ${msg}` : msg;
      })
      .join("; ");
  }
  return padrao;
}

/** Desembrulha a resposta do openapi-fetch: devolve os dados ou lança Error com a mensagem. */
export function ok<T>(res: { data?: T; error?: unknown; response: Response }): T {
  if (res.error !== undefined || !res.response.ok) {
    throw new Error(mensagemErro(res.error, `Erro ${res.response.status}`));
  }
  return res.data as T;
}

/** Busca binária autenticada (GLB, DICOM) fora do cliente tipado. */
export async function baixar(caminho: string): Promise<Blob> {
  const token = useSessao.getState().token;
  const resp = await fetch(`${API_URL}${caminho}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (resp.status === 401) useSessao.getState().sair("Sua sessão expirou. Entre de novo.");
  if (!resp.ok) throw new Error(`Erro ${resp.status} ao baixar o arquivo.`);
  return resp.blob();
}
