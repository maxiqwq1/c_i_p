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

5) TEOREMA DE FUBINI (función fubini)
   Una integral doble se calcula como dos integrales seguidas, y el ORDEN no cambia el
   resultado. El área y el volumen se comprueban así por dos o tres caminos distintos.

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


def tramos(fila):
    """Tramos [inicio, fin) de valores True seguidos en un vector booleano."""
    d = np.diff(np.concatenate([[0], fila.astype(np.int8), [0]]))
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)))


def fubini(med, n_capas=1000):
    """
    TEOREMA DE FUBINI: si R es una región del plano,
        ∬_R F dA = ∫ [ ∫ F dy ] dx = ∫ [ ∫ F dx ] dy
    se puede integrar primero en y o primero en x, y el resultado es el mismo. La integral
    de adentro recorre un CORTE de la región: una columna (x fija) o una fila (y fija).

    1) ÁREA (F = 1) de la región R entre g(x) y f(x):
         columnas primero:  ∫ₐᵇ [ ∫_{g(x)}^{f(x)} dy ] dx = ∫ₐᵇ (f − g) dx    (lo que mide el programa)
         filas primero:     ∫_c^d [ largo del corte horizontal en y ] dy
       En un producto curvo (banano) una fila puede cruzar la silueta en 2 tramos: la integral
       de adentro es la SUMA de los tramos, no "derecha − izquierda".

    2) VOLUMEN en el plano (x, ρ): la región es 0 ≤ ρ ≤ r(x), y cada punto aporta 2πρ (el
       anillo de radio ρ que se forma al girar). Con eje curvo, x pasa a ser s (sobre el arco)
       y r pasa a ser r⊥.
         ρ primero (DISCOS):             ∫ₐᵇ [ ∫₀^{r(x)} 2πρ dρ ] dx = π ∫ₐᵇ r(x)² dx
         x primero (CAPAS CILÍNDRICAS):  ∫₀^R [ ∫_{r(x) ≥ ρ} 2πρ dx ] dρ = ∫₀^R 2πρ ℓ(ρ) dρ
       ℓ(ρ) = largo de la parte del producto que es más gruesa que ρ. Se suman n_capas capas.

    3) VOLUMEN como integral doble sobre la SILUETA: sobre cada punto de la foto el sólido
       tiene un grosor 2√(r² − v²), con v = distancia al eje. Entonces
         V = ∬ 2√(r² − v²) dA = ∫ₐᵇ [ ∫_{−r}^{r} 2√(r² − v²) dv ] dx = ∫ₐᵇ π r(x)² dx
       (la integral de adentro es el área del círculo, π r²). Se calcula como suma doble de
       Riemann con cuadritos de 1 píxel × 1 píxel.

    med: resultado de medir() con "metodo_volumen" ya decidido. Devuelve todo en cm.
    """
    s = 1.0 / med["px_por_cm"]
    x, f, g = med["x"], med["f"], med["g"]
    h = f - g

    # ---- 1) ÁREA: la misma región R, sumada por columnas y por filas
    col = med["columnas"] - med["columnas"][0]
    sup = np.full(col[-1] + 1, np.inf)
    inf = np.full(col[-1] + 1, -np.inf)
    sup[col], inf[col] = med["fila_sup"], med["fila_inf"]
    filas = np.arange(med["fila_sup"].min(), med["fila_inf"].max() + 1)
    dentro = (filas[:, None] >= sup[None, :]) & (filas[:, None] <= inf[None, :])   # R en píxeles
    largo_fila = dentro.sum(axis=1)                                   # ∫ dx de cada fila
    izq = dentro.argmax(axis=1)
    der = dentro.shape[1] - dentro[:, ::-1].argmax(axis=1)
    der_izq = np.where(largo_fila > 0, der - izq, 0)                  # "derecha − izquierda"
    y_fila = -(filas + 0.5) - med["eje_px"]                           # centro de cada fila (eje y arriba)
    L = x[-1] + 0.5

    # fila de ejemplo: si alguna cruza la silueta en 2 o más tramos GRANDES separados por un hueco
    # grande (banano), la de ese tipo donde mejor se ven; si no, una fila en la mitad de arriba.
    # (Los pedacitos del borde, el tallo o un escalón de la sombra no cuentan.)
    minimo = max(3.0, 0.1 * L)
    grandes = [[b - a for a, b in tramos(fila) if b - a >= minimo] for fila in dentro]
    hueco = der_izq - largo_fila
    partida = np.array([len(t) >= 2 for t in grandes]) & (hueco >= minimo)
    if partida.any():
        cand = np.flatnonzero(partida)
        i_fila = cand[int(np.argmax([hueco[i] * min(grandes[i]) for i in cand]))]
    else:
        i_fila = int(np.argmin(np.abs(y_fila - 0.45 * f.max())))
    i_col = int(np.argmin(np.abs(x - 0.4 * L)))                       # columna de ejemplo

    # ---- 2) y 3) VOLUMEN: posición sobre el eje, radio y ancho de cada columna
    curvo = med.get("metodo_volumen") == "curvo"
    if curvo:
        dsdx = np.sqrt(1 + med["dc"] ** 2)
        R, w = (h / 2) / dsdx, dsdx                                   # r⊥ y ds de cada columna
        pos = np.cumsum(dsdx) - dsdx / 2                               # s sobre el arco
    else:
        R, w, pos = h / 2, np.ones_like(h), x

    res = {
        "area_columnas": float(h.sum()) * s ** 2,
        "area_filas": float(largo_fila.sum()) * s ** 2,
        "area_der_izq": float(der_izq.sum()) * s ** 2,
        "fila_partida": bool(partida.any()),                          # la fila de ejemplo tiene 2+ tramos
        "fila_n_tramos": len(grandes[i_fila]),
        "fila_y": float(y_fila[i_fila]) * s,
        "fila_tramos": [(a * s, b * s) for a, b in tramos(dentro[i_fila])],
        "col_x": float(x[i_col]) * s, "col_g": float(g[i_col]) * s, "col_f": float(f[i_col]) * s,
        "curvo": curvo, "pos_cm": pos * s, "ancho_cm": w * s, "r_cm": R * s,
        "vol_discos": None, "vol_capas": None, "vol_doble": None,
    }
    if med.get("metodo_volumen") == "lamina":      # una hoja no es un sólido de revolución
        return res

    # discos: primero ρ (integral exacta: πr²), después x
    res["vol_discos"] = float(np.pi * np.sum(R ** 2 * w)) * s ** 3

    # capas: primero x (ℓ(ρ) = Σ anchos donde r ≥ ρ), después ρ con n_capas capas de grosor Δρ
    d_rho = R.max() / n_capas
    rho = (np.arange(n_capas) + 0.5) * d_rho
    orden = np.argsort(R)
    cola = np.concatenate([np.cumsum(w[orden][::-1])[::-1], [0.0]])  # cola[i] = Σ anchos desde i
    ell = cola[np.searchsorted(R[orden], rho, side="left")]
    res["vol_capas"] = float(np.sum(2 * np.pi * rho * ell) * d_rho) * s ** 3

    # integral doble sobre la silueta: cuadritos de 1 px a distancias v = ±0.5, ±1.5, ... del eje
    v = np.arange(0.5, R.max() + 1.0, 1.0)
    grosor = 2 * np.sqrt(np.clip(R[None, :] ** 2 - v[:, None] ** 2, 0, None))
    res["vol_doble"] = float(2 * np.sum(grosor * w[None, :])) * s ** 3    # 2: arriba y abajo del eje
    return res
