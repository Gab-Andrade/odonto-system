import { OrbitControls } from "@react-three/drei";
import { Canvas, type ThreeEvent } from "@react-three/fiber";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

import { baixar, type Schemas } from "../../api/client";
import { Cartao, Carregando, ErroCarga } from "../../components/ui";
import type { DenteVis } from "./Dente2D";

const COR_NATURAL = "#f1ece1";
const COR_RAIZ = "#e6d9bf";
const COR_SELECAO = new THREE.Color("#14b8a6");

/** O GLB da arcada não tem dado de paciente: pode ficar em cache entre pacientes. */
async function carregarArcada(url: string): Promise<THREE.Group> {
  const blob = await baixar(url);
  const gltf = await new GLTFLoader().parseAsync(await blob.arrayBuffer(), "");
  return gltf.scene;
}

/** Nó "16_O" → dente 16, face O; "16_raiz" → dente 16, sem face; "dente_16" → dente 16. */
function lerNo(nome: string): { dente: number; face: string | null } | null {
  let m = /^dente_(\d{2})$/.exec(nome);
  if (m) return { dente: Number(m[1]), face: null };
  m = /^(\d{2})_([MDOVL]|raiz)$/.exec(nome);
  if (m) return { dente: Number(m[1]), face: m[2] === "raiz" ? null : m[2] };
  return null;
}

export default function Odontograma3D({
  vis,
  selecionado,
  aoTocar,
  compacto = false,
}: {
  vis: Schemas["VisualizationOut"];
  selecionado: number | null;
  aoTocar: (d: DenteVis, face: string | null) => void;
  /** Ao lado da boca 2D, só para ver: mais baixo. */
  compacto?: boolean;
}) {
  const [raizes, setRaizes] = useState(false);
  const [arcadas, setArcadas] = useState<"ambas" | "superior" | "inferior">("ambas");
  const modelo = useQuery({
    queryKey: ["glb", vis.arch_model_url],
    queryFn: () => carregarArcada(vis.arch_model_url),
    staleTime: Infinity,
  });

  // Uma cópia da cena por visualização: as cores são do paciente, o modelo é genérico.
  const cena = useMemo(() => modelo.data?.clone(true) ?? null, [modelo.data]);
  const porDente = useMemo(() => new Map(vis.teeth.map((d) => [d.tooth, d])), [vis.teeth]);

  useEffect(() => {
    if (!cena) return;
    cena.traverse((obj) => {
      const info = lerNo(obj.name);
      if (!info) return;
      const d = porDente.get(info.dente);
      const sup = [1, 2, 5, 6].includes(Math.floor(info.dente / 10));
      if (obj.name.startsWith("dente_")) {
        obj.visible = !(d?.hidden ?? false) && (arcadas === "ambas" || (arcadas === "superior") === sup);
        return;
      }
      if (!(obj instanceof THREE.Mesh)) return;
      const raiz = obj.name.endsWith("_raiz");
      if (raiz) obj.visible = raizes;
      const face = info.face ? Object.values(d?.faces ?? {}).find((f) => f.face === info.face) : null;
      const cor = raiz ? COR_RAIZ : (face?.color ?? d?.color ?? COR_NATURAL);
      const material = new THREE.MeshStandardMaterial({ color: cor, roughness: 0.45, metalness: 0.05 });
      if (info.dente === selecionado) {
        material.emissive = COR_SELECAO;
        material.emissiveIntensity = 0.25;
      }
      (obj.material as THREE.Material | undefined)?.dispose?.();
      obj.material = material;
    });
  }, [cena, porDente, selecionado, raizes, arcadas]);

  function clique(ev: ThreeEvent<MouseEvent>) {
    ev.stopPropagation();
    const info = lerNo(ev.object.name);
    const d = info && porDente.get(info.dente);
    if (d) aoTocar(d, info.face);
  }

  return (
    <Cartao>
      <div className="mb-3 flex flex-wrap items-center gap-4 text-sm">
        <label className="flex min-h-11 items-center gap-2">
          <input type="checkbox" className="size-5" checked={raizes} onChange={(e) => setRaizes(e.target.checked)} />
          Mostrar raízes
        </label>
        <div className="flex rounded-lg border border-borda p-1">
          {(["ambas", "superior", "inferior"] as const).map((a) => (
            <button
              key={a}
              type="button"
              onClick={() => setArcadas(a)}
              className={`min-h-9 rounded-md px-3 font-semibold capitalize ${arcadas === a ? "bg-marca-suave text-marca" : ""}`}
            >
              {a}
            </button>
          ))}
        </div>
        <span className="text-xs text-texto-suave">
          Arraste para girar, pinça/roda para aproximar, {compacto ? "toque num dente para ver." : "toque numa face para marcar."}
        </span>
      </div>
      {modelo.isLoading && <Carregando texto="Carregando o modelo 3D…" />}
      {modelo.error && <ErroCarga erro={modelo.error} />}
      {cena && (
        <div className={`${compacto ? "h-[26rem]" : "h-[60vh] min-h-80"} w-full touch-none overflow-hidden rounded-lg bg-gradient-to-b from-slate-100 to-slate-300 dark:from-slate-800 dark:to-slate-950`}>
          <Canvas camera={{ position: [0, 8, 95], fov: 35, near: 1, far: 1000 }} dpr={[1, 2]}>
            <ambientLight intensity={0.6} />
            <directionalLight position={[30, 60, 80]} intensity={1.6} />
            <directionalLight position={[-40, -30, 40]} intensity={0.5} />
            <primitive object={cena} onClick={clique} />
            <OrbitControls makeDefault enablePan={false} minDistance={40} maxDistance={220} />
          </Canvas>
        </div>
      )}
    </Cartao>
  );
}
