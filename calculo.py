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

3) SUMAS DE RIEMANN
   La imagen es discreta: cada columna de píxeles es un rectángulo de
   ancho Δx = 1 px. Por eso la integral se calcula como suma de Riemann:
        A ≈ Σ ( f(x_i) - g(x_i) ) Δx        V ≈ Σ π r(x_i)² Δx
   Con n rectángulos más anchos se ve cómo la suma CONVERGE a la integral
   cuando n crece (Δx -> 0).

Conversión de unidades: si la escala es k píxeles por cm,
   área (cm²) = área (px²) / k²       volumen (cm³) = volumen (px³) / k³
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
    return {"x": x, "f": f, "g": g,
            "columnas": columnas, "fila_sup": fila_sup, "fila_inf": fila_inf}


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
    """Aplica las integrales de área y volumen y devuelve todo en cm."""
    p = perfiles(mascara_alineada)
    if p is None:
        return None
    x, f, g = p["x"], p["f"], p["g"]
    h = f - g                  # altura de la silueta en cada x  ->  f(x) - g(x)
    r = h / 2.0                # radio del disco en cada x
    s = 1.0 / px_por_cm        # cm por píxel

    area_px = integral_riemann(x, h)                     # ∫ (f - g) dx
    vol_px = np.pi * integral_riemann(x, r ** 2)         # π ∫ r² dx

    convergencia = []
    for n in n_convergencia:
        a_n = integral_riemann(x, h, n) * s ** 2
        v_n = np.pi * integral_riemann(x, r ** 2, n) * s ** 3
        convergencia.append((n, a_n, v_n))

    p.update({
        "x_cm": x * s, "f_cm": f * s, "g_cm": g * s, "r_cm": r * s,
        "area_cm2": area_px * s ** 2,
        "volumen_cm3": vol_px * s ** 3,
        "largo_cm": (x[-1] + 0.5) * s,
        "diametro_cm": float(h.max()) * s,
        "convergencia": convergencia,
        "px_por_cm": px_por_cm,
    })
    return p
