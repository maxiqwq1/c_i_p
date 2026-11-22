"""
Visión por computador: encuentra el producto en la imagen (en cualquier
lugar y sobre cualquier fondo), lo reconoce, lo alinea, detecta manchas
(daño), estima madurez por color y clasifica.
"""
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
    _, _, centros = cv2.kmeans(muestra, k, None, criterio, 2, cv2.KMEANS_PP_CENTERS)
    return centros


def _distancia_fondo(lab, centros):
    """Para cada píxel: distancia (en color) al tono de fondo más parecido."""
    d = np.full(lab.shape[:2], np.inf, np.float32)
    for c in centros:
        d = np.minimum(d, np.sqrt(((lab - c) ** 2).sum(axis=2)))
    return d


def _elegir_objeto(mascara):
    """
    De todas las regiones candidatas elige la que más parece un producto:
    tamaño razonable, forma compacta (convexa), que no toque el borde y
    que esté cerca del centro. Así se ignoran la mesa, sombras y objetos cortados.
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
        if solidez < 0.8:
            continue
        (_, _), (rw, rh), _ = cv2.minAreaRect(c)
        if max(rw, rh) > 4 * max(min(rw, rh), 1):      # muy alargado: lápiz, cuchillo, borde de mesa
            continue
        p = c.reshape(-1, 2)
        en_borde = np.mean((p[:, 0] <= 2) | (p[:, 1] <= 2) | (p[:, 0] >= W - 3) | (p[:, 1] >= H - 3))
        if en_borde > 0.05:
            continue
        m = cv2.moments(c)
        cx, cy = m["m10"] / m["m00"], m["m01"] / m["m00"]
        d_centro = np.hypot((cx - W / 2) / (W / 2), (cy - H / 2) / (H / 2)) / np.sqrt(2)
        puntaje = np.sqrt(frac) * solidez ** 3 * (1 - 0.6 * d_centro)
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
    Segmentos para dibujar sobre el video: n_discos líneas verticales (los discos
    del método de discos) y el eje de revolución, en coordenadas de la imagen.
    """
    cols, sup, inf = r["columnas"], r["fila_sup"], r["fila_inf"]
    idx = np.linspace(0, len(cols) - 1, n_discos + 2).astype(int)[1:-1]
    discos = [_a_lista(a_imagen([(cols[i] + 0.5, sup[i]), (cols[i] + 0.5, inf[i] + 1)],
                                r["Minv"], r["desplazamiento"])) for i in idx]
    fila_eje = np.median((sup + inf + 1) / 2)
    eje = _a_lista(a_imagen([(cols[0], fila_eje), (cols[-1] + 1, fila_eje)],
                            r["Minv"], r["desplazamiento"]))
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
        cv2.line(vista, tuple(eje[0]), tuple(eje[1]), (255, 255, 0), 1, cv2.LINE_AA)
    return vista


# ---------------------------------------------------------------- calidad
def detectar_danos(frame, mascara, producto):
    """Manchas = píxeles del interior mucho más oscuros que el brillo típico del producto."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    area = cv2.countNonZero(mascara)
    diam = np.sqrt(4 * area / np.pi)
    k = max(3, int(0.08 * diam))                 # se ignora el borde (sombra natural)
    interior = cv2.erode(mascara, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    if cv2.countNonZero(interior) == 0:
        return np.zeros_like(mascara), interior, hsv
    V = hsv[..., 2]
    brillo_tipico = np.median(V[interior > 0])
    dano = ((V < producto.factor_oscuro * brillo_tipico) & (interior > 0)).astype(np.uint8) * 255
    dano = cv2.morphologyEx(dano, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    return dano, interior, hsv


def reconocer(hsv, mascara, alargamiento):
    """
    Reconoce el producto comparando la silueta con el perfil de cada ficha:
      color  = fracción de la piel con tonos típicos del producto (ponderada)
      forma  = qué tan cerca está largo/diámetro del rango del producto
      viveza = saturación mediana dentro del rango del producto
    puntaje = color × forma × viveza (0-1). Devuelve (índice, {nombre: puntaje}).
    Si ningún perfil supera 0.35, o el producto es pálido, se usa "Genérico".
    """
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    interior = cv2.erode(mascara, k, iterations=2) > 0
    S = hsv[..., 1][interior]
    V = hsv[..., 2][interior]
    util = (S > 50) & (V > 40)
    i_generico = len(PRODUCTOS) - 1
    if S.size == 0 or util.mean() < 0.3:
        return i_generico, {}
    tonos = hsv[..., 0][interior][util].astype(int)
    s_med = float(np.median(S[util]))

    def cerca(v, rango, escala):
        lo, hi = rango
        d = max(lo - v, 0, v - hi)
        return float(np.exp(-(d / escala) ** 2))

    puntajes = {}
    for i, p in enumerate(PRODUCTOS):
        if not p.colores:
            continue
        peso = np.zeros(180)
        for h0, h1, w in p.colores:
            peso[h0:h1 + 1] = np.maximum(peso[h0:h1 + 1], w)
        color = float(peso[tonos].mean())
        puntajes[i] = color * cerca(alargamiento, p.alargamiento, 0.12) * cerca(s_med, p.saturacion, 35)
    mejor = max(puntajes, key=puntajes.get)
    nombres = {PRODUCTOS[i].nombre: round(v, 3) for i, v in puntajes.items()}
    return (mejor if puntajes[mejor] >= 0.35 else i_generico), nombres


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


def clasificar(producto, dano_pct, madurez_pct, diametro_cm):
    if dano_pct >= producto.dano_descarte:
        estado = "DESCARTE"
    elif dano_pct >= producto.dano_regular:
        estado = "REGULAR"
    else:
        estado = "BUENO"
    if madurez_pct is not None and madurez_pct < producto.madurez_min and estado == "BUENO":
        estado = "INMADURO"
    calibre = "-"
    for nombre, dmin in producto.calibres:
        if diametro_cm >= dmin:
            calibre = nombre
            break
    return estado, calibre


# ---------------------------------------------------------------- proceso completo
def analizar(frame, producto, px_por_cm, fondo=None, sensibilidad=50):
    """
    Proceso completo sobre un cuadro de la cámara.
    producto: una ficha de PRODUCTOS, o None para reconocerlo automáticamente.
    """
    mascara, contorno = segmentar(frame, fondo, sensibilidad)
    if mascara is None:
        return None
    girada, Minv, desp, angulo = alinear(mascara, contorno)
    med = calculo.medir(girada, px_por_cm)
    if med is None:
        return None

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    alarg = med["largo_cm"] / max(med["diametro_cm"], 1e-9)
    i_rec, puntajes = reconocer(hsv, mascara, alarg)
    automatico = producto is None
    if automatico:
        producto = PRODUCTOS[i_rec]

    dano, interior, hsv = detectar_danos(frame, mascara, producto)
    px_producto = cv2.countNonZero(mascara)
    px_dano = cv2.countNonZero(dano)
    dano_pct = 100.0 * px_dano / px_producto
    mad = madurez(hsv, interior, dano, producto)
    estado, calibre = clasificar(producto, dano_pct, mad, med["diametro_cm"])

    med.update({
        "mascara": mascara, "contorno": contorno, "dano": dano,
        "Minv": Minv, "desplazamiento": desp, "angulo": angulo,
        "area_dano_cm2": px_dano / px_por_cm ** 2,     # suma doble de Riemann: cada píxel = (1/k)² cm²
        "dano_pct": dano_pct, "madurez_pct": mad,
        "peso_g": med["volumen_cm3"] * producto.densidad,
        "estado": estado, "calibre": calibre, "producto": producto.nombre,
        "producto_id": PRODUCTOS.index(producto), "automatico": automatico,
        "reconocido_id": i_rec, "reconocimiento": puntajes, "alargamiento": alarg,
    })
    return med
