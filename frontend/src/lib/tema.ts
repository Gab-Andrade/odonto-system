import { useEffect, useState } from "react";

/**
 * Tema claro/escuro. "sistema" segue a preferência do aparelho. A escolha fica no
 * navegador (é uma preferência de cada aparelho) e o tema resolvido vai para
 * `<html data-tema="claro|escuro">`, que o CSS usa nos tokens e na variante `dark:`.
 * O index.html aplica o mesmo antes do React subir, para não piscar.
 */
export type Tema = "sistema" | "claro" | "escuro";

const CHAVE = "odonto.tema";
const escuroNoSistema = () => window.matchMedia("(prefers-color-scheme: dark)");

export function lerTema(): Tema {
  try {
    const t = localStorage.getItem(CHAVE);
    return t === "claro" || t === "escuro" ? t : "sistema";
  } catch {
    return "sistema";
  }
}

function aplicar(tema: Tema) {
  const resolvido = tema === "sistema" ? (escuroNoSistema().matches ? "escuro" : "claro") : tema;
  document.documentElement.dataset.tema = resolvido;
  document.documentElement.style.colorScheme = resolvido === "escuro" ? "dark" : "light";
}

export function useTema(): [Tema, (t: Tema) => void] {
  const [tema, setTema] = useState<Tema>(lerTema);

  useEffect(() => {
    aplicar(tema);
    if (tema !== "sistema") return;
    // Seguindo o sistema: acompanha se a pessoa trocar o tema do aparelho com o app aberto.
    const mq = escuroNoSistema();
    const mudou = () => aplicar("sistema");
    mq.addEventListener("change", mudou);
    return () => mq.removeEventListener("change", mudou);
  }, [tema]);

  function escolher(t: Tema) {
    try {
      if (t === "sistema") localStorage.removeItem(CHAVE);
      else localStorage.setItem(CHAVE, t);
    } catch {
      // sem armazenamento: vale só nesta aba
    }
    setTema(t);
  }

  return [tema, escolher];
}
