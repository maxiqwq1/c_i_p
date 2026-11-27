"""
Entrena la red neuronal fresco / podrido con el dataset de Kaggle
"Fruits fresh and rotten for classification" (manzana, banano y naranja; 6 clases).

    pip install -r requirements-entrenamiento.txt      (PyTorch: solo para entrenar)
    python entrenar_frescura.py "C:\\...\\dataset\\dataset"   (la carpeta que tiene train\\ y test\\)

Resultado: modelo_frescura.onnx + modelo_frescura.json. La página NO necesita PyTorch:
OpenCV (cv2.dnn) ejecuta el .onnx (ver frescura.py).

Por qué se rehace la división train/test del dataset:
el dataset tiene solo 1 511 fotos originales; las demás son copias giradas (15°-75°),
espejadas, desplazadas o con ruido de esas mismas fotos, repartidas al azar entre train y test
(1 310 originales tienen copias en los dos lados). Medir con ese test es medir con fotos que el
modelo ya vio. Aquí se separa POR FOTO ORIGINAL (todas sus copias van al mismo lado):
70 % entrenamiento, 15 % validación (elegir la mejor época) y 15 % prueba (la medida final).

Por qué se cambia el fondo de las fotos al entrenar:
en el dataset las frutas frescas casi siempre están sobre fondo blanco y las podridas muchas veces
sobre madera o tela. Una red entrenada así aprende el atajo "fondo de color = podrido" y se
equivoca con una fruta fresca sobre la mesa. Por eso se calcula la silueta de cada foto original
con el mismo detector de la página (vision.segmentar) y, al entrenar, la fruta (fresca o podrida)
se pega muchas veces sobre fondos al azar: colores lisos, degradados, rayas tipo madera o tela,
o texturas de las propias fotos, a veces con sombra.

Red: MobileNetV2 preentrenada en ImageNet (transferencia de aprendizaje), última capa de 6 salidas.
"""
import argparse
import json
import os
import random
import time
from datetime import date

import cv2
import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import models
from torchvision.transforms import v2 as T

from datos_frutas import (CLASES, SILUETA_DE_COPIA, calcular_siluetas, cuadrar, dividir, leer_silueta, listar,
                          rgb, ruta_silueta)

MEDIA = [0.485, 0.456, 0.406]          # normalización de ImageNet (la misma en frescura.py)
DESV = [0.229, 0.224, 0.225]
ENTRADA = 224
PROB_FONDO = 0.6                       # fracción de las fotos de entrenamiento con el fondo cambiado
RAIZ = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------- fondos al azar
def fondo_al_azar(lado, R, texturas):
    """Fondo de lado×lado: color liso, degradado, rayas (madera/tela) o textura de otra foto."""
    rng = np.random.default_rng(R.getrandbits(32))
    def color():
        return np.array([R.randint(0, 255) for _ in range(3)], np.float32) * R.uniform(0.35, 1.0)
    t = R.random()
    if t < 0.3:
        f = np.ones((lado, lado, 3), np.float32) * color()
    elif t < 0.5:
        a = R.uniform(0, 2 * np.pi)
        yy, xx = np.mgrid[0:lado, 0:lado] / lado
        u = (np.cos(a) * xx + np.sin(a) * yy)
        u = (u - u.min()) / (np.ptp(u) + 1e-6)
        c1, c2 = color(), color()
        f = c1 + u[..., None] * (c2 - c1)
    elif t < 0.75 or not texturas:
        a, periodo = R.uniform(0, np.pi), R.uniform(0.02, 0.3) * lado
        yy, xx = np.mgrid[0:lado, 0:lado].astype(np.float32)
        u = np.cos(a) * xx + np.sin(a) * yy + rng.normal(0, 1, lado).cumsum()[None, :] * R.uniform(0, 0.5)
        v = 0.5 + 0.5 * np.sin(2 * np.pi * u / periodo + R.uniform(0, 6.3))
        c1, c2 = color(), color()
        f = c1 + v[..., None] * (c2 - c1)
    else:                                            # textura real: una esquina de otra foto del dataset
        im = rgb(R.choice(texturas)).astype(np.float32)
        h, w = im.shape[:2]
        s = int(min(h, w) * R.uniform(0.2, 0.35))
        y0, x0 = R.choice([0, h - s]), R.choice([0, w - s])
        f = cv2.resize(im[y0:y0 + s, x0:x0 + s], (lado, lado), interpolation=cv2.INTER_LINEAR)
    f = f + rng.normal(0, R.uniform(1, 9), f.shape)
    return np.clip(f, 0, 255)


def cambiar_fondo(img, m, R, texturas):
    """Pega la fruta (silueta m) sobre un fondo al azar, a veces con sombra; devuelve el cuadrado."""
    img, m = cuadrar(img, 255), cuadrar(m, 0)
    lado = img.shape[0]
    f = fondo_al_azar(lado, R, texturas)
    if R.random() < 0.5:                             # sombra suave desplazada
        k = max(3, int(lado * 0.08)) | 1
        dx, dy = (int(R.uniform(-0.06, 0.06) * lado) for _ in range(2))
        s = cv2.GaussianBlur(np.roll(np.roll(m, dy, 0), dx, 1).astype(np.float32) / 255, (k, k), 0)
        f = f * (1 - R.uniform(0.2, 0.5) * s[..., None])
    alfa = cv2.GaussianBlur(m.astype(np.float32) / 255, (5, 5), 0)[..., None]
    return np.clip(img * alfa + f * (1 - alfa), 0, 255).astype(np.uint8)


class Fotos(Dataset):
    """items: (ruta, clase, silueta, transformación de la silueta). fondos: probabilidad de cambiar
    el fondo (0 = nunca); fijo=True usa siempre el mismo fondo por foto (para validar)."""

    def __init__(self, items, transform, fondos=0.0, texturas=(), fijo=False):
        self.items, self.transform, self.fondos, self.texturas, self.fijo = items, transform, fondos, list(texturas), fijo

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        ruta, y, silueta, como = self.items[i]
        img = rgb(ruta)
        R = random.Random(i) if self.fijo else random
        if self.fondos and silueta and R.random() < self.fondos:
            m = leer_silueta(silueta)
            if m is not None and m.shape == img.shape[:2]:
                img = cambiar_fondo(img, m[:, ::-1] if como == "espejo" else m, R, self.texturas)
        return self.transform(Image.fromarray(cuadrar(img, 255))), y


def transformaciones():
    normal = [T.ToImage(), T.ToDtype(torch.float32, scale=True), T.Normalize(MEDIA, DESV)]
    entrenar = T.Compose([
        T.RandomResizedCrop(ENTRADA, scale=(0.55, 1.0), ratio=(0.8, 1.25), antialias=True),
        T.RandomHorizontalFlip(),
        T.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.2, hue=0.02),   # luz distinta, mismo color
        T.RandomApply([T.GaussianBlur(5, sigma=(0.1, 1.5))], p=0.2),               # cámara desenfocada
        T.RandomApply([T.JPEG((35, 95))], p=0.4),                                 # cuadros comprimidos de la web
        *normal,
    ])
    evaluar = T.Compose([T.Resize((ENTRADA, ENTRADA), antialias=True), *normal])
    return entrenar, evaluar


# ---------------------------------------------------------------- modelo
def crear_modelo():
    m = models.mobilenet_v2(weights=models.MobileNet_V2_Weights.IMAGENET1K_V2)
    m.classifier[1] = nn.Linear(m.classifier[1].in_features, len(CLASES))
    return m


@torch.no_grad()
def predecir(modelo, cargador, disp):
    modelo.eval()
    probs, ys = [], []
    for x, y in cargador:
        with torch.autocast(disp.type, enabled=disp.type == "cuda"):
            p = modelo(x.to(disp, non_blocking=True)).float().softmax(1)
        probs.append(p.cpu())
        ys.append(y)
    return torch.cat(probs).numpy(), torch.cat(ys).numpy()


def metricas(p, y):
    pred = p.argmax(1)
    podrido = p[:, 3:].sum(1) >= 0.5                     # fresco/podrido: suma de las 3 clases podridas
    real_podrido = y >= 3
    matriz = np.zeros((len(CLASES), len(CLASES)), int)
    for a, b in zip(y, pred):
        matriz[a, b] += 1
    return {"exactitud_6_clases": float((pred == y).mean()),
            "exactitud_fresco_podrido": float((podrido == real_podrido).mean()),
            "podridas_detectadas": float(podrido[real_podrido].mean()),
            "frescas_bien": float((~podrido[~real_podrido]).mean()),
            "n": int(len(y)), "matriz": matriz.tolist()}


# ---------------------------------------------------------------- principal
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dataset", help="carpeta con train/ y test/ (6 subcarpetas cada una)")
    ap.add_argument("--epocas", type=int, default=12)
    ap.add_argument("--lote", type=int, default=64)
    ap.add_argument("--sin-fondos", action="store_true", help="no cambiar el fondo al entrenar")
    ap.add_argument("--solo-evaluar", action="store_true",
                    help="no entrena: mide y exporta el mejor punto de control ya guardado (mejor.pt)")
    ap.add_argument("--trabajo", default=os.path.join(RAIZ, "entrenamiento_frescura"),
                    help="carpeta para la división, las siluetas y el mejor punto de control (no se sube a GitHub)")
    a = ap.parse_args()
    torch.manual_seed(7)
    random.seed(7)
    os.makedirs(a.trabajo, exist_ok=True)
    disp = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("Dispositivo:", torch.cuda.get_device_name(0) if disp.type == "cuda" else "CPU (lento)")

    grupos = listar(a.dataset)
    partes = dividir(grupos)
    with open(os.path.join(a.trabajo, "division.json"), "w", encoding="utf-8") as f:
        json.dump({k: [f"{c}/{b}" for c, b in v] for k, v in partes.items()}, f, ensure_ascii=False, indent=0)
    carpeta_sil = os.path.join(a.trabajo, "siluetas")
    calcular_siluetas(grupos, [x for v in partes.values() for x in v], carpeta_sil)

    def items(parte, solo_originales):
        out = []
        for c, b in partes[parte]:
            sil = ruta_silueta(carpeta_sil, c, b)
            for nombre, ruta in grupos[(c, b)].items():
                if solo_originales and nombre != b:
                    continue
                prefijo = nombre[:len(nombre) - len(b)]
                como = SILUETA_DE_COPIA.get(prefijo)
                out.append((ruta, CLASES.index(c), sil if como else None, como))
        return out

    tr, ev = transformaciones()
    entrenamiento = items("entrenamiento", False)       # originales + copias: más variedad
    validacion = items("validacion", False)
    val_orig = items("validacion", True)
    prueba = items("prueba", True)                     # solo las fotos originales: la medida honesta
    prueba_copias = items("prueba", False)
    texturas = [r for r, *_ in items("entrenamiento", True)]
    fondos = 0.0 if a.sin_fondos else PROB_FONDO
    print(f"Fotos originales: {len(grupos)} | entrenamiento {len(partes['entrenamiento'])} "
          f"({len(entrenamiento)} con copias) | validación {len(partes['validacion'])} | prueba {len(prueba)}"
          f" | fondo cambiado: {fondos:.0%} de las fotos con silueta")

    modelo = crear_modelo().to(disp)
    ruta_mejor = os.path.join(a.trabajo, "mejor.pt")
    if not a.solo_evaluar:
        entrenar(modelo, disp, a, Fotos(entrenamiento, tr, fondos, texturas), Fotos(validacion, ev),
                 Fotos(val_orig, ev, 1.0, texturas, fijo=True), ruta_mejor)

    # medir el mejor punto de control con la PRUEBA y exportarlo
    modelo.load_state_dict(torch.load(ruta_mejor, map_location=disp))
    res = {}
    for nombre, ds in (("prueba_originales", Fotos(prueba, ev)), ("prueba_otros_fondos", Fotos(prueba, ev, 1.0, texturas, fijo=True)),
                       ("prueba_con_copias", Fotos(prueba_copias, ev)), ("validacion", Fotos(validacion, ev))):
        res[nombre] = metricas(*predecir(modelo, DataLoader(ds, 128, num_workers=2), disp))
        print(f"{nombre}: fresco/podrido {res[nombre]['exactitud_fresco_podrido']:.3f} · 6 clases "
              f"{res[nombre]['exactitud_6_clases']:.3f} (n={res[nombre]['n']})", flush=True)
    exportar(modelo, {
        "descripcion": "Red fresco/podrido (MobileNetV2, transferencia de aprendizaje, fondos cambiados al entrenar)",
        "dataset": "Fruits fresh and rotten for classification (Kaggle: sriramr/fruits-fresh-and-rotten-for-classification)",
        "clases": CLASES, "entrada": ENTRADA, "media": MEDIA, "desv": DESV, "relleno": [255, 255, 255],
        "fotos_originales": len(grupos),
        "division_por_foto_original": {k: len(v) for k, v in partes.items()},
        "epocas": a.epocas, "fondos_cambiados": fondos, "fecha": date.today().isoformat(), "resultados": res,
    })


def entrenar(modelo, disp, a, ds_tr, ds_va, ds_vf, ruta_mejor):
    """Entrena y guarda en ruta_mejor la época con mejor validación (fondo original y otros fondos)."""
    # pocos procesos lectores: en Windows cada uno carga PyTorch entero (~0.6 GB de memoria)
    lectores = min(6, os.cpu_count() or 2)
    c_tr = DataLoader(ds_tr, a.lote, shuffle=True, drop_last=True, num_workers=lectores,
                      pin_memory=disp.type == "cuda", persistent_workers=True)
    c_va = DataLoader(ds_va, 128, num_workers=2)
    c_vf = DataLoader(ds_vf, 128, num_workers=2)    # validación sobre otros fondos
    opt = torch.optim.AdamW(modelo.parameters(), lr=4e-4, weight_decay=1e-4)
    pasos = a.epocas * len(c_tr)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=4e-4, total_steps=pasos, pct_start=0.15)
    escala = torch.amp.GradScaler(enabled=disp.type == "cuda")
    perdida = nn.CrossEntropyLoss(label_smoothing=0.1)
    mejor = -1.0

    for ep in range(1, a.epocas + 1):
        modelo.train()
        t0, total, n = time.time(), 0.0, 0
        for x, y in c_tr:
            x, y = x.to(disp, non_blocking=True), y.to(disp, non_blocking=True)
            with torch.autocast(disp.type, enabled=disp.type == "cuda"):
                l = perdida(modelo(x), y)
            opt.zero_grad(set_to_none=True)
            escala.scale(l).backward()
            escala.step(opt)
            escala.update()
            sched.step()
            total += l.item() * len(y)
            n += len(y)
        m = metricas(*predecir(modelo, c_va, disp))
        mf = metricas(*predecir(modelo, c_vf, disp))
        print(f"época {ep:2d}  pérdida {total / n:.3f}  validación fresco/podrido: fondo original "
              f"{m['exactitud_fresco_podrido']:.3f} · otros fondos {mf['exactitud_fresco_podrido']:.3f} "
              f"(6 clases {m['exactitud_6_clases']:.3f})  ({time.time() - t0:.0f} s)", flush=True)
        nota = m["exactitud_fresco_podrido"] + mf["exactitud_fresco_podrido"] + 0.5 * m["exactitud_6_clases"]
        if nota > mejor:
            mejor = nota
            torch.save(modelo.state_dict(), ruta_mejor)

    del c_tr, c_va, c_vf                             # cierra los procesos lectores antes de seguir


def exportar(modelo, info):
    """Exporta a ONNX (lo ejecuta OpenCV en el servidor, sin PyTorch) y guarda los resultados."""
    modelo = modelo.float().cpu().eval()
    salida = os.path.join(RAIZ, "modelo_frescura.onnx")
    torch.onnx.export(modelo, torch.zeros(1, 3, ENTRADA, ENTRADA), salida, input_names=["imagen"],
                      output_names=["logits"], opset_version=13, dynamo=False)
    with open(os.path.join(RAIZ, "modelo_frescura.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=1)
    print("Guardado:", salida, f"({os.path.getsize(salida) / 1e6:.1f} MB) y modelo_frescura.json")


if __name__ == "__main__":
    main()
