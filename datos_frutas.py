"""
El dataset de Kaggle "Fruits fresh and rotten for classification" (manzana, banano y naranja,
frescas y podridas): listarlo, dividirlo por foto original y calcular la silueta de cada fruta.
Lo usan entrenar_frescura.py (la red neuronal) y entrenar_colores_dano.py (los colores de la piel
podrida). Solo necesita OpenCV y NumPy.

Por qué se divide por foto original: el dataset tiene solo 1 511 fotos distintas; las demás son
copias giradas (15°-75°), espejadas, desplazadas o con ruido de esas mismas fotos, repartidas al
azar entre train y test (1 310 originales tienen copias en los dos lados). Aquí todas las copias
de una foto van al mismo lado: 70 % entrenamiento, 15 % validación y 15 % prueba.
"""
import os
import random
import re
from collections import defaultdict
from multiprocessing import Pool

import cv2
import numpy as np
from PIL import Image

CLASES = ["freshapples", "freshbanana", "freshoranges", "rottenapples", "rottenbanana", "rottenoranges"]
COPIA = re.compile(r"^(rotated_by_-?\d+_|vertical_flip_|translation_|saltandpepper_)")
# copias alineadas con la foto original: se puede usar su silueta (la "vertical_flip" es un espejo izq.-der.)
SILUETA_DE_COPIA = {"": "igual", "saltandpepper_": "igual", "vertical_flip_": "espejo"}


def listar(carpeta):
    """{(clase, foto original): {archivo: ruta}} juntando train y test (la original y sus copias)."""
    grupos = defaultdict(dict)
    for parte in ("train", "test"):
        for c in CLASES:
            d = os.path.join(carpeta, parte, c)
            for f in sorted(os.listdir(d)):
                if f.lower().endswith((".png", ".jpg", ".jpeg")):
                    grupos[(c, COPIA.sub("", f))].setdefault(f, os.path.join(d, f))   # sin duplicados
    return grupos


def dividir(grupos, semilla=7, fracciones=(0.70, 0.15)):
    """División por foto original, estratificada por clase."""
    partes = {"entrenamiento": [], "validacion": [], "prueba": []}
    por_clase = defaultdict(list)
    for (c, base) in sorted(grupos):
        por_clase[c].append(base)
    rnd = random.Random(semilla)
    for c, bases in por_clase.items():
        rnd.shuffle(bases)
        n1 = round(len(bases) * fracciones[0])
        n2 = n1 + round(len(bases) * fracciones[1])
        for nombre, sel in (("entrenamiento", bases[:n1]), ("validacion", bases[n1:n2]), ("prueba", bases[n2:])):
            partes[nombre] += [(c, b) for b in sel]
    return partes


def rgb(ruta):
    """Imagen RGB (si trae transparencia, sobre blanco)."""
    im = Image.open(ruta)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        im = Image.alpha_composite(Image.new("RGBA", im.size, (255, 255, 255, 255)), im)
    return np.asarray(im.convert("RGB"))


def cuadrar(a, relleno):
    """Centra la imagen (o máscara) en un cuadrado, rellenando con `relleno` (como frescura.py)."""
    h, w = a.shape[:2]
    lado = max(h, w)
    out = np.full((lado, lado) + a.shape[2:], relleno, a.dtype)
    y0, x0 = (lado - h) // 2, (lado - w) // 2
    out[y0:y0 + h, x0:x0 + w] = a
    return out


# ---------------------------------------------------------------- siluetas (detector de la página)
def ruta_silueta(carpeta, clase, base):
    return os.path.join(carpeta, clase, os.path.splitext(base)[0] + ".png")


def _silueta(args):
    ruta, destino = args
    import vision                                   # el mismo detector de la página
    img = cv2.cvtColor(rgb(ruta), cv2.COLOR_RGB2BGR)
    H, W = img.shape[:2]
    a, b = H // 4, W // 4                           # margen: la fruta no debe tocar el borde
    m, _ = vision.segmentar(cv2.copyMakeBorder(img, a, a, b, b, cv2.BORDER_REPLICATE), None, 50)
    m = np.zeros((1, 1), np.uint8) if m is None else m[a:a + H, b:b + W]
    if m.size > 1 and not 0.03 <= (m > 0).mean() <= 0.95:
        m = np.zeros((1, 1), np.uint8)              # silueta dudosa: esa foto no se usa
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    cv2.imencode(".png", m)[1].tofile(destino)


def calcular_siluetas(grupos, pares, carpeta):
    """Silueta de cada foto original (se guarda en `carpeta`; las ya calculadas no se repiten)."""
    trabajos = []
    for c, b in pares:
        destino = ruta_silueta(carpeta, c, b)
        if b in grupos[(c, b)] and not os.path.exists(destino):
            trabajos.append((grupos[(c, b)][b], destino))
    if trabajos:
        print(f"Calculando {len(trabajos)} siluetas con el detector de la página…", flush=True)
        with Pool(min(8, os.cpu_count() or 2)) as p:
            p.map(_silueta, trabajos, chunksize=8)


def leer_silueta(ruta):
    if not ruta or not os.path.exists(ruta):
        return None
    m = cv2.imdecode(np.fromfile(ruta, np.uint8), cv2.IMREAD_GRAYSCALE)
    return m if m is not None and m.size > 1 else None
