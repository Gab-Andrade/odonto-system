import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, ok, type Schemas } from "../../api/client";
import { AreaTexto, Aviso, Botao } from "../../components/ui";
import { dataHoraBR } from "../../lib/datas";
import { nomeMembro, useEquipe } from "../../lib/equipe";

type Nota = Schemas["ToothNoteOut"];

/**
 * Anotações livres de um dente. Como no prontuário, não se edita nem apaga: para corrigir,
 * escreve-se uma nova (fica o histórico com autor e data).
 */
export default function AnotacoesDente({
  pacienteId,
  dente,
  notas,
  podeEscrever,
}: {
  pacienteId: string;
  dente: number;
  notas: Nota[];
  podeEscrever: boolean;
}) {
  const cliente = useQueryClient();
  const equipe = useEquipe();
  const [texto, setTexto] = useState("");
  const salvar = useMutation({
    mutationFn: async () =>
      ok(
        await api.POST("/odontograma/pacientes/{patient_id}/anotacoes", {
          params: { path: { patient_id: pacienteId } },
          body: { tooth: dente, text: texto },
        }),
      ),
    onSuccess: () => {
      setTexto("");
      cliente.invalidateQueries({ queryKey: ["odontograma", pacienteId] });
    },
  });

  return (
    <div className="mt-4 border-t border-borda pt-3">
      <h3 className="mb-2 text-sm font-semibold">Anotações</h3>
      {notas.length === 0 && <p className="text-sm text-texto-suave">Nenhuma anotação neste dente.</p>}
      <ul className="flex flex-col gap-2">
        {notas.map((n) => (
          <li key={n.id} className="rounded-lg bg-marca-suave/50 p-2 text-sm">
            <p className="whitespace-pre-wrap">{n.text}</p>
            <p className="mt-1 text-xs text-texto-suave">
              {dataHoraBR(n.created_at)} · {nomeMembro(equipe.data, n.created_by)}
            </p>
          </li>
        ))}
      </ul>
      {podeEscrever && (
        <form
          className="mt-3 flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (texto.trim()) salvar.mutate();
          }}
        >
          <AreaTexto
            rotulo={`Nova anotação no dente ${dente}`}
            value={texto}
            maxLength={2000}
            onChange={(e) => setTexto(e.target.value)}
            placeholder="Ex.: sensibilidade ao frio, acompanhar na próxima consulta"
          />
          {salvar.error && <Aviso tom="perigo">{salvar.error.message}</Aviso>}
          <div className="flex items-center gap-3">
            <Botao type="submit" carregando={salvar.isPending} disabled={!texto.trim()}>
              Salvar anotação
            </Botao>
            <span className="text-xs text-texto-suave">Não dá para editar depois: para corrigir, escreva outra.</span>
          </div>
        </form>
      )}
    </div>
  );
}
