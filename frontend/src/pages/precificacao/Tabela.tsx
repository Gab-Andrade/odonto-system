import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, baixar, mensagemErro, ok, type Schemas } from "../../api/client";
import { Aviso, Botao, Campo, Cartao, Carregando, ErroCarga, Etiqueta, Selecao } from "../../components/ui";
import { dataBR, dinheiro } from "../../lib/datas";
import Importar from "./Importar";

type Versao = Schemas["app__modules__precificacao__schemas__VersionOut"];
interface Linha {
  procedure_code: string;
  description: string;
  category: string;
  price: string;
}

async function salvarArquivo(caminho: string, nome: string) {
  const blob = await baixar(caminho);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nome;
  a.click();
  URL.revokeObjectURL(url);
}

export default function Tabela({ tabelaId, aoVoltar }: { tabelaId: string; aoVoltar: () => void }) {
  const cliente = useQueryClient();
  const [versaoId, setVersaoId] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [importar, setImportar] = useState(false);

  const tabela = useQuery({
    queryKey: ["precificacao", "tabela", tabelaId],
    queryFn: async () => ok(await api.GET("/precificacao/tabelas/{table_id}", { params: { path: { table_id: tabelaId } } })),
  });
  const versoes = useQuery({
    queryKey: ["precificacao", "versoes", tabelaId],
    queryFn: async () =>
      ok(await api.GET("/precificacao/tabelas/{table_id}/versoes", { params: { path: { table_id: tabelaId } } })),
  });
  const lista = [...(versoes.data ?? [])].sort((a, b) => b.version - a.version);
  const atual: Versao | undefined = lista.find((v) => v.id === versaoId) ?? lista.find((v) => v.status === "rascunho") ?? lista[0];

  const itens = useQuery({
    enabled: Boolean(atual),
    queryKey: ["precificacao", "itens", atual?.id],
    queryFn: async () =>
      ok(
        await api.GET("/precificacao/tabelas/{table_id}/versoes/{version_id}/itens", {
          params: { path: { table_id: tabelaId, version_id: atual!.id } },
        }),
      ),
  });

  const atualizar = () => {
    cliente.invalidateQueries({ queryKey: ["precificacao"] });
    cliente.invalidateQueries({ queryKey: ["procedimentos"] });
  };
  const acao = useMutation({
    mutationFn: async (f: () => Promise<string>) => f(),
    onSuccess: (m) => {
      setErro(null);
      setMsg(m);
      atualizar();
    },
    onError: (e) => {
      setMsg(null);
      setErro(e.message);
    },
  });

  if (tabela.isLoading || versoes.isLoading) return <Carregando />;
  if (tabela.error) return <ErroCarga erro={tabela.error} />;
  const t = tabela.data!;
  const rascunho = atual?.status === "rascunho";
  const calculada = t.kind === "calculada";
  const path = { table_id: tabelaId, version_id: atual?.id ?? "" };

  const novoRascunho = () =>
    acao.mutate(async () => {
      const v = ok(await api.POST("/precificacao/tabelas/{table_id}/versoes", { params: { path: { table_id: tabelaId } } }));
      setVersaoId(v.id);
      return `Rascunho da versão ${v.version} aberto a partir da última publicada.`;
    });
  const publicar = (confirmar = false) =>
    acao.mutate(async () => {
      const v = ok(
        await api.POST("/precificacao/tabelas/{table_id}/versoes/{version_id}/publicar", {
          params: { path },
          body: { valid_from: null, confirmar_erros: confirmar },
        }),
      );
      return `Versão ${v.version} publicada, vale a partir de ${dataBR(v.valid_from)}.`;
    });
  const recalcular = () =>
    acao.mutate(async () => {
      const r = ok(await api.POST("/precificacao/tabelas/{table_id}/versoes/{version_id}/recalcular", { params: { path } }));
      return `${r.calculados} preço(s) calculado(s)${r.erros.length ? `; ${r.erros.length} com erro: ${r.erros.map((e) => Object.values(e).join(" ")).join("; ")}` : ""}.`;
    });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <Botao variante="fantasma" onClick={aoVoltar}>
          ← Tabelas
        </Botao>
        <h2 className="flex-1 text-lg font-bold">{t.name}</h2>
        <Selecao rotulo="Versão" value={atual?.id ?? ""} onChange={(e) => setVersaoId(e.target.value)}>
          {lista.map((v) => (
            <option key={v.id} value={v.id}>
              v{v.version} · {v.status}
              {v.valid_from ? ` desde ${dataBR(v.valid_from)}` : ""}
            </option>
          ))}
        </Selecao>
      </div>
      {erro && <Aviso tom="perigo">{erro}</Aviso>}
      {msg && <Aviso tom="sucesso">{msg}</Aviso>}

      <Cartao
        titulo={
          <span className="flex items-center gap-2">
            Versão {atual?.version}
            <Etiqueta tom={rascunho ? "alerta" : "sucesso"}>{atual?.status}</Etiqueta>
            {atual?.adjustment_pct && <Etiqueta>ajuste {atual.adjustment_pct}% sobre a mãe</Etiqueta>}
          </span>
        }
        acoes={
          <>
            {!lista.some((v) => v.status === "rascunho") && t.status === "ativa" && (
              <Botao variante="secundario" onClick={novoRascunho}>
                Nova versão (rascunho)
              </Botao>
            )}
            {rascunho && !calculada && (
              <Botao variante="secundario" onClick={() => setImportar(true)}>
                Importar planilha
              </Botao>
            )}
            {rascunho && calculada && (
              <Botao variante="secundario" onClick={recalcular} carregando={acao.isPending}>
                Recalcular preços
              </Botao>
            )}
            {rascunho && (
              <Botao onClick={() => publicar(false)} carregando={acao.isPending}>
                Publicar
              </Botao>
            )}
            {atual && (
              <Botao
                variante="fantasma"
                onClick={() =>
                  salvarArquivo(`/precificacao/tabelas/${tabelaId}/versoes/${atual.id}/exportar`, `${t.name}-v${atual.version}.xlsx`).catch((e) =>
                    setErro(mensagemErro(e)),
                  )
                }
              >
                Exportar .xlsx
              </Botao>
            )}
          </>
        }
      >
        {erro?.includes("confirmar_erros") && (
          <Botao variante="perigo" className="mb-3" onClick={() => publicar(true)}>
            Publicar mesmo assim (os procedimentos com erro caem para a próxima tabela)
          </Botao>
        )}
        {calculada && (
          <p className="mb-3 text-sm text-texto-suave">
            Preços gerados pela fórmula (custo de materiais + hora clínica + pró-labore, "preço por dentro").
            Fichas técnicas, variáveis e a fórmula ficam na API (/precificacao/fichas, /variaveis, /formula); o
            editor visual de fórmulas entra depois.
          </p>
        )}
        {itens.isLoading && <Carregando />}
        {itens.error && <ErroCarga erro={itens.error} />}
        {itens.data && (
          <Itens
            key={`${atual?.id}-${itens.dataUpdatedAt}`}
            itens={itens.data}
            editavel={rascunho && !calculada}
            aoSalvar={(linhas) =>
              acao.mutate(async () => {
                ok(
                  await api.PUT("/precificacao/tabelas/{table_id}/versoes/{version_id}/itens", {
                    params: { path },
                    body: {
                      items: linhas.map((l) => ({
                        procedure_code: l.procedure_code.trim(),
                        description: l.description.trim(),
                        category: l.category.trim() || null,
                        price: l.price.replace(",", "."),
                      })),
                    },
                  }),
                );
                return `${linhas.length} item(ns) salvos no rascunho.`;
              })
            }
          />
        )}
      </Cartao>
      {importar && atual && (
        <Importar
          tabelaId={tabelaId}
          aoFechar={() => setImportar(false)}
          aoAplicar={(m) => {
            setMsg(m);
            atualizar();
          }}
        />
      )}
    </div>
  );
}

function Itens({
  itens,
  editavel,
  aoSalvar,
}: {
  itens: Schemas["app__modules__precificacao__schemas__ItemOut"][];
  editavel: boolean;
  aoSalvar: (linhas: Linha[]) => void;
}) {
  const inicial = () =>
    itens.map((i) => ({ procedure_code: i.procedure_code, description: i.description, category: i.category ?? "", price: String(i.price) }));
  const [linhas, setLinhas] = useState<Linha[]>(inicial);
  const [filtro, setFiltro] = useState("");

  const mudar = (i: number, campo: keyof Linha, v: string) => setLinhas(linhas.map((l, j) => (j === i ? { ...l, [campo]: v } : l)));
  const visiveis = linhas
    .map((l, i) => ({ l, i }))
    .filter(({ l }) => !filtro || `${l.procedure_code} ${l.description} ${l.category}`.toLowerCase().includes(filtro.toLowerCase()));

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end gap-2">
        <Campo rotulo="Filtrar" className="min-w-60 flex-1" value={filtro} onChange={(e) => setFiltro(e.target.value)} />
        {editavel && (
          <>
            <Botao variante="secundario" onClick={() => setLinhas([...linhas, { procedure_code: "", description: "", category: "", price: "0" }])}>
              + Linha
            </Botao>
            <Botao onClick={() => aoSalvar(linhas.filter((l) => l.procedure_code.trim()))}>Salvar itens</Botao>
          </>
        )}
      </div>
      <div className="max-h-[60vh] overflow-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-painel">
            <tr className="border-b border-borda text-left text-xs text-texto-suave">
              <th className="py-2">Código</th>
              <th>Descrição</th>
              <th>Categoria</th>
              <th className="text-right">Preço</th>
              {editavel && <th />}
            </tr>
          </thead>
          <tbody>
            {visiveis.map(({ l, i }) => (
              <tr key={i} className="border-b border-borda/60">
                {editavel ? (
                  <>
                    <td className="py-1 pr-1">
                      <input className="min-h-10 w-28 rounded border border-borda bg-painel px-2" value={l.procedure_code} onChange={(e) => mudar(i, "procedure_code", e.target.value)} />
                    </td>
                    <td className="pr-1">
                      <input className="min-h-10 w-full min-w-48 rounded border border-borda bg-painel px-2" value={l.description} onChange={(e) => mudar(i, "description", e.target.value)} />
                    </td>
                    <td className="pr-1">
                      <input className="min-h-10 w-32 rounded border border-borda bg-painel px-2" value={l.category} onChange={(e) => mudar(i, "category", e.target.value)} />
                    </td>
                    <td className="pr-1 text-right">
                      <input inputMode="decimal" className="min-h-10 w-28 rounded border border-borda bg-painel px-2 text-right" value={l.price} onChange={(e) => mudar(i, "price", e.target.value)} />
                    </td>
                    <td>
                      <button type="button" aria-label="Remover linha" className="min-h-10 px-2 text-perigo" onClick={() => setLinhas(linhas.filter((_, j) => j !== i))}>
                        ×
                      </button>
                    </td>
                  </>
                ) : (
                  <>
                    <td className="py-2 font-mono text-xs">{l.procedure_code}</td>
                    <td>{l.description}</td>
                    <td className="text-texto-suave">{l.category || "—"}</td>
                    <td className="text-right">{dinheiro(l.price)}</td>
                  </>
                )}
              </tr>
            ))}
          </tbody>
        </table>
        {linhas.length === 0 && <p className="p-4 text-center text-sm text-texto-suave">Sem itens{editavel ? ": adicione linhas ou importe uma planilha." : "."}</p>}
      </div>
      <p className="text-xs text-texto-suave">{linhas.length} item(ns). Itens herdados da tabela-mãe não aparecem aqui: são resolvidos na hora do orçamento.</p>
    </div>
  );
}
