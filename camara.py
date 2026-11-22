"""
INSPECCIÓN EN VIVO CON LA CÁMARA DEL PC

Ponga el producto sobre un fondo claro y liso (por ejemplo una hoja blanca)
dentro del recuadro guía. El programa calcula en tiempo real:
  área (∫(f−g)dx), volumen (π∫r²dx), peso estimado, % de daño, madurez y estado.

Teclas:
  1-6        elegir producto (ver productos.py)
  K          calibrar escala con una tarjeta (carnet / tarjeta de crédito: 8.56 cm)
  B          capturar el fondo vacío (para productos pálidos); otra vez = desactivar
  D          mostrar/ocultar los discos
  M          ver la máscara (lo que el programa considera producto)
  C o ESPACIO  capturar: guarda foto + lámina de cálculo + fila en resultados.csv
  Q o ESC    salir
"""
import csv
import json
import os
import sys
from datetime import datetime

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

import reporte
import vision
from productos import PRODUCTOS

CARPETA = os.path.dirname(os.path.abspath(__file__))
ARCHIVO_CAL = os.path.join(CARPETA, "calibracion.json")
CARPETA_CAPT = os.path.join(CARPETA, "capturas")
INDICE_CAMARA = int(sys.argv[1]) if len(sys.argv) > 1 else 0
REFERENCIA_CM = 8.56          # lado largo de una tarjeta tipo carnet o crédito
PX_POR_CM_DEFECTO = 16.0      # valor aproximado si nunca se ha calibrado
VENTANA = "Inspeccion de productos agricolas"
COLOR_ESTADO = {"BUENO": (80, 175, 40), "REGULAR": (20, 160, 245),
                "INMADURO": (195, 135, 45), "DESCARTE": (45, 50, 200)}

_fuentes = {}


def fuente(tam):
    if tam not in _fuentes:
        for nombre in ("segoeui.ttf", "arial.ttf"):
            try:
                _fuentes[tam] = ImageFont.truetype(nombre, tam)
                break
            except OSError:
                continue
        else:
            _fuentes[tam] = ImageFont.load_default()
    return _fuentes[tam]


def escribir(img, textos):
    """Dibuja texto con tildes y símbolos (cm², ∫) usando Pillow. textos: [(texto, (x,y), tamaño, color_bgr)]."""
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    d = ImageDraw.Draw(pil)
    for t, pos, tam, c in textos:
        d.text(pos, t, font=fuente(tam), fill=(c[2], c[1], c[0]))
    return cv2.cvtColor(np.asarray(pil), cv2.COLOR_RGB2BGR)


def cargar_calibracion():
    try:
        with open(ARCHIVO_CAL, encoding="utf-8") as fh:
            return float(json.load(fh)["px_por_cm"]), True
    except (OSError, ValueError, KeyError):
        return PX_POR_CM_DEFECTO, False


def guardar_calibracion(px_por_cm):
    with open(ARCHIVO_CAL, "w", encoding="utf-8") as fh:
        json.dump({"px_por_cm": px_por_cm, "referencia_cm": REFERENCIA_CM,
                   "fecha": datetime.now().isoformat(timespec="seconds")}, fh, indent=2)


def abrir_camara(indice):
    cap = cv2.VideoCapture(indice, cv2.CAP_DSHOW) if os.name == "nt" else cv2.VideoCapture(indice)
    if not cap.isOpened():
        cap = cv2.VideoCapture(indice)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    return cap


def dibujar(frame, r, producto, px_por_cm, calibrado, roi, ver_discos, fondo_activo, suav):
    vista = frame.copy()
    x0, y0, x1, y1 = roi
    cv2.rectangle(vista, (x0, y0), (x1, y1), (200, 200, 200), 1)

    if r is not None:
        # manchas en rojo
        capa = vista.copy()
        capa[r["dano"] > 0] = (0, 0, 255)
        vista = cv2.addWeighted(capa, 0.55, vista, 0.45, 0)
        cv2.drawContours(vista, [r["contorno"]], -1, (0, 255, 0), 2)

        if ver_discos:
            cols, sup, inf = r["columnas"], r["fila_sup"], r["fila_inf"]
            idx = np.linspace(0, len(cols) - 1, 18).astype(int)[1:-1]
            for i in idx:
                p = vision.a_imagen([(cols[i] + 0.5, sup[i]), (cols[i] + 0.5, inf[i] + 1)],
                                    r["Minv"], r["desplazamiento"]).astype(int)
                cv2.line(vista, tuple(p[0]), tuple(p[1]), (0, 220, 255), 1)
            fila_eje = np.median((sup + inf + 1) / 2)
            p = vision.a_imagen([(cols[0], fila_eje), (cols[-1] + 1, fila_eje)],
                                r["Minv"], r["desplazamiento"]).astype(int)
            cv2.line(vista, tuple(p[0]), tuple(p[1]), (255, 255, 0), 1, cv2.LINE_AA)

    # panel lateral de resultados (no tapa el video)
    H = vista.shape[0]
    panel = np.full((H, 440, 3), 28, np.uint8)
    blanco, gris, amarillo = (255, 255, 255), (170, 170, 170), (80, 220, 255)
    textos = [(f"Producto: {producto.nombre}", (18, 14), 26, amarillo)]
    if r is None:
        textos.append(("Coloque el producto dentro del recuadro", (18, 62), 18, gris))
    else:
        mad = "no aplica" if suav["madurez_pct"] is None else f"{suav['madurez_pct']:.0f} %"
        lineas = [
            f"Área  ∫(f−g)dx  = {suav['area_cm2']:.1f} cm²",
            f"Volumen  π∫r²dx = {suav['volumen_cm3']:.0f} cm³",
            f"Peso estimado = {suav['peso_g']:.0f} g",
            f"Largo × diámetro = {suav['largo_cm']:.1f} × {suav['diametro_cm']:.1f} cm",
            f"Daño = {suav['dano_pct']:.1f} %",
            f"Madurez = {mad}",
            f"Calibre: {r['calibre']}",
        ]
        for i, t in enumerate(lineas):
            textos.append((t, (18, 60 + i * 32), 21, blanco))
    y = 300
    escala = f"Escala: {px_por_cm:.1f} px/cm" + ("" if calibrado else "  (SIN CALIBRAR: K)")
    textos.append((escala, (18, y + 60), 17, gris if calibrado else (60, 120, 255)))
    if fondo_activo:
        textos.append(("Modo fondo capturado (B para quitar)", (18, y + 84), 17, gris))
    ayuda = ["1-6  elegir producto", "C / Espacio  capturar lámina", "K  calibrar con tarjeta",
             "B  capturar fondo vacío", "D  discos     M  máscara", "Q / Esc  salir"]
    for i, t in enumerate(ayuda):
        textos.append((t, (18, H - 30 - (len(ayuda) - i) * 24), 17, gris))
    if r is not None:
        color = COLOR_ESTADO.get(r["estado"], (90, 90, 90))
        cv2.rectangle(panel, (18, y), (18 + 240, y + 46), color, -1)
        textos.append((r["estado"], (32, y + 4), 28, blanco))
    panel = escribir(panel, textos)
    return vista, np.hstack([vista, panel])


def suavizar(prev, r, alfa=0.3):
    claves = ("area_cm2", "volumen_cm3", "peso_g", "largo_cm", "diametro_cm", "dano_pct", "madurez_pct")
    nuevo = {}
    for k in claves:
        v = r[k]
        if prev is None or prev.get(k) is None or v is None:
            nuevo[k] = v
        else:
            nuevo[k] = alfa * v + (1 - alfa) * prev[k]
    return nuevo


def guardar_captura(frame, vista, r):
    os.makedirs(CARPETA_CAPT, exist_ok=True)
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    cv2.imwrite(os.path.join(CARPETA_CAPT, f"foto_{marca}.png"), frame)
    ruta_rep = reporte.generar(vista, r, os.path.join(CARPETA_CAPT, f"reporte_{marca}.png"))
    ruta_csv = os.path.join(CARPETA_CAPT, "resultados.csv")
    nuevo = not os.path.exists(ruta_csv)
    with open(ruta_csv, "a", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        if nuevo:
            w.writerow(["fecha", "producto", "largo_cm", "diametro_cm", "area_cm2", "volumen_cm3",
                        "peso_g", "area_dano_cm2", "dano_pct", "madurez_pct", "calibre", "estado"])
        mad = "" if r["madurez_pct"] is None else f"{r['madurez_pct']:.1f}"
        w.writerow([marca, r["producto"], f"{r['largo_cm']:.2f}", f"{r['diametro_cm']:.2f}",
                    f"{r['area_cm2']:.2f}", f"{r['volumen_cm3']:.1f}", f"{r['peso_g']:.0f}",
                    f"{r['area_dano_cm2']:.2f}", f"{r['dano_pct']:.1f}", mad, r["calibre"], r["estado"]])
    return ruta_rep


def main():
    cap = abrir_camara(INDICE_CAMARA)
    if not cap.isOpened():
        print(f"No se pudo abrir la cámara {INDICE_CAMARA}. Pruebe: python camara.py 1")
        return

    px_por_cm, calibrado = cargar_calibracion()
    producto = PRODUCTOS[0]
    fondo = None
    ver_discos, ver_mascara = True, False
    suav = None

    cv2.namedWindow(VENTANA, cv2.WINDOW_NORMAL)
    cv2.createTrackbar("Saturacion min", VENTANA, 60, 255, lambda v: None)
    cv2.createTrackbar("Oscuro max", VENTANA, 70, 255, lambda v: None)
    print(__doc__)

    fallos = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            fallos += 1
            if fallos > 30:
                print("La cámara dejó de enviar imágenes.")
                break
            continue
        fallos = 0
        H, W = frame.shape[:2]
        roi = (int(W * 0.06), int(H * 0.06), int(W * 0.94), int(H * 0.94))
        s_min = cv2.getTrackbarPos("Saturacion min", VENTANA)
        v_osc = cv2.getTrackbarPos("Oscuro max", VENTANA)

        try:
            r = vision.analizar(frame, producto, px_por_cm, fondo, roi, s_min, v_osc)
        except cv2.error:
            r = None
        suav = suavizar(suav, r) if r is not None else None

        if ver_mascara:
            masc, _ = vision.segmentar(frame, fondo, roi, s_min, v_osc)
            vista = cv2.cvtColor(masc if masc is not None else np.zeros((H, W), np.uint8), cv2.COLOR_GRAY2BGR)
            vista = escribir(vista, [("MÁSCARA (M para volver) — ajuste las barras", (20, 20), 22, (80, 220, 255))])
            video_anotado = vista
        else:
            video_anotado, vista = dibujar(frame, r, producto, px_por_cm, calibrado, roi, ver_discos,
                                           fondo is not None, suav)
        cv2.imshow(VENTANA, vista)

        tecla = cv2.waitKey(1) & 0xFF
        if tecla in (ord("q"), ord("Q"), 27):
            break
        if ord("1") <= tecla <= ord("9") and tecla - ord("1") < len(PRODUCTOS):
            producto = PRODUCTOS[tecla - ord("1")]
            suav = None
        elif tecla in (ord("d"), ord("D")):
            ver_discos = not ver_discos
        elif tecla in (ord("m"), ord("M")):
            ver_mascara = not ver_mascara
        elif tecla in (ord("b"), ord("B")):
            fondo = None if fondo is not None else frame.copy()
            print("Fondo capturado." if fondo is not None else "Fondo desactivado.")
        elif tecla in (ord("k"), ord("K")):
            masc, cont = vision.segmentar(frame, fondo, roi, s_min, v_osc)
            if cont is None:
                print("Calibración: no se detectó la tarjeta.")
            else:
                (_, _), (w, h), _ = cv2.minAreaRect(cont)
                px_por_cm, calibrado = max(w, h) / REFERENCIA_CM, True
                guardar_calibracion(px_por_cm)
                print(f"Calibrado: {px_por_cm:.2f} px/cm (lado largo {max(w, h):.0f} px = {REFERENCIA_CM} cm)")
        elif tecla in (ord("c"), ord("C"), ord(" ")):
            if r is None:
                print("No hay producto detectado para capturar.")
            else:
                ruta = guardar_captura(frame, video_anotado, r)
                print(f"Captura guardada: {ruta}")
                lamina = cv2.imread(ruta)
                if lamina is not None:
                    esc = min(1.0, 1400 / lamina.shape[1])
                    cv2.imshow("Reporte de calculo", cv2.resize(lamina, None, fx=esc, fy=esc))

        if cv2.getWindowProperty(VENTANA, cv2.WND_PROP_VISIBLE) < 1:
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
