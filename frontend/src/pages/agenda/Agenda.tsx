import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { api, ok, type Schemas } from "../../api/client";
import { AGENDA, GESTAO, temPapel, useSessao } from "../../auth/sessao";
import { Botao, Campo, Cartao, Carregando, ErroCarga, Selecao, Titulo } from "../../components/ui";
import { dataBR, hojeISO, horaBR, inicioDoDia, somarDias } from "../../lib/datas";
import { useDentistas } from "../../lib/equipe";
import DetalheAgendamento from "./DetalheAgendamento";
import FormAgendamento from "./FormAgendamento";
import { NOME_STATUS } from "./status";

type Entrada = Schemas["EntryOut"];

const INICIO_DIA = 7; // 07:00
const FIM_DIA = 21; // 21:00
const PX_POR_MIN = 1.4;

const COR_STATUS: Record<string, string> = {
  agendado: "border-marca bg-marca-suave",
  confirmado: "border-sucesso bg-sucesso-suave",
  atendido: "border-texto-suave bg-fundo opacity-70",
  falta: "border-perigo bg-perigo-suave",
  cancelado: "border-borda bg-fundo opacity-50 line-through",
};

function minutosDoDia(iso: string): number {
  const [h, m] = horaBR(iso).split(":").map(Number);
  return h * 60 + m;
}

export default function Agenda() {
  const { papel, usuario } = useSessao();
  const [params] = useSearchParams();
  const [dia, setDia] = useState(hojeISO());
  const [filtroDentista, setFiltroDentista] = useState<string>(
    papel === "dentista" && usuario ? usuario.id : "",
  );
  const [novo, setNovo] = useState<{ inicio?: string; dentista?: string; bloqueio?: boolean } | null>(
    params.get("paciente") ? {} : null,
  );
  const [aberto, setAberto] = useState<Entrada | null>(null);
  const dentistas = useDentistas();

  const entradas = useQuery({
    queryKey: ["agenda", "dia", dia],
    queryFn: async () =>
      ok(
        await api.GET("/agenda/agendamentos", {
          params: { query: { inicio: inicioDoDia(dia), fim: inicioDoDia(somarDias(dia, 1)) } },
        }),
      ),
  });

  const colunas = useMemo(() => {
    const lista = dentistas.data ?? [];
    return filtroDentista ? lista.filter((d) => d.user_id === filtroDentista) : lista;
  }, [dentistas.data, filtroDentista]);

  const horas = Array.from({ length: FIM_DIA - INICIO_DIA }, (_, i) => INICIO_DIA + i);
  const altura = (FIM_DIA - INICIO_DIA) * 60 * PX_POR_MIN;
  const podeEditar = temPapel(papel, ...AGENDA);

  function abrirNovo(dentista: string, ev: React.MouseEvent<HTMLDivElement>) {
    if (!podeEditar) return;
    const y = ev.clientY - ev.currentTarget.getBoundingClientRect().top;
    const min = Math.floor(y / PX_POR_MIN / 15) * 15 + INICIO_DIA * 60;
    const hh = String(Math.floor(min / 60)).padStart(2, "0");
    const mm = String(min % 60).padStart(2, "0");
    setNovo({ inicio: `${dia}T${hh}:${mm}`, dentista });
  }

  return (
    <div>
      <Titulo
        acoes={
          <>
            {temPapel(papel, ...GESTAO, "dentista", "recepcao") && (
              <Botao variante="secundario" onClick={() => setNovo({ bloqueio: true })}>
                Bloquear horário
              </Botao>
            )}
            <Botao onClick={() => setNovo({})}>+ Agendar</Botao>
          </>
        }
      >
        Agenda
      </Titulo>

      <Cartao className="mb-4">
        <div className="flex flex-wrap items-end gap-3">
          <Botao variante="secundario" onClick={() => setDia(somarDias(dia, -1))} aria-label="Dia anterior">
            ‹
          </Botao>
          <Campo rotulo="Dia" type="date" value={dia} onChange={(e) => e.target.value && setDia(e.target.value)} />
          <Botao variante="secundario" onClick={() => setDia(somarDias(dia, 1))} aria-label="Próximo dia">
            ›
          </Botao>
          <Botao variante="fantasma" onClick={() => setDia(hojeISO())}>
            Hoje
          </Botao>
          <Selecao rotulo="Dentista" value={filtroDentista} onChange={(e) => setFiltroDentista(e.target.value)}>
            <option value="">Todos</option>
            {dentistas.data?.map((d) => (
              <option key={d.user_id} value={d.user_id}>
                {d.full_name}
              </option>
            ))}
          </Selecao>
        </div>
      </Cartao>

      {(entradas.isLoading || dentistas.isLoading) && <Carregando />}
      {entradas.error && <ErroCarga erro={entradas.error} />}

      <div className="overflow-x-auto rounded-xl border border-borda bg-painel">
        <div className="flex min-w-fit">
          <div className="sticky left-0 z-10 w-14 shrink-0 border-r border-borda bg-painel">
            <div className="h-10 border-b border-borda" />
            <div className="relative" style={{ height: altura }}>
              {horas.map((h) => (
                <span
                  key={h}
                  className="absolute right-1 -translate-y-2 text-xs text-texto-suave"
                  style={{ top: (h - INICIO_DIA) * 60 * PX_POR_MIN }}
                >
                  {String(h).padStart(2, "0")}:00
                </span>
              ))}
            </div>
          </div>
          {colunas.map((d) => {
            const doDentista = (entradas.data ?? []).filter((e) => e.dentist_id === d.user_id);
            return (
              <div key={d.user_id} className="min-w-48 flex-1 border-r border-borda last:border-r-0">
                <div className="flex h-10 items-center justify-center border-b border-borda px-2 text-sm font-semibold">
                  <span className="truncate">{d.full_name}</span>
                </div>
                <div
                  className="relative cursor-copy"
                  style={{ height: altura }}
                  onClick={(ev) => abrirNovo(d.user_id, ev)}
                >
                  {horas.map((h) => (
                    <div
                      key={h}
                      className="absolute inset-x-0 border-t border-borda/60"
                      style={{ top: (h - INICIO_DIA) * 60 * PX_POR_MIN }}
                    />
                  ))}
                  {doDentista.map((e) => {
                    const ini = Math.max(minutosDoDia(e.starts_at), INICIO_DIA * 60);
                    const fim = Math.min(minutosDoDia(e.ends_at) || FIM_DIA * 60, FIM_DIA * 60);
                    const bloqueio = e.kind === "bloqueio";
                    return (
                      <button
                        key={e.id}
                        type="button"
                        onClick={(ev) => {
                          ev.stopPropagation();
                          setAberto(e);
                        }}
                        className={`absolute inset-x-1 overflow-hidden rounded-md border-l-4 px-2 py-1 text-left text-xs ${
                          bloqueio ? "border-texto-suave bg-borda/60" : COR_STATUS[e.status]
                        }`}
                        style={{
                          top: (ini - INICIO_DIA * 60) * PX_POR_MIN,
                          height: Math.max((fim - ini) * PX_POR_MIN - 2, 22),
                        }}
                      >
                        <span className="font-semibold">
                          {horaBR(e.starts_at)} {bloqueio ? "Bloqueado" : e.patient_name}
                        </span>
                        <span className="block truncate text-texto-suave">
                          {bloqueio ? e.notes : `${e.procedure ?? ""} · ${NOME_STATUS[e.status]}`}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </div>
      <p className="mt-2 text-xs text-texto-suave">
        {dataBR(dia)} · toque num horário vazio para agendar; toque num agendamento para ver,
        confirmar, remarcar ou cancelar.
      </p>

      {novo && (
        <FormAgendamento
          dia={dia}
          inicial={novo}
          pacienteInicial={params.get("paciente")}
          aoFechar={() => setNovo(null)}
        />
      )}
      {aberto && <DetalheAgendamento entrada={aberto} aoFechar={() => setAberto(null)} />}
    </div>
  );
}
