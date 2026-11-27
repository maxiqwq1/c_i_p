"""
SEGUNDA OPINIÓN: ¿FRESCO O PODRIDO? (red neuronal)

El estado del producto lo decide el cálculo (área dañada = suma de Riemann sobre los píxeles
oscuros, ver vision.py). Esta red neuronal da una segunda opinión independiente, aprendida de
fotos reales: el dataset de Kaggle "Fruits fresh and rotten for classification"
(manzana, banano y naranja; ver entrenar_frescura.py y modelo_frescura.json).

- Solo opina sobre Manzana roja, Manzana verde, Banano y Naranja (las frutas que vio al entrenar).
- La red es una MobileNetV2 exportada a ONNX; la ejecuta OpenCV (cv2.dnn), sin PyTorch.
- Entrada: un cuadrado alrededor del producto (con un margen), tal como lo ve la cámara;
  224 × 224 píxeles normalizados como ImageNet. Pintar el fondo de blanco (como las fotos del
  dataset) resultó peor: la máscara recorta a veces el moho o el borde, y eso cambia la opinión.
- Salida: 6 probabilidades (softmax). P(podrido) = suma de las 3 clases podridas.
"""
import json
import os
import threading

import cv2
import numpy as np

RAIZ = os.path.dirname(os.path.abspath(__file__))
RUTA_MODELO = os.path.join(RAIZ, "modelo_frescura.onnx")
RUTA_INFO = os.path.join(RAIZ, "modelo_frescura.json")

# producto de productos.py -> fruta del dataset
FRUTA = {"Manzana roja": "apples", "Manzana verde": "apples", "Banano": "banana", "Naranja": "oranges"}
NOMBRE_FRUTA = {"apples": "manzana", "banana": "banano", "oranges": "naranja"}

_red = None          # None = sin cargar; False = no hay modelo
_info = {}
_candado = threading.Lock()


def disponible():
    global _red, _info
    if _red is None:
        try:
            with open(RUTA_INFO, encoding="utf-8") as f:
                _info = json.load(f)
            _red = cv2.dnn.readNetFromONNX(RUTA_MODELO)
        except (OSError, ValueError, cv2.error) as e:
            print("Segunda opinión (red neuronal) no disponible:", e)
            _red = False
    return _red is not False


def aplica(producto):
    return producto in FRUTA


def recorte(imagen, contorno, margen=0.08):
    """Cuadrado alrededor del producto (lo que quede fuera de la imagen se rellena de blanco,
    como al entrenar)."""
    H, W = imagen.shape[:2]
    x, y, w, h = cv2.boundingRect(contorno)
    lado = max(int(round(max(w, h) * (1 + 2 * margen))), 8)
    x0, y0 = int(round(x + w / 2 - lado / 2)), int(round(y + h / 2 - lado / 2))
    cuadro = np.full((lado, lado, 3), 255, np.uint8)
    xa, ya, xb, yb = max(x0, 0), max(y0, 0), min(x0 + lado, W), min(y0 + lado, H)
    cuadro[ya - y0:yb - y0, xa - x0:xb - x0] = imagen[ya:yb, xa:xb]
    return cuadro


def probabilidades(cuadro_bgr):
    """Las 6 probabilidades de la red para una imagen ya recortada."""
    if not disponible():
        raise RuntimeError("No está el modelo (modelo_frescura.onnx): corra entrenar_frescura.py")
    n = _info["entrada"]
    x = cv2.resize(cuadro_bgr, (n, n), interpolation=cv2.INTER_AREA)
    x = cv2.cvtColor(x, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    x = (x - np.float32(_info["media"])) / np.float32(_info["desv"])
    blob = np.ascontiguousarray(x.transpose(2, 0, 1)[None])
    with _candado:
        _red.setInput(blob)
        z = _red.forward().reshape(-1).astype(np.float64)
    e = np.exp(z - z.max())
    return e / e.sum()


def evaluar(imagen, contorno, producto):
    """Segunda opinión para el producto detectado, o None si no aplica o no hay modelo."""
    if not aplica(producto) or not disponible():
        return None
    p = probabilidades(recorte(imagen, contorno))
    clases = _info["clases"]
    podrido = float(sum(p[i] for i, c in enumerate(clases) if c.startswith("rotten")))
    mejor = clases[int(p.argmax())]
    fruta_red = NOMBRE_FRUTA.get(mejor.replace("fresh", "").replace("rotten", ""), "?")
    return {
        "podrido": round(podrido, 4), "fresco": round(1 - podrido, 4),
        "veredicto": "Podrido" if podrido >= 0.5 else "Fresco",
        "confianza": round(max(podrido, 1 - podrido), 4),
        "fruta_red": fruta_red,                                 # qué fruta cree la red que es
        "coincide_fruta": fruta_red == NOMBRE_FRUTA[FRUTA[producto]],
        "probabilidades": {c: round(float(v), 4) for c, v in zip(clases, p)},
    }
