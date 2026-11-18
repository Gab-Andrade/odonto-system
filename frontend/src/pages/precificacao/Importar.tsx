import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { api, API_URL, baixar, mensagemErro, ok, type Schemas } from "../../api/client";
import { useSessao } from "../../auth/sessao";
import Modal from "../../components/Modal";
import { Aviso, Botao, Selecao } from "../../components/ui";

type Job = Schemas["ImportJobOut"];

const CAMPOS: [string, string][] = [
  ["procedure_code", "Código *"],
  ["description", "Descrição *"],
  ["price", "Preço *"],
  ["category", "Categoria"],
];

interface Relatorio {
  total_linhas?: number;
  linhas_validas?: number;
  total_erros?: number;
  erros?: { linha: number; campo: string; valor: string; erro: string }[];
  total_avisos?: number;
  diferencas?: { novos: number; alterados: number; removidos: number; inalterados: number };
}

/** Upload → mapeamento de colunas → prévia com erros e diff → aplicar no rascunho. */
export default function Importar({
  tabelaId,
  aoFechar,
  aoAplicar,
}: {
  tabelaId: string;
  aoFechar: () => void;
  aoAplicar: (msg: string) => void;
}) {
  const { token } = useSessao();
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [mapa, setMapa] = useState<Record<string, string>>({});
  const [erro, setErro] = useState<string | null>(null);

  const enviar = useMutation({
    mutationFn: async () => {
      const corpo = new FormData();
      corpo.append("arquivo", arquivo!);
      corpo.append("table_id", tabelaId);
      const resp = await fetch(`${API_URL}/precificacao/importacoes`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: corpo,
      });
      const dados = await resp.json().catch(() => null);
      if (!resp.ok) throw new Error(mensagemErro(dados, `Erro ${resp.status}`));
      return dados as Job;
    },
    onSuccess: (j) => {
      setErro(null);
      setJob(j);
      const sugerido = (j.detected?.mapeamento_sugerido ?? {}) as Record<string, string | null>;
      setMapa(Object.fromEntries(Object.entries(sugerido).filter(([, v]) => v)) as Record<string, string>);
    },
    onError: (e) => setErro(e.message),
  });

  const validar = useMutation({
    mutationFn: async () =>
      ok(
        await api.POST("/precificacao/importacoes/{job_id}/validar", {
          params: { path: { job_id: job!.id } },
          body: { column_map: mapa },
        }),
      ),
    onSuccess: (j) => {
      setErro(null);
      setJob(j);
    },
    onError: (e) => setErro(e.message),
  });

  const aplicar = useMutation({
    mutationFn: async (ignorar: boolean) =>
      ok(
        await api.POST("/precificacao/importacoes/{job_id}/aplicar", {
          params: { path: { job_id: job!.id } },
          body: { ignorar_erros: ignorar },
        }),
      ),
    onSuccess: (r) => {
      aoAplicar(`Planilha aplicada no rascunho da versão ${r.versao.version}. Confira e publique.`);
      aoFechar();
    },
    onError: (e) => setErro(e.message),
  });

  const rel = (job?.report ?? null) as Relatorio | null;
  const d = rel?.diferencas;

  return (
    <Modal titulo="Importar planilha de preços" aberto aoFechar={aoFechar} largura="max-w-3xl">
      <div className="flex flex-col gap-4">
        {erro && <Aviso tom="perigo">{erro}</Aviso>}
        <div className="flex flex-wrap items-center gap-3">
          <input type="file" accept=".csv,.xlsx" onChange={(e) => setArquivo(e.target.files?.[0] ?? null)} className="min-h-11 text-sm" />
          <Botao onClick={() => enviar.mutate()} disabled={!arquivo} carregando={enviar.isPending}>
            Ler arquivo
          </Botao>
          <Botao
            variante="fantasma"
            onClick={() =>
              baixar("/precificacao/importacoes/modelo")
                .then((b) => {
                  const url = URL.createObjectURL(b);
                  const a = document.createElement("a");
                  a.href = url;
                  a.download = "modelo-tabela-precos.xlsx";
                  a.click();
                  URL.revokeObjectURL(url);
                })
                .catch((e) => setErro(mensagemErro(e)))
            }
          >
            Baixar planilha-modelo
          </Botao>
        </div>
        <p className="text-xs text-texto-suave">.csv ou .xlsx até 2 MB. Encoding, separador e números no formato brasileiro (1.234,56) são detectados sozinhos.</p>

        {job && (
          <>
            <div>
              <p className="mb-2 text-sm font-semibold">Qual coluna da planilha vai para cada campo?</p>
              <div className="grid gap-3 sm:grid-cols-4">
                {CAMPOS.map(([campo, rotulo]) => (
                  <Selecao key={campo} rotulo={rotulo} value={mapa[campo] ?? ""} onChange={(e) => setMapa({ ...mapa, [campo]: e.target.value })}>
                    <option value="">—</option>
                    {job.headers.map((h) => (
                      <option key={h} value={h}>
                        {h}
                      </option>
                    ))}
                  </Selecao>
                ))}
              </div>
            </div>
            <Botao className="self-start" variante="secundario" onClick={() => validar.mutate()} carregando={validar.isPending}>
              Validar e ver diferenças
            </Botao>
          </>
        )}

        {rel && (
          <div className="flex flex-col gap-2 rounded-lg border border-borda p-3 text-sm">
            <p>
              {rel.linhas_validas} de {rel.total_linhas} linha(s) válidas · {rel.total_erros ?? 0} erro(s) · {rel.total_avisos ?? 0} aviso(s)
            </p>
            {d && (
              <p>
                Contra a versão atual: <strong>{d.novos}</strong> novos, <strong>{d.alterados}</strong> alterados,{" "}
                <strong>{d.removidos}</strong> removidos, {d.inalterados} iguais.
              </p>
            )}
            {rel.erros && rel.erros.length > 0 && (
              <ul className="max-h-40 overflow-y-auto text-xs text-perigo">
                {rel.erros.map((e, i) => (
                  <li key={i}>
                    Linha {e.linha}: {e.campo} — {e.erro} {e.valor && `("${e.valor}")`}
                  </li>
                ))}
              </ul>
            )}
            <div className="flex flex-wrap gap-2">
              <Botao onClick={() => aplicar.mutate(false)} carregando={aplicar.isPending} disabled={(rel.total_erros ?? 0) > 0}>
                Aplicar no rascunho
              </Botao>
              {(rel.total_erros ?? 0) > 0 && (
                <Botao variante="secundario" onClick={() => aplicar.mutate(true)} carregando={aplicar.isPending}>
                  Aplicar só as linhas válidas
                </Botao>
              )}
            </div>
            <p className="text-xs text-texto-suave">Aplicar grava só no rascunho; nada muda nos orçamentos até publicar.</p>
          </div>
        )}
      </div>
    </Modal>
  );
}
