"""
Aprende qué COLORES de piel indican podredumbre (manzana, banano y naranja), a partir de las
fotos del dataset de Kaggle "Fruits fresh and rotten for classification".

    python entrenar_colores_dano.py "C:\\...\\dataset\\dataset"   (la carpeta que tiene train\\ y test\\)

Resultado: colores_dano.json, que usa vision.detectar_danos (solo OpenCV y NumPy; no hace falta PyTorch).

Por qué: el daño se medía solo como manchas MUCHO más oscuras que la luz local. La piel podrida
café claro y agrietada, el moho blanco o verde, o el café parejo de un banano pasado no son más
oscuros que la luz: quedaban fuera del área dañada (una manzana con media piel podrida daba 2 %).

Cómo:
1. Silueta de cada foto original con el detector de la página; se toma el interior de la piel
   (sin el borde) y se corrige el color de la luz igual que en la página (vision.balance_blancos).
2. Para cada fruta se cuenta cuántas veces aparece cada color (espacio Lab, en 8 × 32 × 32 casillas)
   en la piel de las frutas FRESCAS y en la de las PODRIDAS (cada foto pesa lo mismo), y se suaviza.
3. Razón de verosimilitud: r(color) = ln( P(color | podrida) / P(color | fresca) ). Un color es
   "de podrido" si r > umbral: aparece mucho más en la piel podrida que en la sana.
4. Dos umbrales (teorema de Bayes: lo que ya se sabe de la fruta cambia cuánto pesa un color dudoso):
   - si la red neuronal ve la fruta FRESCA: el umbral de cada fruta se elige con las fotos de
     VALIDACIÓN, el menor con el que casi ninguna fruta fresca (≤ 2 %) llega a 5 % de piel "podrida";
   - si la red la ve PODRIDA (o duda): UMBRAL_PODRIDA = 1.2, elegido mirando fotos de prueba: con
     él la zona marcada coincide con lo podrido sin tomar la piel sana (más bajo, empieza a tomarla).
   Se mide con las fotos de PRUEBA.
"""
import argparse
import json
import os
from datetime import date
from multiprocessing import Pool

import cv2
import numpy as np

from datos_frutas import calcular_siluetas, dividir, leer_silueta, listar, rgb, ruta_silueta

RAIZ = os.path.dirname(os.path.abspath(__file__))
BINS = (8, 32, 32)                      # casillas de L, a y b (Lab de OpenCV, 0-255)
FRUTAS = ("apples", "banana", "oranges")
DESCARTE = {"apples": 15, "banana": 25, "oranges": 15}    # % de daño de descarte (productos.py)
UMBRALES = [round(x, 1) for x in np.arange(1.2, 3.01, 0.1)]
UMBRAL_PODRIDA = 1.2


def interior(m):
    """La piel sin el borde, igual que vision.detectar_danos."""
    area = cv2.countNonZero(m)
    k = max(3, int(0.08 * np.sqrt(4 * area / np.pi)))
    return cv2.erode(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))) > 0


def casillas(lab):
    nl, na, nb = BINS
    return ((lab[:, 0].astype(np.int32) * nl // 256) * na * nb + (lab[:, 1].astype(np.int32) * na // 256) * nb
            + lab[:, 2].astype(np.int32) * nb // 256)


def _piel(args):
    """Casillas de color de la piel de una foto (muestra de hasta 20 000 píxeles)."""
    ruta, silueta = args
    import vision
    m = leer_silueta(silueta)
    img = cv2.cvtColor(rgb(ruta), cv2.COLOR_RGB2BGR)
    if m is None or m.shape != img.shape[:2]:
        return None
    m = (m > 0).astype(np.uint8) * 255
    color = vision.balance_blancos(img, m)             # como en la página
    lab = cv2.cvtColor(color, cv2.COLOR_BGR2Lab)[interior(m)]
    if len(lab) < 200:
        return None
    return casillas(lab[::max(1, len(lab) // 20000)])


def suavizar(h, s=1.0):
    """Suavizado gaussiano separable en las 3 dimensiones de casillas."""
    x = np.arange(-3, 4)
    k = np.exp(-x ** 2 / (2 * s * s))
    k /= k.sum()
    h = h.reshape(BINS)
    for eje in range(3):
        h = np.apply_along_axis(lambda v: np.convolve(v, k, mode="same"), eje, h)
    return h.ravel()


def razon(pieles, clases):
    """ln P(color|podrida)/P(color|fresca), con cada foto pesando lo mismo."""
    h = {"fresh": np.zeros(np.prod(BINS)), "rotten": np.zeros(np.prod(BINS))}
    for idx, c in zip(pieles, clases):
        cuenta = np.bincount(idx, minlength=np.prod(BINS)).astype(np.float64)
        h["fresh" if c.startswith("fresh") else "rotten"] += cuenta / cuenta.sum()
    p = {k: suavizar(v) for k, v in h.items()}
    p = {k: v / max(v.sum(), 1e-9) for k, v in p.items()}
    return np.log((p["rotten"] + 1e-6) / (p["fresh"] + 1e-6))


def porcentajes(pieles, clases, r, umbral):
    fres, podr = [], []
    for idx, c in zip(pieles, clases):
        (fres if c.startswith("fresh") else podr).append(100 * float((r[idx] > umbral).mean()))
    return np.array(fres), np.array(podr)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dataset", help="carpeta con train/ y test/ (6 subcarpetas cada una)")
    ap.add_argument("--trabajo", default=os.path.join(RAIZ, "entrenamiento_frescura"),
                    help="carpeta con las siluetas (la misma de entrenar_frescura.py; no se sube a GitHub)")
    a = ap.parse_args()
    grupos = listar(a.dataset)
    partes = dividir(grupos)
    carpeta = os.path.join(a.trabajo, "siluetas")
    calcular_siluetas(grupos, [x for v in partes.values() for x in v], carpeta)

    datos = {}
    for parte, pares in partes.items():
        trabajos = [(grupos[(c, b)][b], ruta_silueta(carpeta, c, b)) for c, b in pares]
        with Pool(min(8, os.cpu_count() or 2)) as p:
            pieles = p.map(_piel, trabajos, chunksize=8)
        datos[parte] = [(c, idx) for (c, _), idx in zip(pares, pieles) if idx is not None]
        print(f"{parte}: {len(datos[parte])} fotos con silueta", flush=True)

    salida = {"descripcion": "Colores de piel podrida (razón de verosimilitud podrida/fresca en Lab)",
              "dataset": "Fruits fresh and rotten for classification (Kaggle: sriramr/fruits-fresh-and-rotten-for-classification)",
              "bins_lab": list(BINS), "fecha": date.today().isoformat(), "frutas": {}}
    for fruta in FRUTAS:
        sel = {k: [(c, i) for c, i in v if c.endswith(fruta)] for k, v in datos.items()}
        r = razon([i for _, i in sel["entrenamiento"]], [c for c, _ in sel["entrenamiento"]])
        val = ([i for _, i in sel["validacion"]], [c for c, _ in sel["validacion"]])
        umbral = UMBRALES[-1]
        for u in UMBRALES:                               # el menor que casi no marca frutas frescas
            f, _ = porcentajes(*val, r, u)
            if (f >= 5).mean() <= 0.02 and np.percentile(f, 90) <= 2.5:
                umbral = u
                break
        res = {}
        for parte in ("validacion", "prueba"):
            f, p = porcentajes([i for _, i in sel[parte]], [c for c, _ in sel[parte]], r, umbral)
            _, p2 = porcentajes([i for _, i in sel[parte]], [c for c, _ in sel[parte]], r, UMBRAL_PODRIDA)
            res[parte] = {"frescas_mediana_pct": round(float(np.median(f)), 2),
                          "frescas_con_5pct_o_mas": round(float((f >= 5).mean()), 3),
                          "podridas_mediana_pct": round(float(np.median(p)), 2),
                          "podridas_con_5pct_o_mas": round(float((p >= 5).mean()), 3),
                          f"podridas_con_{DESCARTE[fruta]}pct_o_mas": round(float((p >= DESCARTE[fruta]).mean()), 3),
                          "podridas_mediana_pct_con_umbral_podrida": round(float(np.median(p2)), 2),
                          "n_frescas": len(f), "n_podridas": len(p)}
            print(f"{fruta:8s} umbral {umbral} [{parte}] frescas: mediana {np.median(f):.1f} %, con ≥5 %: {100 * (f >= 5).mean():.1f} %"
                  f" | podridas: mediana {np.median(p):.1f} %, con ≥{DESCARTE[fruta]} %: {100 * (p >= DESCARTE[fruta]).mean():.0f} %")
        salida["frutas"][fruta] = {"umbral_fresca": umbral, "umbral_podrida": UMBRAL_PODRIDA,
                                   "ln_razon_x10": np.clip(np.round(r * 10), -99, 99).astype(int).tolist(),
                                   "resultados": res}
    with open(os.path.join(RAIZ, "colores_dano.json"), "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False)
    print("Guardado: colores_dano.json")


if __name__ == "__main__":
    main()
