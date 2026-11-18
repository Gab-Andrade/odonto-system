import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api, ok, type Schemas } from "../../api/client";
import { DENTISTAS, temPapel, useSessao } from "../../auth/sessao";
import Modal from "../../components/Modal";
import { Aviso, Botao, Campo, Etiqueta } from "../../components/ui";
import { dataHoraBR, dataLocalISO, horaBR, instante } from "../../lib/datas";
import { nomeMembro, useEquipe } from "../../lib/equipe";
import { NOME_STATUS, PROXIMOS, TOM_STATUS, type StatusAgenda } from "./status";

type Entrada = Schemas["EntryOut"];

const ACAO: Partial<Record<StatusAgenda, string>> = {
  confirmado: "Confirmar",
  atendido: "Marcar atendido",
  falta: "Faltou",
  cancelado: "Cancelar",
};

export default function DetalheAgendamento({
  entrada: e,
  aoFechar,
}: {
  entrada: Entrada;
  aoFechar: () => void;
}) {
  const cliente = useQueryClient();
  const navegar = useNavigate();
  const { papel } = useSessao();
  const equipe = useEquipe();
  const [motivo, setMotivo] = useState("");
  const [remarcar, setRemarcar] = useState(false);
  const [data, setData] = useState(dataLocalISO(new Date(e.starts_at)));
  const [hora, setHora] = useState(horaBR(e.starts_at));
  const [erro, setErro] = useState<string | null>(null);
  const bloqueio = e.kind === "bloqueio";
  const duracaoMin = (new Date(e.ends_at).getTime() - new Date(e.starts_at).getTime()) / 60_000;

  const pronto = () => {
    cliente.invalidateQueries({ queryKey: ["agenda"] });
    aoFechar();
  };

  const status = useMutation({
    mutationFn: async (novo: StatusAgenda) =>
      ok(
        await api.POST("/agenda/agendamentos/{entry_id}/status", {
          params: { path: { entry_id: e.id } },
          body: { status: novo, motivo: motivo || null },
        }),
      ),
    onSuccess: pronto,
    onError: (x) => setErro(x.message),
  });

  const remarcacao = useMutation({
    mutationFn: async () => {
      const inicio = instante(data, hora);
      const fim = new Date(new Date(inicio).getTime() + duracaoMin * 60_000).toISOString();
      return ok(
        await api.PATCH("/agenda/agendamentos/{entry_id}", {
          params: { path: { entry_id: e.id } },
          body: { starts_at: inicio, ends_at: fim },
        }),
      );
    },
    onSuccess: pronto,
    onError: (x) => setErro(x.message),
  });

  // Dentista (ou admin) abre o atendimento a partir da agenda: a consulta vira "atendido".
  const atender = useMutation({
    mutationFn: async () =>
      ok(
        await api.POST("/prontuario/atendimentos", {
          body: { patient_id: e.patient_id!, appointment_id: e.id },
        }),
      ),
    onSuccess: (enc) => {
      cliente.invalidateQueries({ queryKey: ["agenda"] });
      navegar(`/pacientes/${enc.patient_id}?aba=atendimentos`);
    },
    onError: (x) => setErro(x.message),
  });

  const proximos = bloqueio ? (["cancelado"] as StatusAgenda[]) : PROXIMOS[e.status];

  return (
    <Modal titulo={bloqueio ? "Bloqueio de horário" : "Agendamento"} aberto aoFechar={aoFechar}>
      <div className="flex flex-col gap-3">
        {erro && <Aviso tom="perigo">{erro}</Aviso>}
        <div className="flex flex-wrap items-center gap-2">
          {!bloqueio && e.patient_id && (
            <Link to={`/pacientes/${e.patient_id}`} className="text-lg font-bold text-marca hover:underline">
              {e.patient_name}
            </Link>
          )}
          <Etiqueta tom={TOM_STATUS[e.status]}>{NOME_STATUS[e.status]}</Etiqueta>
        </div>
        <p className="text-sm">
          {dataHoraBR(e.starts_at)} – {horaBR(e.ends_at)} · {nomeMembro(equipe.data, e.dentist_id)}
        </p>
        {e.procedure && <p className="text-sm">Procedimento: {e.procedure}</p>}
        {e.notes && <p className="text-sm text-texto-suave">{e.notes}</p>}
        {e.status_reason && <p className="text-sm text-texto-suave">Motivo: {e.status_reason}</p>}

        {!bloqueio && e.patient_id && temPapel(papel, ...DENTISTAS) && ["agendado", "confirmado"].includes(e.status) && (
          <Botao onClick={() => atender.mutate()} carregando={atender.isPending}>
            Iniciar atendimento
          </Botao>
        )}

        {proximos.length > 0 && (
          <>
            <Campo rotulo="Motivo (para falta ou cancelamento)" value={motivo} onChange={(x) => setMotivo(x.target.value)} />
            <div className="flex flex-wrap gap-2">
              {proximos.map((s) => (
                <Botao
                  key={s}
                  variante={s === "cancelado" || s === "falta" ? "perigo" : "secundario"}
                  carregando={status.isPending && status.variables === s}
                  onClick={() => status.mutate(s)}
                >
                  {ACAO[s]}
                </Botao>
              ))}
              {!bloqueio && (
                <Botao variante="fantasma" onClick={() => setRemarcar(!remarcar)}>
                  Remarcar
                </Botao>
              )}
            </div>
          </>
        )}

        {remarcar && (
          <div className="flex flex-wrap items-end gap-2 rounded-lg border border-borda p-3">
            <Campo rotulo="Novo dia" type="date" value={data} onChange={(x) => setData(x.target.value)} />
            <Campo rotulo="Novo horário" type="time" step={300} value={hora} onChange={(x) => setHora(x.target.value)} />
            <Botao onClick={() => remarcacao.mutate()} carregando={remarcacao.isPending}>
              Salvar
            </Botao>
          </div>
        )}
      </div>
    </Modal>
  );
}
