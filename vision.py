"""
Visión por computador: encuentra el producto en la imagen (en cualquier
lugar y sobre cualquier fondo), lo reconoce, lo alinea, detecta manchas
(daño), estima madurez por color y clasifica.
"""
import json
import os

import cv2
import numpy as np

import calculo
from productos import PRODUCTOS

PESO_L = 0.35          # la luminosidad pesa poco: así las sombras no se confunden con el producto


# ---------------------------------------------------------------- detección automática
def _lab(img):
    lab = cv2.cvtColor(cv2.GaussianBlur(img, (5, 5), 0), cv2.COLOR_BGR2LAB).astype(np.float32)
    lab[..., 0] *= PESO_L
    return lab


def _modelo_fondo(lab, k=5):
    """
    Colores del fondo = colores del BORDE de la imagen (el producto normalmente no
    toca el borde). Se agrupan con k-medias para admitir fondos con varios tonos
    (mesa, mantel, hoja, sombra).
    """
    h, w = lab.shape[:2]
    b = max(4, int(0.04 * min(h, w)))
    borde = np.concatenate([lab[:b].reshape(-1, 3), lab[-b:].reshape(-1, 3),
                            lab[:, :b].reshape(-1, 3), lab[:, -b:].reshape(-1, 3)])
    paso = max(1, len(borde) // 4000)
    muestra = np.ascontiguousarray(borde[::paso])
    criterio = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 0.5)
    cv2.setRNGSeed(1)               # misma imagen -> mismo resultado (k-medias arranca al azar)
    _, _, centros = cv2.kmeans(muestra, k, None, criterio, 2, cv2.KMEANS_PP_CENTERS)
    return centros


def _distancia_fondo(lab, centros):
    """Para cada píxel: distancia (en color) al tono de fondo más parecido."""
    d = np.full(lab.shape[:2], np.inf, np.float32)
    for c in centros:
        d = np.minimum(d, np.sqrt(((lab - c) ** 2).sum(axis=2)))
    return d


def _grosor(c):
    """Grosor máximo de una silueta: diámetro del mayor círculo que cabe dentro (en px)."""
    x, y, w, h = cv2.boundingRect(c)
    m = np.zeros((h + 2, w + 2), np.uint8)
    cv2.drawContours(m, [c - np.array([x - 1, y - 1])], -1, 255, -1)
    return 2.0 * float(cv2.distanceTransform(m, cv2.DIST_L2, 5).max())


def _elegir_objeto(mascara):
    """
    De todas las regiones candidatas elige la que más parece un producto:
    tamaño razonable, forma compacta (convexa) o alargada pero gruesa (banano,
    zanahoria, pepino), que no toque el borde y que esté cerca del centro.
    Así se ignoran la mesa, sombras, lápices y objetos cortados.
    """
    H, W = mascara.shape
    contornos, _ = cv2.findContours(mascara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    mejor, mejor_puntaje = None, 0.0
    for c in contornos:
        area = cv2.contourArea(c)
        frac = area / (H * W)
        if not 0.002 <= frac <= 0.6:
            continue
        casco = cv2.contourArea(cv2.convexHull(c))
        solidez = area / casco if casco > 0 else 0
        (_, _), (rw, rh), _ = cv2.minAreaRect(c)
        # El grosor real (círculo inscrito) y no el ancho del rectángulo: un banano muy
        # curvo ocupa un rectángulo ancho, pero sigue siendo largo y delgado.
        largo, grosor = max(rw, rh), max(_grosor(c), 1.0)
        alargado = largo > 2 * grosor
        # un banano es curvo (poco convexo); una fruta redonda debe ser casi convexa
        if solidez < (0.6 if alargado else 0.8):
            continue
        # demasiado alargado o demasiado delgado: lápiz, cuchillo, cable, borde de mesa
        if largo > 8 * grosor or grosor < 0.035 * min(H, W):
            continue
        p = c.reshape(-1, 2)
        en_borde = np.mean((p[:, 0] <= 2) | (p[:, 1] <= 2) | (p[:, 0] >= W - 3) | (p[:, 1] >= H - 3))
        if en_borde > 0.05:
            continue
        m = cv2.moments(c)
        cx, cy = m["m10"] / m["m00"], m["m01"] / m["m00"]
        d_centro = np.hypot((cx - W / 2) / (W / 2), (cy - H / 2) / (H / 2)) / np.sqrt(2)
        puntaje = np.sqrt(frac) * solidez ** (1.5 if alargado else 3) * (1 - 0.6 * d_centro)
        if puntaje > mejor_puntaje:
            mejor, mejor_puntaje = c, puntaje
    return mejor


def segmentar(frame, fondo=None, sensibilidad=50):
    """
    Devuelve (mascara_rellena, contorno) del producto, o (None, None).

    - Automático (sin fondo): un píxel es "producto" si su color está lejos de
      todos los colores del borde de la imagen. No hace falta hoja blanca ni
      recuadro: funciona sobre una mesa, un mantel, etc.
    - Con fondo capturado (tecla B): es producto lo que cambió respecto al fondo
      vacío. Sirve para productos pálidos sobre fondos de color parecido.
    sensibilidad 0-100: más alta detecta productos más parecidos al fondo
    (pero también más sombras).
    """
    umbral_min = 30.0 - 0.24 * float(np.clip(sensibilidad, 0, 100))      # 50 -> 18
    if fondo is not None:
        dist = cv2.absdiff(cv2.GaussianBlur(frame, (5, 5), 0),
                           cv2.GaussianBlur(fondo, (5, 5), 0)).max(axis=2).astype(np.float32)
        umbral = 2 * umbral_min
    else:
        # El mapa de distancias se calcula a resolución reducida (más rápido) y se
        # interpola: el borde sigue quedando con precisión de ~1 píxel.
        H, W = frame.shape[:2]
        f = min(1.0, 480 / max(H, W))
        peq = cv2.resize(frame, None, fx=f, fy=f, interpolation=cv2.INTER_AREA) if f < 1 else frame
        lab = _lab(peq)
        dist = _distancia_fondo(lab, _modelo_fondo(lab))
        if f < 1:
            dist = cv2.resize(dist, (W, H), interpolation=cv2.INTER_LINEAR)
        # Otsu separa "fondo" de "producto" en el mapa de distancias; el mínimo evita ruido
        d8 = np.clip(dist * 2, 0, 255).astype(np.uint8)
        otsu, _ = cv2.threshold(d8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        umbral = float(np.clip(otsu / 2, umbral_min, 2.5 * umbral_min))
    mascara = (dist > umbral).astype(np.uint8) * 255

    lado = min(mascara.shape)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (max(3, lado // 100) | 1,) * 2)
    mascara = cv2.morphologyEx(mascara, cv2.MORPH_CLOSE, k, iterations=2)
    mascara = cv2.morphologyEx(mascara, cv2.MORPH_OPEN, k)

    c = _elegir_objeto(mascara)
    if c is None:
        return None, None
    rellena = np.zeros_like(mascara)
    cv2.drawContours(rellena, [c], -1, 255, thickness=-1)   # rellena huecos internos (manchas)
    return rellena, c


# ---------------------------------------------------------------- geometría
def alinear(mascara, contorno):
    """
    Gira la silueta para que su eje mayor quede horizontal (eje de revolución).
    El ángulo sale de los momentos de segundo orden de la imagen.
    Devuelve la máscara girada y la transformación inversa para dibujar sobre el video.
    """
    x, y, w, h = cv2.boundingRect(contorno)
    D = int(np.ceil(np.hypot(w, h))) + 4
    lienzo = np.zeros((D, D), np.uint8)
    ox, oy = (D - w) // 2, (D - h) // 2
    lienzo[oy:oy + h, ox:ox + w] = mascara[y:y + h, x:x + w]

    m = cv2.moments(lienzo, binaryImage=True)
    angulo = 0.5 * np.degrees(np.arctan2(2 * m["mu11"], m["mu20"] - m["mu02"]))
    M = cv2.getRotationMatrix2D((D / 2, D / 2), angulo, 1.0)
    girada = cv2.warpAffine(lienzo, M, (D, D), flags=cv2.INTER_NEAREST)
    return girada, cv2.invertAffineTransform(M), (x - ox, y - oy), angulo


def a_imagen(puntos, Minv, desplazamiento):
    """Convierte puntos de la silueta girada a coordenadas del video original."""
    pts = np.asarray(puntos, dtype=float)
    unos = np.ones((pts.shape[0], 1))
    orig = np.hstack([pts, unos]) @ Minv.T
    orig += np.array(desplazamiento, dtype=float)
    return orig


def _a_lista(puntos):
    return [[int(round(x)), int(round(y))] for x, y in puntos]


def geometria(r, n_discos=16):
    """
    Para dibujar sobre el video, en coordenadas de la imagen:
      discos  n_discos segmentos (los discos del método de discos); con eje curvo
              son perpendiculares a la curva
      eje     polilínea del eje de revolución (recto: 2 puntos; curvo: la curva)
    """
    cols, sup, inf = r["columnas"], r["fila_sup"], r["fila_inf"]
    idx = np.linspace(0, len(cols) - 1, n_discos + 2).astype(int)[1:-1]
    M, d = r["Minv"], r["desplazamiento"]
    if r.get("metodo_volumen") == "curvo":
        # fila del eje curvo en la imagen alineada: c = -(fila) - eje  ->  fila = -c - eje
        fila_c = -(r["c_px"] + r["eje_px"])
        pend = -r["dc"]                                   # pendiente en filas (la y de la imagen baja)
        medio = (inf + 1 - sup) / 2 / np.sqrt(1 + r["dc"] ** 2)     # radio perpendicular (px)
        discos = []
        for i in idx:
            n = np.array([-pend[i], 1.0]) / np.hypot(pend[i], 1.0)   # normal a la curva
            c0 = np.array([cols[i] + 0.5, fila_c[i]])
            discos.append(_a_lista(a_imagen([c0 - medio[i] * n, c0 + medio[i] * n], M, d)))
        j = np.linspace(0, len(cols) - 1, 40).astype(int)
        eje = _a_lista(a_imagen(np.stack([cols[j] + 0.5, fila_c[j]], 1), M, d))
        return discos, eje
    discos = [_a_lista(a_imagen([(cols[i] + 0.5, sup[i]), (cols[i] + 0.5, inf[i] + 1)], M, d)) for i in idx]
    fila_eje = np.median((sup + inf + 1) / 2)
    eje = _a_lista(a_imagen([(cols[0], fila_eje), (cols[-1] + 1, fila_eje)], M, d))
    return discos, eje


def caja_enfoque(contorno, forma, margen=0.45, proporcion=None):
    """
    Rectángulo (x0, y0, x1, y1) alrededor del producto, con margen, para hacer
    zoom sobre él. Si se da proporcion (ancho/alto) se ajusta a esa forma.
    """
    H, W = forma[:2]
    x, y, w, h = cv2.boundingRect(contorno)
    cx, cy = x + w / 2, y + h / 2
    w, h = w * (1 + 2 * margen), h * (1 + 2 * margen)
    if proporcion:
        if w / h < proporcion:
            w = h * proporcion
        else:
            h = w / proporcion
    w, h = min(w, W), min(h, H)
    x0 = int(np.clip(cx - w / 2, 0, W - w))
    y0 = int(np.clip(cy - h / 2, 0, H - h))
    return x0, y0, int(x0 + w), int(y0 + h)


def anotar(frame, r, ver_discos=True):
    """Dibuja sobre una copia del cuadro: manchas en rojo, contorno verde, discos y eje."""
    vista = frame.copy()
    capa = vista.copy()
    capa[r["dano"] > 0] = (0, 0, 255)
    vista = cv2.addWeighted(capa, 0.55, vista, 0.45, 0)
    cv2.drawContours(vista, [r["contorno"]], -1, (0, 255, 0), 2)
    if ver_discos:
        discos, eje = geometria(r)
        for p0, p1 in discos:
            cv2.line(vista, tuple(p0), tuple(p1), (0, 220, 255), 1)
        cv2.polylines(vista, [np.array(eje, np.int32)], False, (255, 255, 0), 1, cv2.LINE_AA)
    return vista


# ---------------------------------------------------------------- calidad
def iluminacion(V, interior, iteraciones=3):
    """
    Cómo cae la luz sobre la fruta: superficie suave (polinomio cúbico en x, y) ajustada
    por mínimos cuadrados al brillo de la piel. En cada vuelta se descartan los píxeles
    mucho más oscuros que el ajuste (las manchas), para que no lo arrastren hacia abajo.
    Devuelve el brillo esperado en cada píxel del interior.
    """
    ys, xs = np.nonzero(interior)
    v = V[ys, xs].astype(np.float64)
    cx, cy = xs.mean(), ys.mean()
    s = max(xs.std(), ys.std(), 1.0)
    x, y = (xs - cx) / s, (ys - cy) / s
    A = np.stack([np.ones_like(x), x, y, x * x, x * y, y * y, x ** 3, x * x * y, x * y * y, y ** 3], axis=1)
    paso = max(1, len(v) // 20000)                        # basta una muestra para ajustar
    usar = np.zeros(len(v), bool)
    usar[::paso] = True
    ajuste = np.full(len(v), np.median(v))
    for _ in range(iteraciones):
        if usar.sum() < 20:
            break
        coef, *_ = np.linalg.lstsq(A[usar], v[usar], rcond=None)
        ajuste = A @ coef
        usar = (v >= 0.8 * ajuste)
        usar[np.arange(len(v)) % paso != 0] = False
    esperado = np.zeros(V.shape, np.float32)
    esperado[ys, xs] = np.maximum(ajuste, 1.0)
    return esperado


def detectar_danos(frame, mascara, producto):
    """
    Manchas = píxeles del interior mucho más oscuros que la luz que les LLEGA
    (ver iluminacion). Así la sombra del lado no iluminado no se cuenta como daño,
    pero una mancha oscura sí, esté donde esté.
    """
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    area = cv2.countNonZero(mascara)
    diam = np.sqrt(4 * area / np.pi)
    k = max(3, int(0.08 * diam))                 # se ignora el borde (sombra natural)
    interior = cv2.erode(mascara, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    if cv2.countNonZero(interior) < 50:
        return np.zeros_like(mascara), interior, hsv
    V = hsv[..., 2]
    esperado = iluminacion(V, interior > 0)
    # En pieles oscuras (aguacate Hass, pepino) las grietas y rayas naturales ya son muy oscuras:
    # allí el umbral baja con la luz que llega y solo cuenta lo casi negro.
    factor = producto.factor_oscuro * np.clip(esperado / 120.0, 0.5, 1.0)
    dano = ((V < factor * esperado) & (interior > 0)).astype(np.uint8) * 255
    # se quitan puntos y grietas finas (poros, rugosidad del Hass): una mancha real es un parche
    lado = max(3, int(round(0.015 * diam)) | 1)
    dano = cv2.morphologyEx(dano, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (lado, lado)))
    return dano, interior, hsv


# ---------------------------------------------------------------- reconocimiento
I_GENERICO = len(PRODUCTOS) - 1
UMBRAL_EJEMPLO = 0.5        # distancia máxima para aceptar el ejemplo enseñado más parecido
UMBRAL_TABLA = 0.4          # más estricto para las fotos de la tabla (son fotos de estudio)
RUTA_TABLA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "entrenamiento_tabla.json")


def cargar_ejemplos_tabla(ruta=RUTA_TABLA):
    """
    Entrenamiento base: los rasgos de las 16 fotos de la tabla de colores
    (los genera entrenar_tabla.py). Se usan como ejemplos de referencia.
    """
    try:
        with open(ruta, encoding="utf-8") as f:
            datos = json.load(f)
    except (OSError, ValueError):
        return []
    por_nombre = {p.nombre: i for i, p in enumerate(PRODUCTOS)}
    return [{"producto": por_nombre[e["nombre"]], "rasgos": e["rasgos"], "foto": e.get("foto")}
            for e in datos.get("ejemplos", []) if e.get("nombre") in por_nombre]


EJEMPLOS_TABLA = cargar_ejemplos_tabla()


def balance_blancos(frame, mascara):
    """
    Corrige el tinte de la luz (amarilla, azulada) usando el fondo que rodea al producto,
    pero SOLO si ese fondo es claro, neutro y uniforme (hoja, pared, mesa blanca).
    Así una manzana roja bajo luz cálida no parece naranja. Sobre madera o un mantel
    de color no se corrige nada (no se sabe cuál es el "blanco").
    """
    area = cv2.countNonZero(mascara)
    r = max(3, int(0.15 * np.sqrt(area)))
    cerca_ = cv2.dilate(mascara, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1,) * 2))
    lejos = cv2.dilate(mascara, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (6 * r + 1,) * 2))
    anillo = (lejos > 0) & (cerca_ == 0)
    if anillo.sum() < 200:
        return frame
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)[anillo].astype(np.float32)
    L, a, b = np.median(lab, axis=0)
    croma = np.hypot(a - 128, b - 128)
    uniforme = lab[:, 1].std() < 8 and lab[:, 2].std() < 8
    # hoja/pared bajo luz con tinte: muy clara (L alto) aunque se vea amarillenta o azulada.
    # Una madera clara tiene el mismo tinte pero es bastante más oscura, y no se corrige.
    blanco_tenido = L >= 200 and croma <= 40
    gris_neutro = L >= 90 and croma <= 20          # mesa gris, pared, cartulina
    if not uniforme or not (blanco_tenido or gris_neutro):
        return frame
    bgr = np.median(frame[anillo].astype(np.float32), axis=0)
    ganancia = np.clip(bgr.mean() / np.maximum(bgr, 1), 0.75, 1.33)
    return np.clip(frame.astype(np.float32) * ganancia, 0, 255).astype(np.uint8)


def colores_dominantes(color_bgr, mascara, k=4):
    """
    Los k colores principales de la piel (k-medias en Lab) y qué % de la piel ocupa
    cada uno, del más abundante al menos. Se muestran junto a la paleta de la tabla.
    """
    interior = cv2.erode(mascara, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)), iterations=2) > 0
    if interior.sum() < 20 * k:
        interior = mascara > 0
    px = color_bgr[interior]
    px = px[:: max(1, len(px) // 3000)].reshape(-1, 1, 3)
    if len(px) < k:
        return []
    lab = cv2.cvtColor(px, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32)
    lab[:, 0] *= 0.5                                  # la luz (sombras, reflejos) pesa menos que el tono
    cv2.setRNGSeed(7)                                 # mismo resultado en cada llamada
    _, etiq, centros = cv2.kmeans(lab, k, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 0.5),
                                  2, cv2.KMEANS_PP_CENTERS)
    centros[:, 0] /= 0.5
    bgr = cv2.cvtColor(np.clip(centros, 0, 255).astype(np.uint8).reshape(-1, 1, 3), cv2.COLOR_LAB2BGR).reshape(-1, 3)
    pct = np.bincount(etiq.ravel(), minlength=k) / len(etiq)
    return [{"hex": "#%02x%02x%02x" % (int(bgr[i][2]), int(bgr[i][1]), int(bgr[i][0])), "pct": round(100 * float(pct[i]), 1)}
            for i in np.argsort(-pct)]


def rasgos_forma(contorno, med):
    """
    solidez    área / envolvente convexa (un manojo de hojas tiene entrantes)
    extension  área / rectángulo mínimo que la encierra (elipse: 0.785; hoja con punta: ~0.7)
    asimetria  |ancho en el primer tramo del eje - ancho en el último| / ancho máximo
               (tramos de 15-35 % y 65-85 % del largo): una pera, con cuello, ~0.3-0.5
    """
    area = cv2.contourArea(contorno)
    casco = cv2.contourArea(cv2.convexHull(contorno))
    (_, _), (rw, rh), _ = cv2.minAreaRect(contorno)
    ancho = med["f_cm"] - med["g_cm"]
    n = len(ancho)
    tramo = lambda a, b: float(ancho[int(a * n):max(int(b * n), int(a * n) + 1)].mean())
    return {
        "solidez": round(area / casco, 3) if casco > 0 else 1.0,
        "extension": round(area / max(rw * rh, 1.0), 3),
        "asimetria": round(abs(tramo(0.15, 0.35) - tramo(0.65, 0.85)) / max(float(ancho.max()), 1e-9), 3),
    }


def calcular_rasgos(hsv, mascara, med, calibrado, contorno=None):
    """
    Rasgos que describen al producto (los usa el reconocimiento y se guardan como ejemplos):
      hist        histograma de tonos de la piel con color (18 grupos de 10 unidades de hue)
      hist_suave  igual, pero contando también la piel poco saturada (papa, cebolla blanca)
      palidez     fracción de piel casi sin color (blanca, gris, beige)
      oscuro      fracción de piel casi negra (aguacate Hass maduro)
      sat/val     saturación (de la piel con color) y brillo medianos (0-255)
      sat_global  saturación mediana de toda la piel (para productos pálidos)
      alarg       eje mayor / eje menor de la elipse equivalente (momentos de segundo orden)
      curvatura   flecha / cuerda del eje (0 = recto; banano ≈ 0.1-0.3)
      solidez, extension, asimetria   forma de la silueta (ver rasgos_forma)
      diam_cm     grosor (perpendicular al eje); solo es fiable si la cámara está calibrada
    """
    if contorno is None:
        cs, _ = cv2.findContours(mascara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        contorno = max(cs, key=cv2.contourArea)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    interior = cv2.erode(mascara, k, iterations=2) > 0
    if not interior.any():
        interior = mascara > 0
    H, S, V = (hsv[..., i][interior] for i in range(3))
    util = (S > 45) & (V > 40)
    suave = (S > 15) & (V > 40)
    hist180 = np.bincount(H[util], minlength=180)[:180] / max(1, int(util.sum()))
    hist180_suave = np.bincount(H[suave], minlength=180)[:180] / max(1, int(suave.sum()))
    m = cv2.moments(mascara, binaryImage=True)
    mu20, mu02, mu11 = m["mu20"], m["mu02"], m["mu11"]
    raiz = np.sqrt(((mu20 - mu02) / 2) ** 2 + mu11 ** 2)
    l1, l2 = (mu20 + mu02) / 2 + raiz, (mu20 + mu02) / 2 - raiz
    grupos = lambda h: [round(float(v), 4) for v in h.reshape(18, 10).sum(axis=1)]
    return {
        "hist": grupos(hist180),
        "hist_suave": grupos(hist180_suave),
        "palidez": round(float(((S <= 45) & (V > 40)).mean()), 3),
        "oscuro": round(float((V <= 40).mean()), 3),
        "sat": round(float(np.median(S[util])) if util.any() else float(np.median(S)), 1),
        "sat_global": round(float(np.median(S[V > 40])) if (V > 40).any() else 0.0, 1),
        "val": round(float(np.median(V)), 1),
        "alarg": round(float(np.sqrt(l1 / max(l2, 1e-9))), 3),
        "curvatura": round(float(med["curvatura"]), 3),
        **rasgos_forma(contorno, med),
        "diam_cm": round(float(med["grosor_cm"]), 2),
        "calibrado": bool(calibrado),
        "_hist180": hist180, "_hist180_suave": hist180_suave,
    }


def _cerca(v, rango, escala):
    """1 dentro del rango; cae suavemente (gaussiana) al alejarse."""
    lo, hi = rango
    d = max(lo - v, 0, v - hi)
    return float(np.exp(-(d / escala) ** 2))


def _forma_extra(rasgos, g):
    """asimetría × extensión × solidez: solo cuentan si la ficha (o la variante) los define."""
    f = 1.0
    for campo, escala in (("asimetria", 0.08), ("extension", 0.04), ("solidez", 0.04)):
        if g(campo) and campo in rasgos:
            f *= _cerca(rasgos[campo], g(campo), escala)
    return f


def _puntajes_reglas(rasgos):
    """
    puntaje = color × forma × curvatura × viveza × brillo × palidez × oscuro × tamaño
              × (asimetría × extensión × solidez, si la ficha los usa)
    (cada factor entre 0 y 1; vale 1 dentro del rango de la ficha).
    """
    puntajes = {}
    for i, p in enumerate(PRODUCTOS):
        for v in p.variantes or ([{}] if p.colores else []):
            g = lambda campo: v.get(campo, getattr(p, campo))
            h = rasgos["_hist180_suave"] if g("palido") else rasgos["_hist180"]
            peso = np.zeros(180)
            for h0, h1, w in g("colores"):
                peso[h0:h1 + 1] = np.maximum(peso[h0:h1 + 1], w)
            color = float((h * peso).sum())
            # tolerancia proporcional: 1.05 vs 1.15 es mucha diferencia; 4.0 vs 4.5, poca
            forma = _cerca(rasgos["alarg"], g("alargamiento"), 0.05 * rasgos["alarg"] ** 2)
            curva = _cerca(rasgos["curvatura"], g("curvatura"), 0.03) if g("curvatura") else 1.0
            # en productos pálidos la saturación se mide en toda la piel (no solo en la parte con color)
            viveza = _cerca(rasgos["sat_global"] if g("palido") else rasgos["sat"], g("saturacion"), 35)
            luz = _cerca(rasgos["val"], g("brillo"), 35)
            pal = _cerca(rasgos["palidez"], g("palidez"), 0.15)
            osc = _cerca(rasgos["oscuro"], g("oscuro"), 0.15)
            # El tamaño ayuda pero NO veta: si la escala no corresponde a la distancia actual
            # (calibró a otra altura, celular en la mano) el diámetro sale mal.
            tam = (0.4 + 0.6 * _cerca(rasgos["diam_cm"], g("diametro"), 1.0)
                   if rasgos["calibrado"] else 1.0)
            total = color * forma * curva * viveza * luz * pal * osc * tam * _forma_extra(rasgos, g)
            puntajes[i] = max(puntajes.get(i, 0.0), total)
    return puntajes


def _suavizar_hist(h):
    h = np.asarray(h, float)
    h = 0.5 * h + 0.25 * np.roll(h, 1) + 0.25 * np.roll(h, -1)      # el tono es circular (rojo = 0 = 179)
    return h / max(h.sum(), 1e-9)


def _hellinger(a, b):
    ha, hb = _suavizar_hist(a), _suavizar_hist(b)
    return float(np.sqrt(max(0.0, 1 - float(np.sqrt(ha * hb).sum()))))


def distancia_rasgos(a, b):
    """
    Qué tan distintos son dos productos (0 = idénticos). Se usa con los ejemplos enseñados.
    Los rasgos que falten en un ejemplo antiguo simplemente no se comparan.
    """
    d = _hellinger(a["hist"], b["hist"])                                 # distancia de Hellinger
    if "hist_suave" in a and "hist_suave" in b:
        d += 0.5 * _hellinger(a["hist_suave"], b["hist_suave"])
    d += abs(a["sat"] - b["sat"]) / 255 + 0.5 * abs(a["val"] - b["val"]) / 255
    d += 2.0 * abs(np.log(a["alarg"] / b["alarg"])) + abs(a["palidez"] - b["palidez"])
    for campo, peso in (("curvatura", 2.0), ("oscuro", 1.0), ("asimetria", 1.5), ("extension", 3.0), ("solidez", 3.0)):
        if campo in a and campo in b:
            d += peso * abs(a[campo] - b[campo])
    if a.get("calibrado") and b.get("calibrado") and a["diam_cm"] > 0 and b["diam_cm"] > 0:
        d += abs(np.log(a["diam_cm"] / b["diam_cm"]))
    return float(d)


def _vecino(rasgos, ejemplos, umbral):
    """Vecino más cercano: (índice, candidatos, distancia) si el mejor ejemplo está a menos de umbral."""
    mejor_por_producto = {}
    for e in ejemplos:
        i = e["producto"]
        d = distancia_rasgos(rasgos, e["rasgos"])
        if i not in mejor_por_producto or d < mejor_por_producto[i]:
            mejor_por_producto[i] = d
    orden = sorted(mejor_por_producto.items(), key=lambda kv: kv[1])
    if not orden or orden[0][1] >= umbral:
        return None
    cand = [(PRODUCTOS[i].nombre, round(max(0.0, 1 - d / umbral), 2)) for i, d in orden[:3]]
    return orden[0][0], cand, round(orden[0][1], 3)


def reconocer(rasgos, ejemplos=None, tabla=True):
    """
    Decide qué producto es.
      1) Si hay EJEMPLOS enseñados y alguno se parece lo suficiente (vecino más cercano),
         gana ese: aprende las frutas y la luz reales del usuario.
      2) Si se parece mucho a una de las 16 fotos de la TABLA de colores (entrenamiento base), esa.
      3) Si no, REGLAS: el perfil de cada ficha (productos.py), ajustado con esas mismas fotos.
      4) Si nada coincide: "Genérico".
    Devuelve (índice, info) con el método usado y los 3 mejores candidatos (para explicar la decisión).
    """
    for metodo, lista, umbral in (("ejemplos", ejemplos, UMBRAL_EJEMPLO),
                                  ("tabla", EJEMPLOS_TABLA if tabla else None, UMBRAL_TABLA)):
        if lista:
            v = _vecino(rasgos, lista, umbral)
            if v:
                return v[0], {"metodo": metodo, "candidatos": v[1], "distancia": v[2]}

    puntajes = _puntajes_reglas(rasgos)
    total = sum(puntajes.values()) + 0.05
    orden = sorted(puntajes.items(), key=lambda kv: kv[1], reverse=True)
    cand = [(PRODUCTOS[i].nombre, round(v / total, 2)) for i, v in orden[:3]]
    mejor, valor = orden[0]
    if valor < 0.25:
        return I_GENERICO, {"metodo": "reglas", "candidatos": cand, "motivo": "ningún perfil coincide"}
    return mejor, {"metodo": "reglas", "candidatos": cand}


def madurez(hsv, interior, dano, producto):
    """% de la superficie sana cuyo color está en el rango 'maduro' del producto."""
    if not producto.rangos_maduro:
        return None
    sano = (interior > 0) & (dano == 0) & (hsv[..., 1] > 50)
    tonos = hsv[..., 0][sano]
    if tonos.size == 0:
        return None
    en_rango = np.zeros(tonos.shape, bool)
    for h0, h1 in producto.rangos_maduro:
        en_rango |= (tonos >= h0) & (tonos <= h1)
    return 100.0 * en_rango.mean()


def clasificar(producto, dano_pct, madurez_pct, diametro_cm, largo_cm=0.0):
    if dano_pct >= producto.dano_descarte:
        estado = "DESCARTE"
    elif dano_pct >= producto.dano_regular:
        estado = "REGULAR"
    else:
        estado = "BUENO"
    if madurez_pct is not None and madurez_pct < producto.madurez_min and estado == "BUENO":
        estado = "INMADURO"
    medida = largo_cm if producto.calibre_por == "largo" else diametro_cm
    calibre = "-"
    for nombre, minimo in producto.calibres:
        if medida >= minimo:
            calibre = nombre
            break
    return estado, calibre


# ---------------------------------------------------------------- proceso completo
def analizar(frame, producto, px_por_cm, fondo=None, sensibilidad=50, calibrado=False, ejemplos=None):
    """
    Proceso completo sobre un cuadro de la cámara.
    producto:  una ficha de PRODUCTOS, o None para reconocerlo automáticamente.
    calibrado: True si px_por_cm viene de una calibración real (entonces el tamaño ayuda a reconocer).
    ejemplos:  [{"producto": índice, "rasgos": {...}}] enseñados por el usuario (opcional).
    """
    mascara, contorno = segmentar(frame, fondo, sensibilidad)
    if mascara is None:
        return None
    girada, Minv, desp, angulo = alinear(mascara, contorno)
    med = calculo.medir(girada, px_por_cm)
    if med is None:
        return None

    color = balance_blancos(frame, mascara)          # colores sin el tinte de la luz
    hsv = cv2.cvtColor(color, cv2.COLOR_BGR2HSV)
    rasgos = calcular_rasgos(hsv, mascara, med, calibrado, contorno)
    i_rec, info = reconocer(rasgos, ejemplos)
    rasgos.pop("_hist180")
    rasgos.pop("_hist180_suave")
    automatico = producto is None
    if automatico:
        producto = PRODUCTOS[i_rec]

    if producto.lamina_cm > 0:
        # Hoja (espinaca): no es un sólido de revolución. Es una lámina delgada de grosor e:
        # V = ∫∫ e dA = e · ∫(f - g)dx  (el área entre curvas por el grosor).
        e = producto.lamina_cm
        med.update({"volumen_cm3": med["area_cm2"] * e, "metodo_volumen": "lamina", "lamina_cm": e,
                    "convergencia": [(n, a, a * e) for n, a, _ in med["convergencia"]]})
    elif producto.eje_curvo or (rasgos["alarg"] >= 1.8 and rasgos["curvatura"] >= 0.03):
        # Eje curvo (banano, o cualquier producto alargado y curvo): largo = longitud de arco,
        # grosor perpendicular a la curva y volumen con discos perpendiculares al eje.
        med.update({"volumen_cm3": med["volumen_curvo_cm3"], "largo_cm": med["largo_arco_cm"],
                    "diametro_cm": med["grosor_cm"], "convergencia": med["convergencia_curvo"],
                    "metodo_volumen": "curvo"})

    dano, interior, hsv = detectar_danos(color, mascara, producto)
    px_producto = cv2.countNonZero(mascara)
    px_dano = cv2.countNonZero(dano)
    dano_pct = 100.0 * px_dano / px_producto
    mad = madurez(hsv, interior, dano, producto)
    estado, calibre = clasificar(producto, dano_pct, mad, med["diametro_cm"], med["largo_cm"])

    med.update({
        "mascara": mascara, "contorno": contorno, "dano": dano,
        "Minv": Minv, "desplazamiento": desp, "angulo": angulo,
        "area_dano_cm2": px_dano / px_por_cm ** 2,     # suma doble de Riemann: cada píxel = (1/k)² cm²
        "dano_pct": dano_pct, "madurez_pct": mad,
        "peso_g": med["volumen_cm3"] * producto.densidad,
        "estado": estado, "calibre": calibre, "producto": producto.nombre,
        "producto_id": PRODUCTOS.index(producto), "automatico": automatico,
        "reconocido_id": i_rec, "reconocimiento": info, "rasgos": rasgos,
        "colores": colores_dominantes(color, mascara),
    })
    return med
