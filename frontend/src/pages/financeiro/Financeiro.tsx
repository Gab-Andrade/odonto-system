import { useState } from "react";

import { GESTAO, temPapel, useSessao } from "../../auth/sessao";
import { Abas, Titulo } from "../../components/ui";
import ContasPagar from "./ContasPagar";
import Repasse from "./Repasse";

/** Financeiro da clínica: contas a pagar (gestão) e repasse aos dentistas. */
type Aba = "pagar" | "repasse";

export default function Financeiro() {
  const papel = useSessao((s) => s.papel);
  const gestao = temPapel(papel, ...GESTAO);
  const [aba, setAba] = useState<Aba>(gestao ? "pagar" : "repasse");
  return (
    <div>
      <Titulo>{gestao ? "Financeiro" : "Meu repasse"}</Titulo>
      {gestao && (
        <Abas
          abas={[
            { id: "pagar", rotulo: "Contas a pagar" },
            { id: "repasse", rotulo: "Repasse aos dentistas" },
          ]}
          atual={aba}
          aoMudar={setAba}
        />
      )}
      {aba === "pagar" && gestao && <ContasPagar />}
      {aba === "repasse" && <Repasse />}
    </div>
  );
}
