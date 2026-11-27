"""
SIMULACIÓN DE VALIDACIÓN (no necesita cámara)

Dibuja frutas artificiales de tamaño CONOCIDO y compara lo que mide el
programa (sumas de Riemann sobre píxeles) con las fórmulas exactas:

  Círculo de radio R          A = πR²      Esfera:            V = (4/3)πR³
  Elipse de semiejes a, b     A = πab      Elipsoide (giro en el eje a): V = (4/3)πab²

Así se demuestra que la integral numérica converge al valor exacto.
"""
import os

import cv2
import numpy as np

import reporte
import vision
from productos import PRODUCTOS

PX_POR_CM = 30.0
CARPETA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "capturas")
POR_NOMBRE = {p.nombre: p for p in PRODUCTOS}


def fruta(a_cm, b_cm, angulo, color_bgr, manchas=(), tam=(720, 960), sub=4):
    """
    Dibuja la fruta con la ecuación exacta de la elipse  (u/a)² + (v/b)² ≤ 1,
    con supermuestreo (sub × sub puntos por píxel) para bordes suaves y realistas.
    """
    alto, ancho = tam
    cx, cy = ancho / 2, alto / 2
    a, b = a_cm * PX_POR_CM, b_cm * PX_POR_CM
    th = np.radians(angulo)

    off = (np.arange(sub) + 0.5) / sub
    ys = (np.arange(alto)[:, None] + off[None, :]).ravel()
    xs = (np.arange(ancho)[:, None] + off[None, :]).ravel()
    X, Y = np.meshgrid(xs - cx, ys - cy)
    U = X * np.cos(th) + Y * np.sin(th)
    V = -X * np.sin(th) + Y * np.cos(th)
    t = np.sqrt((U / a) ** 2 + (V / b) ** 2)          # 0 en el centro, 1 en el borde
    dentro = (t <= 1).astype(float)
    brillo = np.clip(1.10 - 0.25 * t ** 2, 0, 1)       # sombreado: borde más oscuro
    en_mancha = np.zeros_like(dentro)
    for (dx, dy, rad) in manchas:
        en_mancha = np.maximum(en_mancha, (((X - dx * PX_POR_CM) ** 2 + (Y - dy * PX_POR_CM) ** 2)
                                           <= (rad * PX_POR_CM) ** 2).astype(float) * dentro)

    def promedio(z):                                   # vuelve de sub-píxeles a píxeles
        return z.reshape(alto, sub, ancho, sub).mean(axis=(1, 3))

    img = np.empty((alto, ancho, 3))
    alfa = promedio(dentro)
    alfa_m = promedio(en_mancha)
    for k in range(3):
        piel = promedio(dentro * brillo * color_bgr[k]) / np.maximum(alfa, 1e-9)
        piel = np.clip(piel, 0, 255)
        mancha = (25, 45, 70)[k]
        color = piel * (alfa - alfa_m) / np.maximum(alfa, 1e-9) + mancha * alfa_m / np.maximum(alfa, 1e-9)
        img[..., k] = alfa * color + (1 - alfa) * 245
    ruido = np.random.default_rng(0).normal(0, 1.5, img.shape)
    return np.clip(img + ruido, 0, 255).astype(np.uint8)


CASOS = [
    # nombre, producto, a(cm), b(cm), ángulo, color, manchas [(dx, dy, radio) en cm]
    ("naranja_sana", "Naranja", 3.8, 3.8, 0, (0, 140, 255), []),
    ("naranja_manchada", "Naranja", 4.0, 4.0, 0, (0, 140, 255), [(-1.2, -0.8, 0.6), (1.0, 1.1, 0.45)]),
    ("limon_inclinado", "Limón", 3.5, 2.5, 30, (40, 200, 150), []),
    ("manzana_danada", "Manzana roja", 3.6, 3.3, -15, (40, 30, 190), [(0.3, 0.2, 1.4)]),
]


def main():
    os.makedirs(CARPETA, exist_ok=True)
    print(f"{'caso':18} {'A medida':>9} {'A exacta':>9} {'err%':>6} | {'V medido':>9} {'V exacto':>9} {'err%':>6} | "
          f"{'daño%':>6} {'estado':>9}")
    for nombre, prod, a, b, ang, color, manchas in CASOS:
        img = fruta(a, b, ang, color, manchas)
        r = vision.analizar(img, POR_NOMBRE[prod], PX_POR_CM)
        A_exacta = np.pi * a * b
        V_exacto = 4 / 3 * np.pi * a * b ** 2          # giro alrededor del eje mayor a
        ea = 100 * (r["area_cm2"] - A_exacta) / A_exacta
        ev = 100 * (r["volumen_cm3"] - V_exacto) / V_exacto
        print(f"{nombre:18} {r['area_cm2']:9.2f} {A_exacta:9.2f} {ea:6.2f} | {r['volumen_cm3']:9.1f} "
              f"{V_exacto:9.1f} {ev:6.2f} | {r['dano_pct']:6.1f} {r['estado']:>9}")

        anotada = img.copy()
        capa = anotada.copy()
        capa[r["dano"] > 0] = (0, 0, 255)
        anotada = cv2.addWeighted(capa, 0.55, anotada, 0.45, 0)
        cv2.drawContours(anotada, [r["contorno"]], -1, (0, 200, 0), 2)
        reporte.generar(anotada, r, os.path.join(CARPETA, f"demo_{nombre}.png"))
    print(f"\nLáminas guardadas en: {CARPETA}")


if __name__ == "__main__":
    main()
