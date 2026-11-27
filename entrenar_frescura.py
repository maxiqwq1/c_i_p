"""
Entrena la "segunda opinión" fresco / podrido (red neuronal) con el dataset de Kaggle
"Fruits fresh and rotten for classification" (manzana, banano y naranja; 6 clases).

    pip install -r requirements-entrenamiento.txt      (PyTorch: solo para entrenar)
    python entrenar_frescura.py "C:\\...\\dataset\\dataset"   (la carpeta que tiene train\\ y test\\)

Resultado: modelo_frescura.onnx + modelo_frescura.json. La página NO necesita PyTorch:
OpenCV (cv2.dnn) ejecuta el .onnx (ver frescura.py).

Por qué se rehace la división train/test del dataset:
el dataset tiene solo 1 511 fotos originales; las demás son copias giradas (15°-75°),
volteadas, desplazadas o con ruido de esas mismas fotos, repartidas al azar entre train y test
(1 310 originales tienen copias en los dos lados). Medir con ese test es medir con fotos que el
modelo ya vio. Aquí se separa POR FOTO ORIGINAL (todas sus copias van al mismo lado):
70 % entrenamiento, 15 % validación (elegir la mejor época) y 15 % prueba (la medida final).

Red: MobileNetV2 preentrenada en ImageNet (transferencia de aprendizaje), última capa de 6 salidas.
"""
import argparse
import json
import os
import random
import re
import time
from collections import defaultdict
from datetime import date

import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import models
from torchvision.transforms import v2 as T

CLASES = ["freshapples", "freshbanana", "freshoranges", "rottenapples", "rottenbanana", "rottenoranges"]
MEDIA = [0.485, 0.456, 0.406]          # normalización de ImageNet (la misma en frescura.py)
DESV = [0.229, 0.224, 0.225]
ENTRADA = 224
COPIA = re.compile(r"^(rotated_by_-?\d+_|vertical_flip_|translation_|saltandpepper_)")
RAIZ = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------- datos
def listar(carpeta):
    """{(clase, foto original): [rutas de la original y sus copias]} juntando train y test."""
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


def cargar(ruta):
    """RGB sobre fondo blanco (si trae transparencia) y cuadrada (relleno blanco), como en frescura.py."""
    im = Image.open(ruta)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        fondo = Image.new("RGBA", im.size, (255, 255, 255, 255))
        im = Image.alpha_composite(fondo, im)
    im = im.convert("RGB")
    w, h = im.size
    lado = max(w, h)
    cuadro = Image.new("RGB", (lado, lado), (255, 255, 255))
    cuadro.paste(im, ((lado - w) // 2, (lado - h) // 2))
    return cuadro


class Fotos(Dataset):
    def __init__(self, items, transform):
        self.items, self.transform = items, transform

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        ruta, y = self.items[i]
        return self.transform(cargar(ruta)), y


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
    ap.add_argument("--epocas", type=int, default=10)
    ap.add_argument("--lote", type=int, default=64)
    ap.add_argument("--trabajo", default=os.path.join(RAIZ, "entrenamiento_frescura"),
                    help="carpeta para la división y el mejor punto de control (no se sube a GitHub)")
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

    def items(parte, solo_originales):
        out = []
        for c, b in partes[parte]:
            for nombre, ruta in grupos[(c, b)].items():
                if not solo_originales or nombre == b:
                    out.append((ruta, CLASES.index(c)))
        return out

    tr, ev = transformaciones()
    entrenamiento = items("entrenamiento", False)       # originales + copias: más variedad
    validacion = items("validacion", False)
    prueba = items("prueba", True)                     # solo las fotos originales: la medida honesta
    prueba_copias = items("prueba", False)
    print(f"Fotos originales: {len(grupos)} | entrenamiento {len(partes['entrenamiento'])} "
          f"({len(entrenamiento)} con copias) | validación {len(partes['validacion'])} | prueba {len(prueba)}")

    kw = dict(num_workers=min(8, os.cpu_count() or 2), pin_memory=disp.type == "cuda", persistent_workers=True)
    c_tr = DataLoader(Fotos(entrenamiento, tr), a.lote, shuffle=True, drop_last=True, **kw)
    c_va = DataLoader(Fotos(validacion, ev), 128, **kw)

    modelo = crear_modelo().to(disp)
    opt = torch.optim.AdamW(modelo.parameters(), lr=4e-4, weight_decay=1e-4)
    pasos = a.epocas * len(c_tr)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=4e-4, total_steps=pasos, pct_start=0.15)
    escala = torch.amp.GradScaler(enabled=disp.type == "cuda")
    perdida = nn.CrossEntropyLoss(label_smoothing=0.1)
    mejor, ruta_mejor = -1.0, os.path.join(a.trabajo, "mejor.pt")

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
        print(f"época {ep:2d}  pérdida {total / n:.3f}  validación: 6 clases {m['exactitud_6_clases']:.3f} · "
              f"fresco/podrido {m['exactitud_fresco_podrido']:.3f}  ({time.time() - t0:.0f} s)", flush=True)
        if m["exactitud_fresco_podrido"] + m["exactitud_6_clases"] > mejor:
            mejor = m["exactitud_fresco_podrido"] + m["exactitud_6_clases"]
            torch.save(modelo.state_dict(), ruta_mejor)

    modelo.load_state_dict(torch.load(ruta_mejor, map_location=disp))
    res = {}
    for nombre, lista in (("prueba_originales", prueba), ("prueba_con_copias", prueba_copias), ("validacion", validacion)):
        res[nombre] = metricas(*predecir(modelo, DataLoader(Fotos(lista, ev), 128, num_workers=4), disp))
        print(f"{nombre}: 6 clases {res[nombre]['exactitud_6_clases']:.3f} · fresco/podrido "
              f"{res[nombre]['exactitud_fresco_podrido']:.3f} (n={res[nombre]['n']})")

    # exportar a ONNX (lo ejecuta OpenCV en el servidor, sin PyTorch)
    modelo = modelo.float().cpu().eval()
    salida = os.path.join(RAIZ, "modelo_frescura.onnx")
    torch.onnx.export(modelo, torch.zeros(1, 3, ENTRADA, ENTRADA), salida, input_names=["imagen"],
                      output_names=["logits"], opset_version=13, dynamo=False)
    info = {
        "descripcion": "Segunda opinión fresco/podrido (MobileNetV2, transferencia de aprendizaje)",
        "dataset": "Fruits fresh and rotten for classification (Kaggle: sriramr/fruits-fresh-and-rotten-for-classification)",
        "clases": CLASES, "entrada": ENTRADA, "media": MEDIA, "desv": DESV, "relleno": [255, 255, 255],
        "fotos_originales": len(grupos),
        "division_por_foto_original": {k: len(v) for k, v in partes.items()},
        "epocas": a.epocas, "fecha": date.today().isoformat(), "resultados": res,
    }
    with open(os.path.join(RAIZ, "modelo_frescura.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=1)
    print("Guardado:", salida, f"({os.path.getsize(salida) / 1e6:.1f} MB) y modelo_frescura.json")


if __name__ == "__main__":
    main()
