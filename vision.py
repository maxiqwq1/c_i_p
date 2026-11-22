"""
Visión por computador: separa el producto del fondo, lo alinea, detecta
manchas (daño), estima madurez por color y clasifica.
"""
import cv2
import numpy as np

import calculo


def segmentar(frame, fondo=None, roi=None, s_min=60, v_oscuro=70, diff_min=35):
    """
    Devuelve (mascara_rellena, contorno) del objeto más grande dentro del ROI.

    - Sin fondo capturado: se asume un fondo claro y poco saturado (hoja blanca).
      Es producto todo píxel con color (saturación > s_min) o muy oscuro.
    - Con fondo capturado (tecla B): es producto todo lo que cambió respecto al
      fondo vacío. Sirve para productos pálidos (papa, cebolla, ajo...).
    """
    suave = cv2.GaussianBlur(frame, (5, 5), 0)
    if fondo is not None:
        dif = cv2.absdiff(suave, cv2.GaussianBlur(fondo, (5, 5), 0)).max(axis=2)
        mascara = dif > diff_min
    else:
        hsv = cv2.cvtColor(suave, cv2.COLOR_BGR2HSV)
        S = hsv[..., 1]
        # Umbral adaptativo (Otsu): corta el borde a mitad de camino entre fondo y producto.
        # s_min actúa como piso para que el ruido del fondo no se tome como producto.
        zona = S if roi is None else S[roi[1]:roi[3], roi[0]:roi[2]]
        otsu, _ = cv2.threshold(zona, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        umbral = max(s_min, otsu)
        mascara = (S > umbral) | (hsv[..., 2] < v_oscuro)
    mascara = mascara.astype(np.uint8) * 255

    if roi is not None:
        x0, y0, x1, y1 = roi
        recorte = np.zeros_like(mascara)
        recorte[y0:y1, x0:x1] = mascara[y0:y1, x0:x1]
        mascara = recorte
        area_roi = (x1 - x0) * (y1 - y0)
    else:
        area_roi = mascara.size

    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    mascara = cv2.morphologyEx(mascara, cv2.MORPH_CLOSE, k, iterations=2)
    mascara = cv2.morphologyEx(mascara, cv2.MORPH_OPEN, k)

    contornos, _ = cv2.findContours(mascara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contornos:
        return None, None
    c = max(contornos, key=cv2.contourArea)
    if cv2.contourArea(c) < 0.005 * area_roi:
        return None, None
    rellena = np.zeros_like(mascara)
    cv2.drawContours(rellena, [c], -1, 255, thickness=-1)   # rellena huecos internos
    return rellena, c


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


def analizar(frame, producto, px_por_cm, fondo=None, roi=None, s_min=60, v_oscuro=70):
    """Proceso completo sobre un cuadro de la cámara."""
    mascara, contorno = segmentar(frame, fondo, roi, s_min, v_oscuro)
    if mascara is None:
        return None
    girada, Minv, desp, angulo = alinear(mascara, contorno)
    med = calculo.medir(girada, px_por_cm)
    if med is None:
        return None

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
    })
    return med
