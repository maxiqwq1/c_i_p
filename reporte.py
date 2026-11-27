"""
Genera la lámina de evidencia (PNG) con las gráficas de cálculo integral
para cada captura: área entre curvas, método de discos, sólido de
revolución y convergencia de las sumas de Riemann.
"""
import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np

import calculo
import frescura
import vision
from productos import PRODUCTOS

COLOR_ESTADO = {"BUENO": "#1a9850", "REGULAR": "#f39c12", "INMADURO": "#2e86c1", "DESCARTE": "#c0392b"}


def colores_tabla(ax, r, y=0.2):
    """Colores medidos en la piel (barra, cada uno con su %) junto a la paleta de la tabla de colores."""
    medidos = r.get("colores") or []
    paleta = next((p.paleta for p in PRODUCTOS if p.nombre == r["producto"]), [])
    if not medidos and not paleta:
        return
    ax.text(0.0, y, "Colores", fontsize=12, color="#444", transform=ax.transAxes, va="center")
    ax.text(0.65, y + 0.04, "medidos", fontsize=8, color="#777", transform=ax.transAxes, ha="center", va="center")
    if paleta:
        ax.text(0.885, y + 0.04, "tabla", fontsize=8, color="#777", transform=ax.transAxes, ha="center", va="center")
    x0, ancho, alto = 0.55, 0.2, 0.045
    for c in medidos:                                     # barra: cada color con su % de la piel
        w = ancho * c["pct"] / 100
        ax.add_patch(Rectangle((x0, y - alto / 2), w, alto, transform=ax.transAxes, fc=c["hex"], ec="none"))
        x0 += w
    if paleta:                                            # paleta de la tabla (círculos, como en la tabla)
        ax.scatter([0.81 + i * 0.05 for i in range(len(paleta))], [y] * len(paleta), s=150, c=paleta,
                   transform=ax.transAxes, edgecolors="white", linewidths=0.6, clip_on=False)


def generar(imagen_bgr, r, ruta, n_rect=16):
    x, f, g, rad = r["x_cm"], r["f_cm"], r["g_cm"], r["r_cm"]
    L = r["x_cm"][-1] + 0.5 / r["px_por_cm"]           # largo sobre el eje x (cuerda)
    s = 1.0 / r["px_por_cm"]
    curvo = r.get("metodo_volumen") == "curvo"
    lamina = r.get("metodo_volumen") == "lamina"          # hoja (espinaca): V = área × grosor
    e = r.get("lamina_cm", 0.0)

    fig = plt.figure(figsize=(17, 10))
    gs = fig.add_gridspec(2, 3, hspace=0.32, wspace=0.25)

    # 1. Captura (con zoom al producto)
    ax = fig.add_subplot(gs[0, 0])
    if "contorno" in r:
        x0, y0, x1, y1 = vision.caja_enfoque(r["contorno"], imagen_bgr.shape, margen=0.3, proporcion=4 / 3)
        imagen_bgr = imagen_bgr[y0:y1, x0:x1]
    ax.imshow(cv2.cvtColor(imagen_bgr, cv2.COLOR_BGR2RGB))
    modo = " (reconocido automáticamente)" if r.get("automatico") else ""
    ax.set_title(f"Captura: {r['producto']}{modo}", fontsize=12)
    ax.axis("off")

    # 2. Área entre curvas con rectángulos de Riemann
    ax = fig.add_subplot(gs[0, 1])
    ax.fill_between(x, g, f, color="#f5b041", alpha=0.45, label="Área = ∫(f − g)dx")
    ax.plot(x, f, color="#c0392b", lw=2, label="f(x) borde superior")
    ax.plot(x, g, color="#2471a3", lw=2, label="g(x) borde inferior")
    dx = L / n_rect
    for i in range(n_rect):
        xm = (i + 0.5) * dx
        fi, gi = np.interp(xm, x, f), np.interp(xm, x, g)
        ax.add_patch(Rectangle((i * dx, gi), dx, fi - gi, fill=False, ec="#555", lw=0.8))
    if curvo:
        ax.plot(x, r["c_cm"], color="#117a65", lw=1.6, ls="--", label="eje curvo c(x) = [f(x) + g(x)] / 2")
    ax.set_title(r"Área entre curvas  $A=\int_a^b[f(x)-g(x)]\,dx$" +
                 f"\nA = {r['area_cm2']:.2f} cm²   ({n_rect} rectángulos de Riemann dibujados)", fontsize=11)
    ax.set_xlabel("x (cm)")
    ax.set_ylabel("y (cm)")
    ax.set_aspect("equal")
    ax.legend(fontsize=7 if curvo else 8, loc="best", framealpha=0.85)
    ax.grid(alpha=0.3)

    # 3. Sólido de revolución 3D (con eje curvo: tubo que sigue la curva)
    ax = fig.add_subplot(gs[0, 2], projection="3d")
    paso = max(1, len(x) // 80)
    T = np.linspace(0, 2 * np.pi, 40)[:, None]
    if lamina:
        ev = max(e, 0.04 * L)                            # grosor exagerado para que se vea
        X = np.concatenate([x, x[::-1]])
        Y = np.concatenate([f, g[::-1]])
        for z in (-ev / 2, ev / 2):
            ax.add_collection3d(Poly3DCollection([list(zip(X, Y, np.full_like(X, z)))],
                                                 facecolor="#8bc34a", edgecolor="#33691e", alpha=0.8))
        ax.set_xlim(0, L)
        ax.set_title(r"Lámina delgada  $V=e\cdot A$" +
                     f"\nV = {r['area_cm2']:.1f} cm² × {e:.2f} cm = {r['volumen_cm3']:.1f} cm³", fontsize=11)
        lim = max(L / 2, float(np.abs(Y).max()))
    elif curvo:
        c, dc, rp = r["c_cm"][::paso], r["dc"][::paso], r["r_perp_cm"][::paso]
        sec = np.sqrt(1 + dc ** 2)
        Nx, Ny = -dc / sec, 1 / sec                     # normal a la curva en el plano
        X = x[::paso] + rp * np.cos(T) * Nx
        Y = c + rp * np.cos(T) * Ny
        Z = rp * np.sin(T)
        ax.plot_surface(X, Y, Z, cmap="YlOrRd", alpha=0.85, linewidth=0)
        ax.plot(x, r["c_cm"], 0 * x, color="#117a65", lw=1.5)
        ax.set_title(r"Sólido sobre eje curvo  $V=\pi\int r(s)^2\,ds$" +
                     f"\nV = {r['volumen_cm3']:.1f} cm³", fontsize=11)
        lim = max(L / 2, float(np.abs(Y).max()), float(rp.max()))
    else:
        X = np.tile(x[::paso], (40, 1))
        R = np.tile(rad[::paso], (40, 1))
        ax.plot_surface(X, R * np.cos(T), R * np.sin(T), cmap="YlOrRd", alpha=0.85, linewidth=0)
        ax.set_title(r"Sólido de revolución  $V=\pi\int_a^b r(x)^2\,dx$" +
                     f"\nV = {r['volumen_cm3']:.1f} cm³", fontsize=11)
        lim = max(L / 2, rad.max())
    ax.set_xlabel("x (cm)")
    ax.set_ylim(-lim, lim)
    ax.set_zlim(-lim, lim)
    ax.set_box_aspect((L, 2 * lim, 2 * lim))

    # 4. Método de discos (vista lateral); con eje curvo, discos perpendiculares a la curva
    ax = fig.add_subplot(gs[1, 0])
    if lamina:
        for i in range(n_rect):
            xm = (i + 0.5) * dx
            fi, gi = np.interp(xm, x, f), np.interp(xm, x, g)
            ax.add_patch(Rectangle((i * dx, gi), dx, fi - gi, fc="#aed581", ec="#33691e", alpha=0.6))
        ax.plot(x, f, color="#c0392b", lw=1.5, label="bordes f(x), g(x)")
        ax.plot(x, g, color="#c0392b", lw=1.5)
        ax.set_title(f"La hoja es una lámina: {n_rect} franjas de ancho Δx = {dx:.2f} cm\n"
                     r"cada franja aporta $e\,[f(x_i)-g(x_i)]\,\Delta x$" + f"   (grosor e = {e:.2f} cm)", fontsize=10)
        ax.set_ylabel("y (cm)")
    elif curvo:
        sc = r["s_cm"]                                   # posición sobre el arco
        Ls = r["largo_cm"]                               # longitud de arco
        ds = Ls / n_rect
        for i in range(n_rect):
            si = (i + 0.5) * ds
            xi, ci = np.interp(si, sc, x), np.interp(si, sc, r["c_cm"])
            di, ri = np.interp(si, sc, r["dc"]), np.interp(si, sc, r["r_perp_cm"])
            th = np.arctan(di)
            t, n = np.array([np.cos(th), np.sin(th)]), np.array([-np.sin(th), np.cos(th)])
            esquina = np.array([xi, ci]) - ds / 2 * t - ri * n
            ax.add_patch(Rectangle(esquina, ds, 2 * ri, angle=np.degrees(th),
                                   fc="#f5b041", ec="#7e5109", alpha=0.6))
        ax.plot(x, f, color="#c0392b", lw=1.5, label="bordes f(x), g(x)")
        ax.plot(x, g, color="#c0392b", lw=1.5)
        ax.plot(x, r["c_cm"], color="#117a65", lw=1.5, ls="--", label="eje curvo c(x)")
        ax.set_title(f"Discos perpendiculares al eje curvo: {n_rect} discos de grosor Δs = {ds:.2f} cm\n"
                     r"$L=\int_a^b\sqrt{1+c'(x)^2}\,dx$" + f" = {Ls:.2f} cm   " +
                     r"$r_\perp=\frac{f-g}{2}\cos\theta$", fontsize=10)
        ax.set_ylabel("y (cm)")
    else:
        for i in range(n_rect):
            xm = (i + 0.5) * dx
            ri = np.interp(xm, x, rad)
            ax.add_patch(Rectangle((i * dx, -ri), dx, 2 * ri, fc="#f5b041", ec="#7e5109", alpha=0.6))
        ax.plot(x, rad, color="#c0392b", lw=2, label="r(x) = [f(x) − g(x)] / 2")
        ax.plot(x, -rad, color="#c0392b", lw=2)
        ax.axhline(0, color="k", lw=0.8, ls="--", label="eje de revolución")
        ax.set_title(f"Método de discos: {n_rect} discos de grosor Δx = {dx:.2f} cm\n"
                     r"cada disco aporta $\pi\,r(x_i)^2\,\Delta x$", fontsize=11)
        ax.set_ylabel("r (cm)")
    ax.set_xlabel("x (cm)")
    ax.set_aspect("equal")
    ax.legend(fontsize=8, loc="lower right")
    ax.grid(alpha=0.3)

    # 5. Convergencia de las sumas de Riemann
    ax = fig.add_subplot(gs[1, 1])
    ns = [c[0] for c in r["convergencia"]]
    areas = [c[1] for c in r["convergencia"]]
    vols = [c[2] for c in r["convergencia"]]
    ax.plot(ns, areas, "o-", color="#d35400", label="Área (cm²)")
    ax.axhline(r["area_cm2"], color="#d35400", ls="--", lw=1)
    ax.set_xscale("log", base=2)
    ax.set_xlabel("n (número de rectángulos / discos)")
    ax.set_ylabel("Área (cm²)", color="#d35400")
    ax2 = ax.twinx()
    ax2.plot(ns, vols, "s-", color="#1f618d", label="Volumen (cm³)")
    ax2.axhline(r["volumen_cm3"], color="#1f618d", ls="--", lw=1)
    ax2.set_ylabel("Volumen (cm³)", color="#1f618d")
    ax.set_title("Convergencia de las sumas de Riemann\n"
                 f"(línea punteada: Δx = 1 píxel = {s:.3f} cm)", fontsize=11)
    ax.grid(alpha=0.3)

    # 6. Resultados
    ax = fig.add_subplot(gs[1, 2])
    ax.axis("off")
    mad = "no aplica" if r["madurez_pct"] is None else f"{r['madurez_pct']:.0f} %"
    filas = [
        ("Producto", r["producto"]),
        ("Largo (sobre el arco)" if curvo else "Largo (eje mayor)", f"{r['largo_cm']:.2f} cm"),
        ("Grosor máximo" if curvo else "Ancho máximo" if lamina else "Diámetro máximo", f"{r['diametro_cm']:.2f} cm"),
        ("Área de la silueta", f"{r['area_cm2']:.2f} cm²"),
        ("Volumen (lámina)" if lamina else "Volumen (eje curvo)" if curvo else "Volumen (discos)",
         f"{r['volumen_cm3']:.1f} cm³"),
        ("Área dañada", f"{r['area_dano_cm2']:.2f} cm²  ({r['dano_pct']:.1f} %)"),
        ("Madurez (color)", mad),
        ("Calibre", r["calibre"]),
        ("Escala", f"{r['px_por_cm']:.1f} px/cm"),
    ]
    red = r.get("frescura")
    if red:   # la red neuronal decide el estado junto con el daño (ver frescura.py)
        filas.append(("Red neuronal", frescura.texto(red)))
    if r.get("estado_calculo") and r["estado_calculo"] != r["estado"]:
        filas.append(("Solo con el daño", r["estado_calculo"]))
    paso = 0.075 if len(filas) <= 10 else 0.065
    for i, (k, v) in enumerate(filas):
        y = 0.95 - i * paso
        ax.text(0.0, y, k, fontsize=12, color="#444", transform=ax.transAxes)
        color = ({"Fresco": "#1e8449", "Dudoso": "#b9770e", "Podrido": "#c0392b"}.get(red["veredicto"])
                 if k == "Red neuronal" else "#777" if k == "Solo con el daño" else "black")
        ax.text(0.55, y, v, fontsize=12, weight="bold", color=color, transform=ax.transAxes)
    colores_tabla(ax, r)
    ax.text(0.5, 0.04, r["estado"], fontsize=26, weight="bold", ha="center", color="white",
            transform=ax.transAxes,
            bbox=dict(boxstyle="round,pad=0.4", fc=COLOR_ESTADO.get(r["estado"], "#555")))

    fig.suptitle("Inspección automatizada de productos agrícolas — Cálculo Integral (áreas y volúmenes)",
                 fontsize=15, weight="bold")
    fig.savefig(ruta, dpi=100, bbox_inches="tight")
    plt.close(fig)
    return ruta
