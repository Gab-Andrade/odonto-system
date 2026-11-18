import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api, ok } from "../api/client";
import { useSessao } from "../auth/sessao";
import { Cartao, Carregando, ErroCarga, Etiqueta, Titulo, Vazio } from "../components/ui";
import { horaBR, hojeISO, inicioDoDia, somarDias } from "../lib/datas";
import { NOME_STATUS, TOM_STATUS } from "./agenda/status";

export default function Inicio() {
  const { usuario, papel } = useSessao();
  const hoje = hojeISO();

  const agenda = useQuery({
    queryKey: ["agenda", "hoje", hoje],
    queryFn: async () =>
      ok(
        await api.GET("/agenda/agendamentos", {
          params: {
            query: {
              inicio: inicioDoDia(hoje),
              fim: inicioDoDia(somarDias(hoje, 1)),
              incluir_cancelados: false,
            },
          },
        }),
      ),
  });

  const alertas = useQuery({
    queryKey: ["alertas", "resumo"],
    queryFn: async () => ok(await api.GET("/inteligencia/alertas/resumo")),
  });

  const consultas = (agenda.data ?? []).filter((e) => e.kind === "consulta");

  return (
    <div className="flex flex-col gap-4">
      <Titulo>Olá{usuario ? `, ${usuario.nome.split(" ")[0]}` : ""}!</Titulo>

      <div className="grid gap-4 md:grid-cols-3">
        <Cartao titulo="Agenda de hoje" className="md:col-span-2" acoes={<Link className="text-sm font-semibold text-marca" to="/agenda">Abrir agenda</Link>}>
          {agenda.isLoading && <Carregando />}
          {agenda.error && <ErroCarga erro={agenda.error} />}
          {agenda.data && consultas.length === 0 && <Vazio>Nenhuma consulta hoje.</Vazio>}
          <ul className="divide-y divide-borda">
            {consultas.map((c) => (
              <li key={c.id} className="flex min-h-12 items-center gap-3 py-2">
                <span className="w-14 font-mono text-sm font-semibold">{horaBR(c.starts_at)}</span>
                <div className="min-w-0 flex-1">
                  {c.patient_id ? (
                    <Link to={`/pacientes/${c.patient_id}`} className="font-medium hover:underline">
                      {c.patient_name}
                    </Link>
                  ) : (
                    <span>{c.patient_name}</span>
                  )}
                  {c.procedure && <p className="truncate text-xs text-texto-suave">{c.procedure}</p>}
                </div>
                <Etiqueta tom={TOM_STATUS[c.status]}>{NOME_STATUS[c.status]}</Etiqueta>
              </li>
            ))}
          </ul>
        </Cartao>

        <Cartao titulo="Alertas" acoes={<Link className="text-sm font-semibold text-marca" to="/alertas">Ver todos</Link>}>
          {alertas.isLoading && <Carregando />}
          {alertas.error && <ErroCarga erro={alertas.error} />}
          {alertas.data && (
            <div>
              <p className="text-4xl font-bold">{alertas.data.total}</p>
              <p className="text-sm text-texto-suave">
                {alertas.data.total === 0 ? "Nada pendente." : "alertas pedem atenção."}
              </p>
            </div>
          )}
        </Cartao>
      </div>

      {papel && ["admin", "gestor"].includes(papel) && (
        <Aviso />
      )}
    </div>
  );
}

function Aviso() {
  return (
    <Cartao>
      <p className="text-sm text-texto-suave">
        Indicadores do mês, equipe, metas e tendências estão em{" "}
        <Link to="/gestao" className="font-semibold text-marca">Gestão</Link>.
      </p>
    </Cartao>
  );
}
