import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api, ok } from "../../api/client";
import { Cartao, Carregando, ErroCarga, Etiqueta, Vazio } from "../../components/ui";
import { dataHoraBR } from "../../lib/datas";
import { nomeMembro, useEquipe } from "../../lib/equipe";
import { NOME_STATUS, TOM_STATUS } from "../agenda/status";

export default function ConsultasPaciente({ pacienteId }: { pacienteId: string }) {
  const equipe = useEquipe();
  const consultas = useQuery({
    queryKey: ["agenda", "paciente", pacienteId],
    queryFn: async () =>
      ok(await api.GET("/agenda/agendamentos", { params: { query: { paciente_id: pacienteId } } })),
  });
  const lista = [...(consultas.data ?? [])].sort((a, b) => b.starts_at.localeCompare(a.starts_at));

  return (
    <Cartao
      titulo="Consultas do paciente"
      acoes={
        <Link className="text-sm font-semibold text-marca" to={`/agenda?paciente=${pacienteId}`}>
          Agendar
        </Link>
      }
    >
      {consultas.isLoading && <Carregando />}
      {consultas.error && <ErroCarga erro={consultas.error} />}
      {consultas.data && lista.length === 0 && <Vazio>Nenhuma consulta.</Vazio>}
      <ul className="divide-y divide-borda">
        {lista.map((c) => (
          <li key={c.id} className="flex flex-wrap items-center gap-3 py-2">
            <span className="w-36 text-sm font-medium">{dataHoraBR(c.starts_at)}</span>
            <span className="min-w-0 flex-1 text-sm">
              {c.procedure ?? "Consulta"} · {nomeMembro(equipe.data, c.dentist_id)}
            </span>
            <Etiqueta tom={TOM_STATUS[c.status]}>{NOME_STATUS[c.status]}</Etiqueta>
          </li>
        ))}
      </ul>
    </Cartao>
  );
}
