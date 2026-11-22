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
import numpy as np

import calculo

COLOR_ESTADO = {"BUENO": "#1a9850", "REGULAR": "#f39c12", "INMADURO": "#2e86c1", "DESCARTE": "#c0392b"}


def generar(imagen_bgr, r, ruta, n_rect=16):
    x, f, g, rad = r["x_cm"], r["f_cm"], r["g_cm"], r["r_cm"]
    L = r["largo_cm"]
    s = 1.0 / r["px_por_cm"]

    fig = plt.figure(figsize=(17, 10))
    gs = fig.add_gridspec(2, 3, hspace=0.32, wspace=0.25)

    # 1. Captura
    ax = fig.add_subplot(gs[0, 0])
    ax.imshow(cv2.cvtColor(imagen_bgr, cv2.COLOR_BGR2RGB))
    ax.set_title("Captura de la cámara", fontsize=12)
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
    ax.set_title(r"Área entre curvas  $A=\int_a^b[f(x)-g(x)]\,dx$" +
                 f"\nA = {r['area_cm2']:.2f} cm²   ({n_rect} rectángulos de Riemann dibujados)", fontsize=11)
    ax.set_xlabel("x (cm)")
    ax.set_ylabel("y (cm)")
    ax.set_aspect("equal")
    ax.legend(fontsize=8, loc="lower right")
    ax.grid(alpha=0.3)

    # 3. Sólido de revolución 3D
    ax = fig.add_subplot(gs[0, 2], projection="3d")
    paso = max(1, len(x) // 80)
    X, T = np.meshgrid(x[::paso], np.linspace(0, 2 * np.pi, 40))
    R = np.tile(rad[::paso], (40, 1))
    ax.plot_surface(X, R * np.cos(T), R * np.sin(T), cmap="YlOrRd", alpha=0.85, linewidth=0)
    ax.set_title(r"Sólido de revolución  $V=\pi\int_a^b r(x)^2\,dx$" +
                 f"\nV = {r['volumen_cm3']:.1f} cm³", fontsize=11)
    ax.set_xlabel("x (cm)")
    lim = max(L / 2, rad.max())
    ax.set_ylim(-lim, lim)
    ax.set_zlim(-lim, lim)
    ax.set_box_aspect((L, 2 * lim, 2 * lim))

    # 4. Método de discos (vista lateral)
    ax = fig.add_subplot(gs[1, 0])
    for i in range(n_rect):
        xm = (i + 0.5) * dx
        ri = np.interp(xm, x, rad)
        ax.add_patch(Rectangle((i * dx, -ri), dx, 2 * ri, fc="#f5b041", ec="#7e5109", alpha=0.6))
    ax.plot(x, rad, color="#c0392b", lw=2, label="r(x) = [f(x) − g(x)] / 2")
    ax.plot(x, -rad, color="#c0392b", lw=2)
    ax.axhline(0, color="k", lw=0.8, ls="--", label="eje de revolución")
    ax.set_title(f"Método de discos: {n_rect} discos de grosor Δx = {dx:.2f} cm\n"
                 r"cada disco aporta $\pi\,r(x_i)^2\,\Delta x$", fontsize=11)
    ax.set_xlabel("x (cm)")
    ax.set_ylabel("r (cm)")
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
        ("Largo (eje mayor)", f"{r['largo_cm']:.2f} cm"),
        ("Diámetro máximo", f"{r['diametro_cm']:.2f} cm"),
        ("Área de la silueta", f"{r['area_cm2']:.2f} cm²"),
        ("Volumen (discos)", f"{r['volumen_cm3']:.1f} cm³"),
        ("Peso estimado", f"{r['peso_g']:.0f} g"),
        ("Área dañada", f"{r['area_dano_cm2']:.2f} cm²  ({r['dano_pct']:.1f} %)"),
        ("Madurez (color)", mad),
        ("Calibre", r["calibre"]),
        ("Escala", f"{r['px_por_cm']:.1f} px/cm"),
    ]
    for i, (k, v) in enumerate(filas):
        y = 0.95 - i * 0.075
        ax.text(0.0, y, k, fontsize=12, color="#444", transform=ax.transAxes)
        ax.text(0.55, y, v, fontsize=12, weight="bold", transform=ax.transAxes)
    ax.text(0.5, 0.06, r["estado"], fontsize=26, weight="bold", ha="center", color="white",
            transform=ax.transAxes,
            bbox=dict(boxstyle="round,pad=0.4", fc=COLOR_ESTADO.get(r["estado"], "#555")))

    fig.suptitle("Inspección automatizada de productos agrícolas — Cálculo Integral (áreas y volúmenes)",
                 fontsize=15, weight="bold")
    fig.savefig(ruta, dpi=100, bbox_inches="tight")
    plt.close(fig)
    return ruta
