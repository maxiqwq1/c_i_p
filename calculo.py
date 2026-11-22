"""
Núcleo matemático: CÁLCULO INTEGRAL aplicado a la silueta del producto.

La cámara entrega una máscara binaria (1 = producto, 0 = fondo) ya alineada
para que el eje mayor del producto quede horizontal (eje x).

Para cada columna de píxeles x se obtienen:
    f(x) = borde superior de la silueta
    g(x) = borde inferior de la silueta

1) ÁREA ENTRE CURVAS
        A = ∫[a,b] ( f(x) - g(x) ) dx

2) VOLUMEN POR EL MÉTODO DE DISCOS (sólido de revolución)
   Se supone que el producto es simétrico alrededor de su eje mayor,
   así que al girar la silueta se obtiene el sólido. El radio es
        r(x) = ( f(x) - g(x) ) / 2
        V = π ∫[a,b] r(x)² dx

3) EJE CURVO (banano y otros productos alargados y curvos)
   El eje ya no es una recta sino la LÍNEA MEDIA de la silueta
        c(x) = ( f(x) + g(x) ) / 2      (suavizada con un polinomio)
   Su LONGITUD DE ARCO es el largo real del producto:
        L = ∫[a,b] √( 1 + c'(x)² ) dx            ds = √(1 + c'(x)²) dx
   Los discos se ponen PERPENDICULARES al eje curvo. Si la recta tangente
   forma un ángulo θ con el eje x (tan θ = c'(x)), el grosor vertical
   f - g mide 2r / cos θ, así que el radio perpendicular es
        r⊥(x) = ( f(x) - g(x) ) / 2 · cos θ = r(x) / √(1 + c'(x)²)
   y el volumen (discos de grosor ds a lo largo de la curva) es
        V = π ∫ r⊥(s)² ds = π ∫[a,b] r⊥(x)² √(1 + c'(x)²) dx
   Si el producto es recto, c'(x) = 0 y todo se reduce al método de discos normal.

4) SUMAS DE RIEMANN
   La imagen es discreta: cada columna de píxeles es un rectángulo de
   ancho Δx = 1 px. Por eso la integral se calcula como suma de Riemann:
        A ≈ Σ ( f(x_i) - g(x_i) ) Δx        V ≈ Σ π r(x_i)² Δx
   Con n rectángulos más anchos se ve cómo la suma CONVERGE a la integral
   cuando n crece (Δx -> 0).

Conversión de unidades: si la escala es k píxeles por cm,
   longitud (cm) = px / k     área (cm²) = px² / k²     volumen (cm³) = px³ / k³
"""
import numpy as np


def perfiles(mascara_alineada):
    """Devuelve las curvas f(x), g(x) de la silueta (en píxeles, eje y hacia arriba)."""
    m = mascara_alineada > 0
    alto = m.shape[0]
    columnas = np.flatnonzero(m.any(axis=0))
    if columnas.size < 3:
        return None
    sub = m[:, columnas]
    fila_sup = sub.argmax(axis=0)                       # primera fila con producto
    fila_inf = alto - 1 - sub[::-1].argmax(axis=0)      # última fila con producto

    # Coordenadas matemáticas: y crece hacia arriba y el eje del sólido queda en y = 0
    f = -fila_sup.astype(float)
    g = -(fila_inf + 1).astype(float)
    eje = np.median((f + g) / 2)
    f -= eje
    g -= eje
    x = (columnas - columnas[0]) + 0.5                  # centro de cada columna, x inicia en 0
    return {"x": x, "f": f, "g": g, "eje_px": float(eje),
            "columnas": columnas, "fila_sup": fila_sup, "fila_inf": fila_inf}


def linea_media(x, f, g, grado=3):
    """
    Eje curvo: c(x) = [f(x) + g(x)] / 2 suavizado con un polinomio de grado 3 por
    mínimos cuadrados (las columnas más gruesas pesan más; las puntas delgadas, menos).
    Devuelve c(x) y su derivada c'(x).
    """
    h = f - g
    c = (f + g) / 2
    if len(x) < 8:
        return np.full_like(x, np.average(c, weights=np.maximum(h, 1e-9))), np.zeros_like(x)
    xm, xs = x.mean(), max(x.std(), 1e-9)
    u = (x - xm) / xs
    coef = np.polyfit(u, c, grado, w=np.sqrt(np.maximum(h, 1e-9)))
    return np.polyval(coef, u), np.polyval(np.polyder(coef), u) / xs


def flecha_relativa(x, c):
    """Curvatura del eje: flecha (máxima separación entre la curva y la cuerda) / cuerda."""
    p0, p1 = np.array([x[0], c[0]]), np.array([x[-1], c[-1]])
    cuerda = float(np.linalg.norm(p1 - p0))
    if cuerda <= 0:
        return 0.0
    d = np.abs((p1[0] - p0[0]) * (c - p0[1]) - (p1[1] - p0[1]) * (x - p0[0])) / cuerda
    return float(d.max() / cuerda)


def integral_riemann(x, y, n=None, regla="medio"):
    """
    ∫[0, L] y(x) dx mediante una suma de Riemann.
      n = None  -> un rectángulo por columna de píxeles (Δx = 1 px), máxima resolución.
      n = entero -> n rectángulos de ancho Δx = L / n, evaluados en el punto medio,
                    izquierdo o derecho de cada subintervalo.
    """
    if n is None:
        return float(np.sum(y))                          # Σ y_i · 1
    L = x[-1] + 0.5
    dx = L / n
    i = np.arange(n)
    if regla == "izquierda":
        xs = i * dx
    elif regla == "derecha":
        xs = (i + 1) * dx
    else:
        xs = (i + 0.5) * dx
    ys = np.interp(xs, x, y)
    return float(np.sum(ys) * dx)


def medir(mascara_alineada, px_por_cm, n_convergencia=(2, 4, 8, 16, 32, 64, 128)):
    """
    Aplica las integrales de área y volumen y devuelve todo en cm.
    Calcula las dos versiones del volumen: eje recto (método de discos clásico) y
    eje curvo (vision.analizar elige cuál usar según el producto y su curvatura).
    """
    p = perfiles(mascara_alineada)
    if p is None:
        return None
    x, f, g = p["x"], p["f"], p["g"]
    h = f - g                  # altura de la silueta en cada x  ->  f(x) - g(x)
    r = h / 2.0                # radio del disco en cada x
    s = 1.0 / px_por_cm        # cm por píxel

    area_px = integral_riemann(x, h)                     # ∫ (f - g) dx
    vol_px = np.pi * integral_riemann(x, r ** 2)         # π ∫ r² dx

    # eje curvo: c(x), ds/dx = √(1 + c'²), radio perpendicular r⊥ = r / √(1 + c'²)
    c, dc = linea_media(x, f, g)
    dsdx = np.sqrt(1 + dc ** 2)
    r_perp = r / dsdx
    integrando_curvo = r_perp ** 2 * dsdx                # π ∫ r⊥² ds = π ∫ r⊥² √(1+c'²) dx
    vol_curvo_px = np.pi * integral_riemann(x, integrando_curvo)
    arco_px = integral_riemann(x, dsdx)                  # L = ∫ √(1 + c'²) dx

    convergencia, convergencia_curvo = [], []
    for n in n_convergencia:
        a_n = integral_riemann(x, h, n) * s ** 2
        convergencia.append((n, a_n, np.pi * integral_riemann(x, r ** 2, n) * s ** 3))
        convergencia_curvo.append((n, a_n, np.pi * integral_riemann(x, integrando_curvo, n) * s ** 3))

    p.update({
        "x_cm": x * s, "f_cm": f * s, "g_cm": g * s, "r_cm": r * s,
        "area_cm2": area_px * s ** 2,
        "volumen_cm3": vol_px * s ** 3,
        "largo_cm": (x[-1] + 0.5) * s,
        "diametro_cm": float(h.max()) * s,
        "convergencia": convergencia,
        "px_por_cm": px_por_cm,
        # eje curvo
        "c_px": c, "dc": dc, "c_cm": c * s, "r_perp_cm": r_perp * s,
        "s_cm": (np.cumsum(dsdx) - dsdx / 2) * s,         # posición sobre el arco
        "volumen_curvo_cm3": vol_curvo_px * s ** 3,
        "largo_arco_cm": arco_px * s,
        "grosor_cm": float((h / dsdx).max()) * s,
        "curvatura": flecha_relativa(x, c),
        "convergencia_curvo": convergencia_curvo,
        "metodo_volumen": "recto",
    })
    return p
