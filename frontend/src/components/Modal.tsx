import { useEffect, type ReactNode } from "react";

/** Janela sobreposta simples; fecha no Esc e no fundo. */
export default function Modal({
  titulo,
  aberto,
  aoFechar,
  children,
  largura = "max-w-lg",
}: {
  titulo: string;
  aberto: boolean;
  aoFechar: () => void;
  children: ReactNode;
  largura?: string;
}) {
  useEffect(() => {
    if (!aberto) return;
    const tecla = (e: KeyboardEvent) => e.key === "Escape" && aoFechar();
    window.addEventListener("keydown", tecla);
    return () => window.removeEventListener("keydown", tecla);
  }, [aberto, aoFechar]);

  if (!aberto) return null;
  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center bg-black/50 p-0 sm:items-center sm:p-4">
      <button type="button" aria-label="Fechar" className="absolute inset-0" onClick={aoFechar} />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={titulo}
        className={`relative max-h-[92vh] w-full ${largura} overflow-y-auto rounded-t-2xl bg-painel p-5 shadow-xl sm:rounded-2xl`}
      >
        <div className="mb-4 flex items-center justify-between gap-2">
          <h2 className="text-lg font-bold">{titulo}</h2>
          <button
            type="button"
            onClick={aoFechar}
            aria-label="Fechar"
            className="flex size-11 items-center justify-center rounded-lg text-xl hover:bg-fundo"
          >
            ×
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
