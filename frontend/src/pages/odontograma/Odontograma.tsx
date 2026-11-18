import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { lazy, Suspense, useMemo, useState } from "react";

import { api, ok, type Schemas } from "../../api/client";
import { temPapel, useSessao } from "../../auth/sessao";
import { Aviso, Botao, Campo, Cartao, Carregando, ErroCarga, Etiqueta, Selecao } from "../../components/ui";
import { dataHoraBR, instante } from "../../lib/datas";
import Arcada from "./Arcada";
import Boca2D from "./Boca2D";
import Dente2D, { type DenteVis } from "./Dente2D";
import { LADO, superior } from "./geometria";
import Legenda from "./Legenda";

const Odontograma3D = lazy(() => import("./Odontograma3D"));

type Paciente = Schemas["PatientOut"];
type Item = Schemas["StatusOut"];

export default function Odontograma({ paciente }: { paciente: Paciente }) {
  const { papel } = useSessao();
  const cliente = useQueryClient();
  const podeMarcar = temPapel(papel, "admin", "dentista", "asb");
  const podeEditarCores = temPapel(papel, "admin", "gestor", "dentista");
  const [editando, setEditando] = useState(false);
  const [visao, setVisao] = useState<"2d" | "3d">("2d");
  const [item, setItem] = useState<Item | null>(null);
  const [dente, setDente] = useState<number | null>(null);
  const [atendimento, setAtendimento] = useState("");
  const [verEm, setVerEm] = useState(""); // AAAA-MM-DD: odontograma como estava
  const [erro, setErro] = useState<string | null>(null);
  const [arcadaAberta, setArcadaAberta] = useState(false);

  const em = verEm ? instante(verEm, "23:59") : undefined;
  const chave = ["odontograma", paciente.id, em ?? "agora"];
  const vis = useQuery({
    queryKey: chave,
    queryFn: async () =>
      ok(
        await api.GET("/odontograma/pacientes/{patient_id}/visualizacao", {
          params: { path: { patient_id: paciente.id }, query: { em } },
        }),
      ),
  });
  const legenda = useQuery({
    queryKey: ["odontograma", "legenda"],
    queryFn: async () => ok(await api.GET("/odontograma/legenda")),
  });
  const atendimentos = useQuery({
    enabled: podeMarcar,
    queryKey: ["atendimentos", paciente.id],
    queryFn: async () =>
      ok(
        await api.GET("/prontuario/pacientes/{patient_id}/atendimentos", {
          params: { path: { patient_id: paciente.id } },
        }),
      ),
  });
  const abertos = (atendimentos.data ?? []).filter((a) => a.status === "aberto");

  const marcar = useMutation({
    mutationFn: async (ev: Schemas["EventIn"]) =>
      ok(
        await api.POST("/odontograma/pacientes/{patient_id}/eventos", {
          params: { path: { patient_id: paciente.id } },
          body: { encounter_id: atendimento || null, events: [ev] },
        }),
      ),
    onSuccess: () => {
      setErro(null);
      cliente.invalidateQueries({ queryKey: ["odontograma", paciente.id] });
    },
    onError: (e) => setErro(e.message),
  });

  const dentes = vis.data?.teeth ?? [];
  const sup = dentes.filter((d) => superior(d.tooth));
  const inf = dentes.filter((d) => !superior(d.tooth));
  const selecionado = dentes.find((d) => d.tooth === dente) ?? null;
  const ativos = useMemo(() => (legenda.data ?? []).filter((l) => l.active), [legenda.data]);
  const emUso = useMemo(() => new Set((vis.data?.legend ?? []).map((l) => l.id)), [vis.data]);

  function tocar(d: DenteVis, face: string | null) {
    setDente(d.tooth);
    if (!podeMarcar || !item) return;
    const porFace = item.scope === "face";
    const f = porFace ? face : null;
    if (porFace && !f) {
      setErro(`"${item.name}" é marcado por face: toque numa face do dente.`);
      return;
    }
    const jaTem = porFace
      ? Object.values(d.faces).some((x) => x.face === f && x.marks.some((m) => m.status_id === item.id))
      : d.whole.some((m) => m.status_id === item.id);
    marcar.mutate({ tooth: d.tooth, face: f, status_id: item.id, action: jaTem ? "remover" : "marcar" });
  }

  const legendaLateral = (
    <Legenda itens={ativos} emUso={emUso} podeEditar={podeEditarCores} />
  );

  if (!editando) {
    return (
      <div className="flex flex-col gap-4">
        <div className="nao-imprimir flex flex-wrap items-end gap-3">
          <Campo rotulo="Ver como estava em" type="date" value={verEm} onChange={(e) => setVerEm(e.target.value)} />
          {verEm && (
            <Botao variante="fantasma" onClick={() => setVerEm("")}>
              Voltar para hoje
            </Botao>
          )}
        </div>
        {verEm && <Aviso tom="alerta">Mostrando o odontograma como estava em {verEm.split("-").reverse().join("/")}.</Aviso>}
        {vis.isLoading && <Carregando />}
        {vis.error && <ErroCarga erro={vis.error} />}
        {vis.data && (
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start">
            <div className="grid min-w-0 flex-1 gap-4 md:grid-cols-2">
              <Cartao className="flex flex-col">
                <Boca2D dentes={dentes} selecionado={dente} aoTocar={(d) => setDente(d.tooth)} />
                <p className="mt-2 text-center text-xs text-texto-suave">
                  Arcada {vis.data.arch.dentition} ({vis.data.arch.source === "padrao" ? "sugerida pela idade" : "registrada"}) ·
                  atualizado em {dataHoraBR(vis.data.at)}
                </p>
              </Cartao>
              <Suspense fallback={<Cartao><Carregando texto="Carregando o modelo 3D…" /></Cartao>}>
                <Odontograma3D vis={vis.data} selecionado={dente} aoTocar={(d) => setDente(d.tooth)} compacto />
              </Suspense>
            </div>
            <aside className="lg:w-52 lg:shrink-0">{legendaLateral}</aside>
          </div>
        )}
        {podeMarcar && !verEm && vis.data && (
          <div className="nao-imprimir flex justify-center">
            <Botao onClick={() => setEditando(true)}>Editar odontograma</Botao>
          </div>
        )}
        {selecionado && <DetalheDente dente={selecionado} />}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="nao-imprimir flex flex-wrap items-end gap-3">
        <Botao variante="secundario" onClick={() => { setEditando(false); setItem(null); setErro(null); }}>
          ← Concluir edição
        </Botao>
        <div className="flex rounded-lg border border-borda p-1">
          {(["2d", "3d"] as const).map((v) => (
            <button
              key={v}
              type="button"
              onClick={() => setVisao(v)}
              className={`min-h-10 rounded-md px-4 text-sm font-semibold ${visao === v ? "bg-marca text-white dark:text-slate-900" : ""}`}
            >
              {v.toUpperCase()}
            </button>
          ))}
        </div>
        {podeMarcar && abertos.length > 0 && (
          <Selecao rotulo="Vincular ao atendimento" value={atendimento} onChange={(e) => setAtendimento(e.target.value)}>
            <option value="">— nenhum —</option>
            {abertos.map((a) => (
              <option key={a.id} value={a.id}>
                Aberto em {dataHoraBR(a.started_at)}
              </option>
            ))}
          </Selecao>
        )}
        {podeMarcar && (
          <Botao variante="secundario" onClick={() => setArcadaAberta(true)}>
            Arcada
          </Botao>
        )}
      </div>

      {erro && <Aviso tom="perigo">{erro}</Aviso>}

      {podeMarcar && (
        <Cartao titulo="1. Escolha o que marcar · 2. Toque na face ou no número do dente">
          <div className="flex flex-wrap gap-2">
            {ativos.map((l) => (
              <button
                key={l.id}
                type="button"
                onClick={() => setItem(item?.id === l.id ? null : l)}
                className={`flex min-h-11 items-center gap-2 rounded-lg border px-3 text-sm ${
                  item?.id === l.id ? "border-marca ring-2 ring-marca" : "border-borda"
                }`}
              >
                <span className="size-4 rounded-sm" style={{ background: l.color }} />
                {l.name}
                <span className="text-xs text-texto-suave">({l.scope === "face" ? "face" : "dente"})</span>
              </button>
            ))}
          </div>
          {item && (
            <p className="mt-2 text-xs text-texto-suave">
              Tocar de novo onde já está marcado remove a marcação (fica no histórico).
            </p>
          )}
        </Cartao>
      )}

      {vis.isLoading && <Carregando />}
      {vis.error && <ErroCarga erro={vis.error} />}

      {vis.data && visao === "2d" && (
        <Cartao>
          <div className="overflow-x-auto">
            <Fileira dentes={sup} selecionado={dente} aoTocar={tocar} />
            <div className="my-1 border-t border-dashed border-borda" />
            <Fileira dentes={inf} selecionado={dente} aoTocar={tocar} />
          </div>
          <p className="mt-2 text-xs text-texto-suave">
            Arcada {vis.data.arch.dentition} ({vis.data.arch.source === "padrao" ? "sugerida pela idade" : "registrada"}) ·
            atualizado em {dataHoraBR(vis.data.at)}
          </p>
        </Cartao>
      )}

      {vis.data && visao === "3d" && (
        <Suspense fallback={<Carregando texto="Carregando o modelo 3D…" />}>
          <Odontograma3D vis={vis.data} selecionado={dente} aoTocar={(d, face) => tocar(d, face)} />
        </Suspense>
      )}

      {selecionado && <DetalheDente dente={selecionado} />}

      {arcadaAberta && vis.data && (
        <Arcada paciente={paciente} atual={vis.data.arch} aoFechar={() => setArcadaAberta(false)} />
      )}
    </div>
  );
}

function Fileira({
  dentes,
  selecionado,
  aoTocar,
}: {
  dentes: DenteVis[];
  selecionado: number | null;
  aoTocar: (d: DenteVis, face: string | null) => void;
}) {
  const passo = LADO + 10;
  const largura = Math.max(dentes.length * passo + 20, 200);
  return (
    <svg viewBox={`-10 -22 ${largura} ${LADO + 44}`} className="h-auto w-full min-w-[640px] text-texto" role="img" aria-label="Odontograma">
      {dentes.map((d, i) => (
        <Dente2D
          key={d.tooth}
          dente={d}
          x={i * passo + (i >= dentes.length / 2 ? 12 : 0)}
          y={0}
          selecionado={d.tooth === selecionado}
          aoTocarFace={(face) => aoTocar(d, face)}
          aoTocarDente={() => aoTocar(d, null)}
        />
      ))}
    </svg>
  );
}

function DetalheDente({ dente }: { dente: DenteVis }) {
  const faces = Object.entries(dente.faces).filter(([, f]) => f.marks.length > 0);
  return (
    <Cartao titulo={`Dente ${dente.tooth}${dente.deciduous ? " (decíduo)" : ""}`}>
      {!dente.in_arch && <Aviso tom="alerta">Este dente tem marcação mas não está na arcada atual.</Aviso>}
      {dente.whole.length === 0 && faces.length === 0 && <p className="text-sm text-texto-suave">Sem marcações.</p>}
      <div className="flex flex-wrap gap-2">
        {dente.whole.map((m) => (
          <Etiqueta key={m.status_id}>
            <span className="mr-1 inline-block size-3 rounded-sm" style={{ background: m.color }} />
            {m.name} (dente)
          </Etiqueta>
        ))}
        {faces.map(([rotulo, f]) =>
          f.marks.map((m) => (
            <Etiqueta key={`${rotulo}-${m.status_id}`}>
              <span className="mr-1 inline-block size-3 rounded-sm" style={{ background: m.color }} />
              {m.name} ({rotulo})
            </Etiqueta>
          )),
        )}
      </div>
    </Cartao>
  );
}
