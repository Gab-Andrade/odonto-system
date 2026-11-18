import { Link } from "react-router-dom";

import { Vazio } from "../components/ui";

export default function NaoEncontrado() {
  return (
    <Vazio>
      Página não encontrada. <Link to="/" className="font-semibold text-marca">Voltar ao início</Link>
    </Vazio>
  );
}
