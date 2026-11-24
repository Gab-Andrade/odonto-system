import { useState } from "react";

import { useSessao } from "../../auth/sessao";
import { Abas, Titulo } from "../../components/ui";
import Equipe from "./Equipe";
import ModelosAnamnese from "./ModelosAnamnese";

/** Configurações da clínica (admin e gestor; a equipe é só do administrador). */
type Aba = "anamnese" | "equipe";

export default function Configuracoes() {
  const admin = useSessao((s) => s.papel === "admin");
  const [aba, setAba] = useState<Aba>(admin ? "equipe" : "anamnese");
  const abas: { id: Aba; rotulo: string }[] = [
    ...(admin ? [{ id: "equipe" as const, rotulo: "Equipe" }] : []),
    { id: "anamnese", rotulo: "Modelos de anamnese" },
  ];
  return (
    <div>
      <Titulo>Configurações</Titulo>
      <Abas abas={abas} atual={aba} aoMudar={setAba} />
      {aba === "equipe" && admin && <Equipe />}
      {aba === "anamnese" && <ModelosAnamnese />}
    </div>
  );
}
