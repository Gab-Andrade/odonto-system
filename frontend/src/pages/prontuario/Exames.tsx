import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, baixar, mensagemErro, ok, API_URL, type Schemas } from "../../api/client";
import { temPapel, useSessao } from "../../auth/sessao";
import { Aviso, Botao, Campo, Cartao, Carregando, ErroCarga, Etiqueta, Selecao, Vazio } from "../../components/ui";
import { dataBR } from "../../lib/datas";

type Exame = Schemas["ExamOut"];

const TIPOS: Record<string, string> = {
  periapical: "Periapical",
  interproximal: "Interproximal (bite-wing)",
  panoramica: "Panorâmica",
  tomografia: "Tomografia",
  outro: "Outro",
};

/** Raio-X do paciente: arquivos DICOM com metadados. Sem visualizador por enquanto. */
export default function Exames({ pacienteId }: { pacienteId: string }) {
  const { papel, token } = useSessao();
  const cliente = useQueryClient();
  const podeEnviar = temPapel(papel, "admin", "dentista", "asb");
  const podeInvalidar = temPapel(papel, "admin", "dentista");
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [tipo, setTipo] = useState("");
  const [dentes, setDentes] = useState("");
  const [obs, setObs] = useState("");
  const [invalidados, setInvalidados] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const exames = useQuery({
    queryKey: ["exames", pacienteId, invalidados],
    queryFn: async () =>
      ok(
        await api.GET("/imagens/pacientes/{patient_id}/exames", {
          params: { path: { patient_id: pacienteId }, query: { incluir_invalidados: invalidados } },
        }),
      ),
  });

  // Envio multipart direto (o cliente tipado não monta FormData com arquivo).
  const enviar = useMutation({
    mutationFn: async () => {
      if (!arquivo) throw new Error("Escolha o arquivo .dcm.");
      const corpo = new FormData();
      corpo.append("arquivo", arquivo);
      if (tipo) corpo.append("tipo", tipo);
      if (dentes) corpo.append("dentes", dentes);
      if (obs) corpo.append("observacao", obs);
      const resp = await fetch(`${API_URL}/imagens/pacientes/${pacienteId}/exames`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: corpo,
      });
      const dados = await resp.json().catch(() => null);
      if (!resp.ok) throw new Error(mensagemErro(dados, `Erro ${resp.status} no envio.`));
      return dados as Schemas["ExamDetail"];
    },
    onSuccess: (e) => {
      setArquivo(null);
      setDentes("");
      setObs("");
      setMsg(`Exame anexado: ${TIPOS[e.kind]}${e.dicom_patient_name ? ` · nome no arquivo: ${e.dicom_patient_name}` : ""}.`);
      cliente.invalidateQueries({ queryKey: ["exames", pacienteId] });
    },
  });

  function submeter(ev: FormEvent) {
    ev.preventDefault();
    setMsg(null);
    enviar.mutate();
  }

  return (
    <div className="flex flex-col gap-4">
      {podeEnviar && (
        <Cartao titulo="Anexar raio-X (DICOM)">
          <form onSubmit={submeter} className="flex flex-col gap-3">
            {enviar.error && <Aviso tom="perigo">{enviar.error.message}</Aviso>}
            {msg && <Aviso tom="sucesso">{msg}</Aviso>}
            <input
              type="file"
              accept=".dcm,application/dicom"
              onChange={(e) => setArquivo(e.target.files?.[0] ?? null)}
              className="min-h-11 text-sm file:mr-3 file:min-h-11 file:rounded-lg file:border-0 file:bg-marca-suave file:px-4 file:font-semibold file:text-marca"
            />
            <div className="grid gap-3 sm:grid-cols-3">
              <Selecao rotulo="Tipo" value={tipo} onChange={(e) => setTipo(e.target.value)}>
                <option value="">Pela modalidade do arquivo</option>
                {Object.entries(TIPOS).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </Selecao>
              <Campo rotulo="Dentes" placeholder="36, 37" value={dentes} onChange={(e) => setDentes(e.target.value)} />
              <Campo rotulo="Observação" value={obs} onChange={(e) => setObs(e.target.value)} />
            </div>
            <Botao type="submit" className="self-start" carregando={enviar.isPending} disabled={!arquivo}>
              Enviar
            </Botao>
          </form>
        </Cartao>
      )}

      <Cartao
        titulo="Exames"
        acoes={
          <label className="flex min-h-11 items-center gap-2 text-sm">
            <input type="checkbox" className="size-5" checked={invalidados} onChange={(e) => setInvalidados(e.target.checked)} />
            Mostrar invalidados
          </label>
        }
      >
        {exames.isLoading && <Carregando />}
        {exames.error && <ErroCarga erro={exames.error} />}
        {exames.data && exames.data.length === 0 && <Vazio>Nenhum exame anexado.</Vazio>}
        <ul className="divide-y divide-borda">
          {exames.data?.map((e) => (
            <ExameLinha key={e.id} exame={e} podeInvalidar={podeInvalidar} pacienteId={pacienteId} />
          ))}
        </ul>
        <p className="mt-2 text-xs text-texto-suave">
          Para ver a imagem, baixe o .dcm e abra num visualizador DICOM (ex.: o do próprio
          sensor ou um gratuito como o Weasis). O visualizador no navegador entra depois.
        </p>
      </Cartao>
    </div>
  );
}

function ExameLinha({ exame: e, podeInvalidar, pacienteId }: { exame: Exame; podeInvalidar: boolean; pacienteId: string }) {
  const cliente = useQueryClient();
  const [erro, setErro] = useState<string | null>(null);
  const invalidar = useMutation({
    mutationFn: async (motivo: string) =>
      ok(
        await api.POST("/imagens/exames/{exam_id}/invalidar", {
          params: { path: { exam_id: e.id } },
          body: { reason: motivo },
        }),
      ),
    onSuccess: () => cliente.invalidateQueries({ queryKey: ["exames", pacienteId] }),
    onError: (x) => setErro(x.message),
  });

  async function download() {
    try {
      const blob = await baixar(`/imagens/exames/${e.id}/arquivo`);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = e.file_name || `exame-${e.id}.dcm`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (x) {
      setErro(mensagemErro(x));
    }
  }

  return (
    <li className="flex flex-wrap items-center gap-3 py-3">
      <div className="min-w-0 flex-1">
        <p className="font-medium">
          {TIPOS[e.kind]} · {dataBR(e.exam_date)}
          {e.teeth && e.teeth.length > 0 && <span className="text-texto-suave"> · dentes {e.teeth.join(", ")}</span>}
          {e.invalidated_at && (
            <span className="ml-2">
              <Etiqueta tom="alerta">Invalidado</Etiqueta>
            </span>
          )}
        </p>
        <p className="text-xs text-texto-suave">
          {[e.modality, e.study_description, e.manufacturer, e.rows && `${e.columns}×${e.rows}px`, `${Math.ceil(e.size_bytes / 1024)} KB`]
            .filter(Boolean)
            .join(" · ")}
        </p>
        {e.dicom_patient_name && <p className="text-xs text-texto-suave">Nome no arquivo: {e.dicom_patient_name}</p>}
        {e.invalidation_reason && <p className="text-xs text-alerta">Motivo: {e.invalidation_reason}</p>}
        {erro && <p className="text-xs text-perigo">{erro}</p>}
      </div>
      <Botao variante="secundario" onClick={download}>
        Baixar .dcm
      </Botao>
      {podeInvalidar && !e.invalidated_at && (
        <Botao
          variante="fantasma"
          onClick={() => {
            const motivo = window.prompt("Motivo da invalidação (ex.: paciente errado):");
            if (motivo && motivo.trim().length >= 3) invalidar.mutate(motivo.trim());
          }}
        >
          Invalidar
        </Botao>
      )}
    </li>
  );
}
