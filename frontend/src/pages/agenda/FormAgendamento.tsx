import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, ok } from "../../api/client";
import { useSessao } from "../../auth/sessao";
import BuscaPaciente, { type PacienteEscolhido } from "../../components/BuscaPaciente";
import Modal from "../../components/Modal";
import { AreaTexto, Aviso, Botao, Campo, Selecao } from "../../components/ui";
import { instante } from "../../lib/datas";
import { useDentistas } from "../../lib/equipe";

const DURACOES = [15, 30, 45, 60, 90, 120];

/** Novo agendamento ou bloqueio de horário. */
export default function FormAgendamento({
  dia,
  inicial,
  pacienteInicial,
  aoFechar,
}: {
  dia: string;
  inicial: { inicio?: string; dentista?: string; bloqueio?: boolean };
  pacienteInicial?: string | null;
  aoFechar: () => void;
}) {
  const cliente = useQueryClient();
  const { papel, usuario } = useSessao();
  const dentistas = useDentistas();
  const cadeiras = useQuery({
    queryKey: ["cadeiras"],
    queryFn: async () => ok(await api.GET("/agenda/cadeiras")),
  });
  const pacienteUrl = useQuery({
    enabled: Boolean(pacienteInicial),
    queryKey: ["paciente", pacienteInicial],
    queryFn: async () =>
      ok(await api.GET("/pacientes/{patient_id}", { params: { path: { patient_id: pacienteInicial! } } })),
  });

  const bloqueio = Boolean(inicial.bloqueio);
  const [paciente, setPaciente] = useState<PacienteEscolhido | null>(null);
  const [dentista, setDentista] = useState(
    inicial.dentista ?? (papel === "dentista" && usuario ? usuario.id : ""),
  );
  const [cadeira, setCadeira] = useState("");
  const [data, setData] = useState(inicial.inicio?.slice(0, 10) ?? dia);
  const [hora, setHora] = useState(inicial.inicio?.slice(11, 16) ?? "09:00");
  const [duracao, setDuracao] = useState(30);
  const [horaFim, setHoraFim] = useState("18:00");
  const [procedimento, setProcedimento] = useState("");
  const [obs, setObs] = useState("");
  const [erro, setErro] = useState<string | null>(null);

  const escolhido =
    paciente ??
    (pacienteUrl.data ? { id: pacienteUrl.data.id, nome: pacienteUrl.data.full_name } : null);

  const salvar = useMutation({
    mutationFn: async () => {
      const inicio = instante(data, hora);
      if (bloqueio) {
        return ok(
          await api.POST("/agenda/bloqueios", {
            body: {
              dentist_id: dentista || null,
              chair_id: cadeira || null,
              starts_at: inicio,
              ends_at: instante(data, horaFim),
              notes: obs || null,
            },
          }),
        );
      }
      if (!escolhido) throw new Error("Escolha o paciente.");
      if (!dentista) throw new Error("Escolha o dentista.");
      const fim = new Date(new Date(inicio).getTime() + duracao * 60_000).toISOString();
      return ok(
        await api.POST("/agenda/agendamentos", {
          body: {
            patient_id: escolhido.id,
            dentist_id: dentista,
            chair_id: cadeira || null,
            starts_at: inicio,
            ends_at: fim,
            procedure: procedimento || null,
            notes: obs || null,
          },
        }),
      );
    },
    onSuccess: () => {
      cliente.invalidateQueries({ queryKey: ["agenda"] });
      aoFechar();
    },
    onError: (e) => setErro(e.message),
  });

  function enviar(ev: FormEvent) {
    ev.preventDefault();
    setErro(null);
    salvar.mutate();
  }

  return (
    <Modal titulo={bloqueio ? "Bloquear horário" : "Novo agendamento"} aberto aoFechar={aoFechar}>
      <form onSubmit={enviar} className="flex flex-col gap-3">
        {erro && <Aviso tom="perigo">{erro}</Aviso>}
        {!bloqueio && <BuscaPaciente valor={escolhido} aoEscolher={setPaciente} />}
        <div className="grid gap-3 sm:grid-cols-2">
          <Selecao rotulo={bloqueio ? "Dentista (opcional)" : "Dentista"} value={dentista} onChange={(e) => setDentista(e.target.value)}>
            <option value="">{bloqueio ? "— nenhum —" : "Escolha"}</option>
            {dentistas.data?.map((d) => (
              <option key={d.user_id} value={d.user_id}>
                {d.full_name}
              </option>
            ))}
          </Selecao>
          <Selecao rotulo="Cadeira (opcional)" value={cadeira} onChange={(e) => setCadeira(e.target.value)}>
            <option value="">— nenhuma —</option>
            {cadeiras.data
              ?.filter((c) => c.active)
              .map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
          </Selecao>
          <Campo rotulo="Dia" type="date" required value={data} onChange={(e) => setData(e.target.value)} />
          <Campo rotulo="Início" type="time" step={300} required value={hora} onChange={(e) => setHora(e.target.value)} />
          {bloqueio ? (
            <Campo rotulo="Fim" type="time" step={300} required value={horaFim} onChange={(e) => setHoraFim(e.target.value)} />
          ) : (
            <Selecao rotulo="Duração" value={duracao} onChange={(e) => setDuracao(Number(e.target.value))}>
              {DURACOES.map((d) => (
                <option key={d} value={d}>
                  {d} min
                </option>
              ))}
            </Selecao>
          )}
          {!bloqueio && (
            <Campo rotulo="Procedimento" placeholder="Avaliação, limpeza…" value={procedimento} onChange={(e) => setProcedimento(e.target.value)} />
          )}
        </div>
        <AreaTexto rotulo={bloqueio ? "Motivo" : "Observações"} value={obs} onChange={(e) => setObs(e.target.value)} />
        <div className="flex justify-end gap-2">
          <Botao variante="secundario" onClick={aoFechar}>
            Cancelar
          </Botao>
          <Botao type="submit" carregando={salvar.isPending}>
            Salvar
          </Botao>
        </div>
      </form>
    </Modal>
  );
}
