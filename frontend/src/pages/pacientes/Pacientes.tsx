import { useQuery } from "@tanstack/react-query";
import { useDeferredValue, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api, ok } from "../../api/client";
import { Botao, Campo, Cartao, Carregando, ErroCarga, Etiqueta, Titulo, Vazio } from "../../components/ui";
import { dataBR, idade } from "../../lib/datas";
import FormPaciente from "./FormPaciente";

export default function Pacientes() {
  const [busca, setBusca] = useState("");
  const [inativos, setInativos] = useState(false);
  const [novo, setNovo] = useState(false);
  const termo = useDeferredValue(busca.trim());
  const navegar = useNavigate();

  const lista = useQuery({
    queryKey: ["pacientes", "busca", termo, inativos],
    queryFn: async () =>
      ok(
        await api.GET("/pacientes", {
          params: { query: { busca: termo || undefined, incluir_inativos: inativos, limit: 50 } },
        }),
      ),
  });

  return (
    <div>
      <Titulo acoes={<Botao onClick={() => setNovo(true)}>+ Novo paciente</Botao>}>Pacientes</Titulo>
      <Cartao>
        <div className="mb-3 flex flex-wrap items-end gap-3">
          <Campo
            rotulo="Buscar"
            placeholder="Nome, CPF ou telefone"
            className="min-w-60 flex-1"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            autoFocus
          />
          <label className="flex min-h-11 items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="size-5"
              checked={inativos}
              onChange={(e) => setInativos(e.target.checked)}
            />
            Incluir inativos
          </label>
        </div>
        {lista.isLoading && <Carregando />}
        {lista.error && <ErroCarga erro={lista.error} />}
        {lista.data && lista.data.length === 0 && <Vazio>Nenhum paciente encontrado.</Vazio>}
        <ul className="divide-y divide-borda">
          {lista.data?.map((p) => {
            const anos = idade(p.birth_date);
            return (
              <li key={p.id}>
                <Link
                  to={`/pacientes/${p.id}`}
                  className="flex min-h-14 items-center gap-3 rounded-lg px-2 py-2 hover:bg-fundo"
                >
                  <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-marca-suave font-bold text-marca">
                    {(p.social_name ?? p.full_name).charAt(0)}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">
                      {p.social_name ?? p.full_name}
                      {p.social_name && (
                        <span className="ml-2 text-xs text-texto-suave">({p.full_name})</span>
                      )}
                    </p>
                    <p className="text-xs text-texto-suave">
                      {anos !== null ? `${anos} anos · ${dataBR(p.birth_date)}` : "Sem data de nascimento"}
                      {p.cpf_mascarado && ` · CPF ${p.cpf_mascarado}`} · {p.phone}
                    </p>
                  </div>
                  {!p.active && <Etiqueta tom="alerta">Inativo</Etiqueta>}
                </Link>
              </li>
            );
          })}
        </ul>
      </Cartao>
      <FormPaciente
        aberto={novo}
        aoFechar={() => setNovo(false)}
        aoSalvar={(id) => navegar(`/pacientes/${id}`)}
      />
    </div>
  );
}
