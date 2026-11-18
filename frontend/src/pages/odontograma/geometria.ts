/** Geometria do odontograma 2D (numeração FDI). */

export const LADO = 44; // lado do quadrado do dente (px no viewBox)

/** Superiores: quadrantes 1, 2, 5 e 6. */
export function superior(fdi: number): boolean {
  return [1, 2, 5, 6].includes(Math.floor(fdi / 10));
}

/** Lado direito do paciente (esquerda de quem olha): quadrantes 1, 4, 5 e 8. */
export function ladoDireito(fdi: number): boolean {
  return [1, 4, 5, 8].includes(Math.floor(fdi / 10));
}
