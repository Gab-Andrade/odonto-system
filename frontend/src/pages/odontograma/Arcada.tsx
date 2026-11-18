import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, ok, type Schemas } from "../../api/client";
import Modal from "../../components/Modal";
import { AreaTexto, Aviso, Botao, Selecao } from "../../components/ui";

const SISOS = [18, 28, 38, 48] as const;

/** Registra a composição da arcada (dentição e terceiros molares). */
export default function Arcada({
  paciente,
  atual,
  aoFechar,
}: {
  paciente: Schemas["PatientOut"];
  atual: Schemas["ArchOut"];
  aoFechar: () => void;
}) {
  const cliente = useQueryClient();
  const [denticao, setDenticao] = useState<Schemas["Dentition"]>(atual.dentition);
  const [sisos, setSisos] = useState<number[]>(atual.third_molars);
  const [obs, setObs] = useState("");
  const salvar = useMutation({
    mutationFn: async () =>
      ok(
        await api.POST("/odontograma/pacientes/{patient_id}/arcada", {
          params: { path: { patient_id: paciente.id } },
          body: {
            dentition: denticao,
            third_molars: denticao === "permanente" ? (sisos as (18 | 28 | 38 | 48)[]) : null,
            notes: obs || null,
          },
        }),
      ),
    onSuccess: () => {
      cliente.invalidateQueries({ queryKey: ["odontograma", paciente.id] });
      aoFechar();
    },
  });

  return (
    <Modal titulo="Arcada do paciente" aberto aoFechar={aoFechar}>
      <div className="flex flex-col gap-3">
        {salvar.error && <Aviso tom="perigo">{salvar.error.message}</Aviso>}
        <p className="text-sm text-texto-suave">
          Hoje: {atual.dentition}, {atual.teeth.length} dentes (
          {atual.source === "padrao" ? "sugerida pela idade" : "registrada"}). Dente perdido continua
          sendo marcado como "Ausente" no odontograma.
        </p>
        <Selecao rotulo="Dentição" value={denticao} onChange={(e) => setDenticao(e.target.value as Schemas["Dentition"])}>
          <option value="permanente">Permanente</option>
          <option value="mista">Mista</option>
          <option value="decidua">Decídua</option>
        </Selecao>
        {denticao === "permanente" && (
          <fieldset className="flex flex-wrap gap-3">
            <legend className="mb-1 text-sm font-medium text-texto-suave">Terceiros molares (sisos)</legend>
            {SISOS.map((s) => (
              <label key={s} className="flex min-h-11 items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  className="size-5"
                  checked={sisos.includes(s)}
                  onChange={(e) => setSisos(e.target.checked ? [...sisos, s] : sisos.filter((x) => x !== s))}
                />
                {s}
              </label>
            ))}
          </fieldset>
        )}
        <AreaTexto rotulo="Observação" value={obs} onChange={(e) => setObs(e.target.value)} />
        <div className="flex justify-end gap-2">
          <Botao variante="secundario" onClick={aoFechar}>
            Cancelar
          </Botao>
          <Botao onClick={() => salvar.mutate()} carregando={salvar.isPending}>
            Salvar arcada
          </Botao>
        </div>
      </div>
    </Modal>
  );
}
