import { useState } from "react";

import { Abas, Titulo } from "../../components/ui";
import ModelosAnamnese from "./ModelosAnamnese";

/** Configurações da clínica (admin e gestor). */
type Aba = "anamnese";

export default function Configuracoes() {
  const [aba, setAba] = useState<Aba>("anamnese");
  return (
    <div>
      <Titulo>Configurações</Titulo>
      <Abas abas={[{ id: "anamnese", rotulo: "Modelos de anamnese" }]} atual={aba} aoMudar={setAba} />
      {aba === "anamnese" && <ModelosAnamnese />}
    </div>
  );
}
