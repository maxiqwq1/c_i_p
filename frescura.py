"""
RED NEURONAL: ¿FRESCO O PODRIDO? Y CÓMO DECIDE EL ESTADO JUNTO CON EL DAÑO

El cálculo mide el daño como área de manchas oscuras (suma de Riemann sobre los píxeles mucho
más oscuros que la luz local, ver vision.py). Con fotos reales de fruta podrida eso no basta:
el moho blanco o verde, la piel arrugada o el café parejo no son "manchas más oscuras que la luz"
(con las fotos de prueba de Kaggle, el cálculo solo descartaba el 3 % de las frutas podridas).
Esta red neuronal, aprendida de fotos reales (dataset de Kaggle "Fruits fresh and rotten for
classification"; ver entrenar_frescura.py y modelo_frescura.json), sí los reconoce. Por eso el
estado se decide con las dos cosas (función decidir):

  P(podrido) ≥ RED_PODRIDO            -> DESCARTE (la red la ve podrida)
  RED_DUDA ≤ P(podrido) < RED_PODRIDO -> REGULAR, o DESCARTE si el daño medido ya lo exige
  P(podrido) < RED_DUDA               -> decide el daño medido, como siempre
                                         (BUENO / REGULAR / DESCARTE, e INMADURO por el color)

- Solo para Manzana roja, Manzana verde, Banano y Naranja (las frutas que vio al entrenar);
  con las demás frutas decide solo el daño medido.
- La red es una MobileNetV2 exportada a ONNX; la ejecuta OpenCV (cv2.dnn), sin PyTorch.
- Entrada: un cuadrado alrededor del producto (con un margen), tal como lo ve la cámara;
  224 × 224 píxeles normalizados como ImageNet.
- Salida: 6 probabilidades (softmax). P(podrido) = suma de las 3 clases podridas.

COLORES DE PIEL PODRIDA (piel_podrida): para que el ÁREA dañada también incluya la podredumbre
que no es oscura, se aprendió de las mismas fotos qué colores aparecen mucho más en la piel
podrida que en la sana: r(color) = ln P(color|podrida)/P(color|fresca) (colores_dano.json, ver
entrenar_colores_dano.py). Un píxel cuenta como podrido si r > umbral, y el umbral depende de lo
que vio la red (teorema de Bayes): si la ve fresca, solo los colores claramente de podrido; si la
ve podrida o duda, también los dudosos. vision.detectar_danos suma esos píxeles a las manchas oscuras.
"""
import json
import os
import threading

import cv2
import numpy as np

RAIZ = os.path.dirname(os.path.abspath(__file__))
RUTA_MODELO = os.path.join(RAIZ, "modelo_frescura.onnx")
RUTA_INFO = os.path.join(RAIZ, "modelo_frescura.json")
RUTA_COLORES = os.path.join(RAIZ, "colores_dano.json")

# Umbrales de la decisión (elegidos con las fotos de VALIDACIÓN; medidos con las de PRUEBA, ver README)
RED_PODRIDO = 0.5
RED_DUDA = 0.4

# producto de productos.py -> fruta del dataset
FRUTA = {"Manzana roja": "apples", "Manzana verde": "apples", "Banano": "banana", "Naranja": "oranges"}
NOMBRE_FRUTA = {"apples": "manzana", "banana": "banano", "oranges": "naranja"}

_red = None          # None = sin cargar; False = no hay modelo
_info = {}
_candado = threading.Lock()
_colores = None      # None = sin cargar; False = no hay modelo; si no, (casillas, {fruta: (r, umbral fresca, umbral podrida)})


def _tablas_color():
    global _colores
    if _colores is None:
        try:
            with open(RUTA_COLORES, encoding="utf-8") as f:
                d = json.load(f)
            tablas = {fruta: (np.array(v["ln_razon_x10"], np.float32) / 10, v["umbral_fresca"], v["umbral_podrida"])
                      for fruta, v in d["frutas"].items()}
            _colores = (tuple(d["bins_lab"]), tablas)
        except (OSError, ValueError, KeyError) as e:
            print("Colores de piel podrida no disponibles (el daño son solo manchas oscuras):", e)
            _colores = False
    return _colores


def piel_podrida_disponible(producto):
    t = _tablas_color()
    return bool(t) and FRUTA.get(producto) in t[1]


def piel_podrida(color_bgr, producto, p_podrido=None):
    """Píxeles cuyo color es de piel podrida para este producto (True/False por píxel),
    o None si no hay modelo de colores para él. color_bgr: la imagen con la luz ya corregida.
    p_podrido: lo que vio la red; si ve la fruta podrida o duda, cuentan también los colores dudosos."""
    t = _tablas_color()
    if not t or FRUTA.get(producto) not in t[1]:
        return None
    (nl, na, nb), tablas = t
    r, umbral_fresca, umbral_podrida = tablas[FRUTA[producto]]
    umbral = umbral_podrida if p_podrido is not None and p_podrido >= RED_DUDA else umbral_fresca
    lab = cv2.cvtColor(color_bgr, cv2.COLOR_BGR2Lab)
    i = ((lab[..., 0].astype(np.int32) * nl // 256) * na * nb + (lab[..., 1].astype(np.int32) * na // 256) * nb
         + lab[..., 2].astype(np.int32) * nb // 256)
    return r[i] > umbral


def disponible():
    global _red, _info
    if _red is None:
        try:
            with open(RUTA_INFO, encoding="utf-8") as f:
                _info = json.load(f)
            _red = cv2.dnn.readNetFromONNX(RUTA_MODELO)
        except (OSError, ValueError, cv2.error) as e:
            print("Red neuronal fresco/podrido no disponible (decide solo el daño):", e)
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
    """Lo que ve la red para el producto detectado, o None si no aplica o no hay modelo."""
    if not aplica(producto) or not disponible():
        return None
    p = probabilidades(recorte(imagen, contorno))
    clases = _info["clases"]
    podrido = float(sum(p[i] for i, c in enumerate(clases) if c.startswith("rotten")))
    mejor = clases[int(p.argmax())]
    fruta_red = NOMBRE_FRUTA.get(mejor.replace("fresh", "").replace("rotten", ""), "?")
    return {
        "podrido": round(podrido, 4), "fresco": round(1 - podrido, 4),
        "veredicto": "Podrido" if podrido >= RED_PODRIDO else "Dudoso" if podrido >= RED_DUDA else "Fresco",
        "confianza": round(max(podrido, 1 - podrido), 4),
        "fruta_red": fruta_red,                                 # qué fruta cree la red que es
        "coincide_fruta": fruta_red == NOMBRE_FRUTA[FRUTA[producto]],
        "umbrales": [RED_DUDA, RED_PODRIDO],                    # para que la página muestre las zonas
        "probabilidades": {c: round(float(v), 4) for c, v in zip(clases, p)},
    }


def texto(red):
    """Lo que ve la red, en corto: 'Fresco 96 %', 'Dudoso (45 % podrido)' o 'Podrido 92 %'."""
    P = red["podrido"]
    if red["veredicto"] == "Fresco":
        return f"Fresco {100 * (1 - P):.0f} %"
    if red["veredicto"] == "Dudoso":
        return f"Dudoso ({100 * P:.0f} % podrido)"
    return f"Podrido {100 * P:.0f} %"


def decidir(estado_calculo, red, dano_pct, producto):
    """Estado final con la red y el daño medido. Devuelve (estado, motivo)."""
    if red is None:
        if aplica(producto):
            return estado_calculo, f"Decide el daño medido ({dano_pct:.1f} %): la red neuronal no está disponible."
        return estado_calculo, (f"Decide el daño medido ({dano_pct:.1f} %): la red neuronal solo conoce "
                                f"manzana, banano y naranja.")
    P = red["podrido"]
    if P >= RED_PODRIDO:
        return "DESCARTE", f"La red neuronal la ve podrida ({100 * P:.0f} %)."
    if P >= RED_DUDA:
        if estado_calculo == "DESCARTE":
            return "DESCARTE", f"Daño medido de {dano_pct:.1f} % y la red duda ({100 * P:.0f} % podrido)."
        return "REGULAR", f"La red duda ({100 * P:.0f} % podrido): conviene revisarla."
    return estado_calculo, f"La red la ve fresca ({100 * (1 - P):.0f} %): decide el daño medido ({dano_pct:.1f} %)."
