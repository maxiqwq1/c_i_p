"""
INSPECCIÓN EN VIVO CON LA CÁMARA DEL PC

Apunte la cámara al producto: se detecta solo, en cualquier parte de la
imagen y sobre cualquier fondo liso o de un color distinto al producto
(mesa, mantel, hoja...). El programa:
  - reconoce qué producto es (o use 1-7 para elegirlo a mano),
  - hace zoom sobre él,
  - calcula en tiempo real área (∫(f−g)dx), volumen (π∫r²dx), peso, % de daño,
    madurez y estado,
  - y cuando el producto se queda quieto ~1 s guarda la captura automáticamente.

Teclas:
  0          reconocer el producto automáticamente (predeterminado)
  1-7        elegir el producto a mano (ver productos.py)
  E          enseñar: guarda la fruta actual como ejemplo del producto elegido con 1-7
             (si confunde productos, 2-3 ejemplos de cada uno lo corrigen; se guardan en entrenamiento.json)
  A          activar/desactivar la captura automática
  Z          activar/desactivar el zoom al producto
  C o ESPACIO  capturar a mano: foto + lámina de cálculo + fila en resultados.csv
  K          calibrar escala con una tarjeta (carnet / tarjeta de crédito: 8.56 cm)
  B          capturar el fondo vacío (para productos pálidos); otra vez = desactivar
  D          mostrar/ocultar los discos
  M          ver la máscara (lo que el programa considera producto)
  Q o ESC    salir
"""
import csv
import json
import os
import sys
import time
from datetime import datetime

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

import reporte
import vision
from productos import PRODUCTOS

CARPETA = os.path.dirname(os.path.abspath(__file__))
ARCHIVO_CAL = os.path.join(CARPETA, "calibracion.json")
ARCHIVO_EJ = os.path.join(CARPETA, "entrenamiento.json")
CARPETA_CAPT = os.path.join(CARPETA, "capturas")
INDICE_CAMARA = int(sys.argv[1]) if len(sys.argv) > 1 else 0
REFERENCIA_CM = 8.56          # lado largo de una tarjeta tipo carnet o crédito
PX_POR_CM_DEFECTO = 16.0      # valor aproximado si nunca se ha calibrado
T_QUIETO = 1.2                # segundos quieto para la captura automática
VENTANA = "Inspeccion de productos agricolas"
COLOR_ESTADO = {"BUENO": (80, 175, 40), "REGULAR": (20, 160, 245),
                "INMADURO": (195, 135, 45), "DESCARTE": (45, 50, 200)}

_fuentes = {}


def fuente(tam):
    if tam not in _fuentes:
        for nombre in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
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


def cargar_ejemplos():
    try:
        with open(ARCHIVO_EJ, encoding="utf-8") as fh:
            return [e for e in json.load(fh) if 0 <= e["producto"] < len(PRODUCTOS)]
    except (OSError, ValueError, KeyError, TypeError):
        return []


def guardar_ejemplos(ejemplos):
    with open(ARCHIVO_EJ, "w", encoding="utf-8") as fh:
        json.dump(ejemplos, fh, ensure_ascii=False)


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


# ---------------------------------------------------------------- seguimiento del producto
class Seguimiento:
    """
    Reconocimiento estable (votación entre cuadros) y detección de "producto quieto"
    para la captura automática. Una "presencia" dura mientras el producto siga a la vista.
    """

    def __init__(self):
        self.reiniciar()
        self.ultima_det = 0.0

    def reiniciar(self):
        self.votos, self.muestras, self.progreso, self.capturada = {}, [], 0.0, None

    def producto_estable(self):
        if not self.votos:
            return None, 0.0
        i = max(self.votos, key=self.votos.get)
        return (i, self.votos[i]) if self.votos[i] >= 0.6 else (None, self.votos[i])

    def sin_producto(self, ahora):
        if ahora - self.ultima_det > 1.0:
            self.reiniciar()

    def actualizar(self, r, forma, ahora, producto_fijo):
        """Registra una detección; devuelve True si toca capturar automáticamente."""
        self.ultima_det = ahora
        for i in self.votos:
            self.votos[i] *= 0.7
        self.votos[r["reconocido_id"]] = self.votos.get(r["reconocido_id"], 0) + 0.3

        x, y, w, h = cv2.boundingRect(r["contorno"])
        m = (ahora, r["area_cm2"], (x + w / 2) / forma[1], (y + h / 2) / forma[0])
        self.muestras = [s for s in self.muestras if ahora - s[0] < 3] + [m]
        c = self.capturada
        if c and (abs(m[1] - c[1]) / c[1] > 0.3 or np.hypot(m[2] - c[2], m[3] - c[3]) > 0.15):
            self.reiniciar()                       # otro producto en el mismo lugar
            self.muestras = [m]
        desde = ahora
        for s in reversed(self.muestras):
            if abs(s[1] - m[1]) / m[1] > 0.04 or np.hypot(s[2] - m[2], s[3] - m[3]) > 0.03:
                break
            desde = s[0]
        self.progreso = min(1.0, (ahora - desde) / T_QUIETO)
        reconocido = producto_fijo is not None or self.producto_estable()[0] is not None
        if self.progreso >= 1 and reconocido and self.capturada is None:
            self.capturada = m
            return True
        return False


# ---------------------------------------------------------------- dibujo
def caja_objetivo(r, forma, zoom):
    H, W = forma[:2]
    if not zoom or r is None:
        return np.array([0, 0, W, H], float)
    x0, y0, x1, y1 = vision.caja_enfoque(r["contorno"], forma, margen=0.55, proporcion=W / H)
    if x1 - x0 < 0.3 * W:                      # zoom máximo ~3x
        cx, cy, w = (x0 + x1) / 2, (y0 + y1) / 2, 0.3 * W
        x0, x1 = np.clip([cx - w / 2, cx + w / 2], 0, W)
        y0, y1 = np.clip([cy - w * H / W / 2, cy + w * H / W / 2], 0, H)
    return np.array([x0, y0, x1, y1], float)


def aplicar_zoom(img, caja, original):
    """Recorta la caja y la amplía al tamaño completo; agrega un minimapa con la vista entera."""
    H, W = img.shape[:2]
    x0, y0, x1, y1 = caja.astype(int)
    if (x1 - x0) > 0.95 * W:
        return img
    vista = cv2.resize(img[y0:y1, x0:x1], (W, H), interpolation=cv2.INTER_LINEAR)
    mw, mh = int(W * 0.22), int(H * 0.22)
    mini = cv2.resize(original, (mw, mh), interpolation=cv2.INTER_AREA)
    cv2.rectangle(mini, (int(x0 * mw / W), int(y0 * mh / H)), (int(x1 * mw / W), int(y1 * mh / H)), (90, 210, 255), 2)
    vista[H - mh - 10:H - 10, W - mw - 10:W - 10] = mini
    cv2.rectangle(vista, (W - mw - 11, H - mh - 11), (W - 10, H - 10), (255, 255, 255), 1)
    return vista


def indicador(vista, seg, auto, capturando):
    if not auto:
        return vista
    txt = ("Capturando…" if capturando else "Capturado — ponga otro producto" if seg.capturada
           else "Manténgalo quieto…" if seg.progreso > 0.05 else "Producto detectado")
    cv2.rectangle(vista, (10, 10), (370, 48), (0, 0, 0), -1)
    if not seg.capturada:
        cv2.rectangle(vista, (10, 44), (10 + int(360 * seg.progreso), 48), (90, 210, 255), -1)
    return escribir(vista, [(txt, (22, 16), 20, (130, 220, 60) if seg.capturada else (255, 255, 255))])


def panel(H, r, suav, producto_fijo, seg, px_por_cm, calibrado, fondo_activo, auto, zoom):
    p = np.full((H, 460, 3), 28, np.uint8)
    blanco, gris, amarillo = (255, 255, 255), (170, 170, 170), (80, 220, 255)
    if producto_fijo is not None:
        titulo, sub = producto_fijo.nombre, "elegido a mano (0 = automático)"
    else:
        i, v = seg.producto_estable()
        titulo = PRODUCTOS[i].nombre if i is not None else ("Reconociendo…" if r is not None else "—")
        sub = f"reconocido automáticamente ({v * 100:.0f} %)" if i is not None else "modo automático"
    textos = [(titulo, (18, 12), 28, amarillo), (sub, (18, 46), 16, gris)]
    if r is not None:            # por qué: candidatos y método (para revisar confusiones)
        rec = r["reconocimiento"]
        cand = " · ".join(f"{n} {v * 100:.0f}%" for n, v in rec["candidatos"][:2])
        metodo = "sus ejemplos" if rec["metodo"] == "ejemplos" else "reglas"
        textos.append((f"Por qué ({metodo}): {cand}", (18, 66), 14, gris))
    y = 90
    if r is None:
        textos.append(("Buscando producto…", (18, y), 19, gris))
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
            textos.append((t, (18, y + i * 31), 21, blanco))
        color = COLOR_ESTADO.get(r["estado"], (90, 90, 90))
        cv2.rectangle(p, (18, y + 228), (18 + 240, y + 274), color, -1)
        textos.append((r["estado"], (32, y + 232), 28, blanco))
    y = 380
    escala = f"Escala: {px_por_cm:.1f} px/cm" + ("" if calibrado else "  (SIN CALIBRAR: K)")
    textos.append((escala, (18, y), 17, gris if calibrado else (60, 120, 255)))
    textos.append((f"Captura automática: {'SÍ' if auto else 'no'} (A)    Zoom: {'sí' if zoom else 'no'} (Z)",
                   (18, y + 24), 17, gris))
    if fondo_activo:
        textos.append(("Modo fondo capturado (B para quitar)", (18, y + 48), 17, gris))
    ayuda = ["0 automático · 1-7 elegir · E enseñar", "C / Espacio  capturar a mano", "K  calibrar con tarjeta",
             "B  fondo vacío   D  discos   M  máscara", "Q / Esc  salir"]
    for i, t in enumerate(ayuda):
        textos.append((t, (18, H - 26 - (len(ayuda) - i) * 24), 17, gris))
    return escribir(p, textos)


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


def guardar_captura(frame, r):
    os.makedirs(CARPETA_CAPT, exist_ok=True)
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    cv2.imwrite(os.path.join(CARPETA_CAPT, f"foto_{marca}.png"), frame)
    ruta_rep = reporte.generar(vision.anotar(frame, r), r, os.path.join(CARPETA_CAPT, f"reporte_{marca}.png"))
    ruta_csv = os.path.join(CARPETA_CAPT, "resultados.csv")
    nuevo = not os.path.exists(ruta_csv)
    with open(ruta_csv, "a", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        if nuevo:
            w.writerow(["fecha", "producto", "largo_cm", "diametro_cm", "area_cm2", "volumen_cm3",
                        "peso_g", "area_dano_cm2", "dano_pct", "madurez_pct", "calibre", "estado", "automatico"])
        mad = "" if r["madurez_pct"] is None else f"{r['madurez_pct']:.1f}"
        w.writerow([marca, r["producto"], f"{r['largo_cm']:.2f}", f"{r['diametro_cm']:.2f}",
                    f"{r['area_cm2']:.2f}", f"{r['volumen_cm3']:.1f}", f"{r['peso_g']:.0f}",
                    f"{r['area_dano_cm2']:.2f}", f"{r['dano_pct']:.1f}", mad, r["calibre"], r["estado"],
                    "sí" if r["automatico"] else "no"])
    return ruta_rep


def mostrar_lamina(ruta):
    lamina = cv2.imread(ruta)
    if lamina is not None:
        esc = min(1.0, 1400 / lamina.shape[1])
        cv2.imshow("Reporte de calculo", cv2.resize(lamina, None, fx=esc, fy=esc))


# ---------------------------------------------------------------- programa principal
def main():
    cap = abrir_camara(INDICE_CAMARA)
    if not cap.isOpened():
        print(f"No se pudo abrir la cámara {INDICE_CAMARA}. Revise que esté conectada o pruebe: python camara.py 1")
        return

    px_por_cm, calibrado = cargar_calibracion()
    producto_fijo = None                  # None = reconocer automáticamente
    fondo = None
    ver_discos, ver_mascara, auto, zoom = True, False, True, True
    suav, caja, ultimo_r = None, None, None
    seg = Seguimiento()
    ejemplos = cargar_ejemplos()

    cv2.namedWindow(VENTANA, cv2.WINDOW_NORMAL)
    cv2.createTrackbar("Sensibilidad", VENTANA, 50, 100, lambda v: None)
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
        ahora = time.monotonic()
        sens = cv2.getTrackbarPos("Sensibilidad", VENTANA)

        estable, _ = seg.producto_estable()
        prod = producto_fijo if producto_fijo is not None else (PRODUCTOS[estable] if estable is not None else None)
        try:
            r = vision.analizar(frame, prod, px_por_cm, fondo, sens, calibrado, ejemplos)
        except cv2.error:
            r = None
        if r is not None:
            r["automatico"] = producto_fijo is None
            suav = suavizar(suav, r)
            capturar_ya = seg.actualizar(r, frame.shape, ahora, producto_fijo)
        else:
            suav, capturar_ya = None, False
            seg.sin_producto(ahora)

        # vista: anotaciones + zoom suave al producto
        if ver_mascara:
            m = r["mascara"] if r is not None else np.zeros(frame.shape[:2], np.uint8)
            base = cv2.cvtColor(m, cv2.COLOR_GRAY2BGR)
        else:
            base = vision.anotar(frame, r, ver_discos) if r is not None else frame.copy()
        if r is not None:
            ultimo_r = r
        reciente = r if r is not None else (ultimo_r if ahora - seg.ultima_det < 1.0 else None)
        objetivo = caja_objetivo(reciente, frame.shape, zoom)
        caja = objetivo if caja is None else caja + 0.25 * (objetivo - caja)
        vista = aplicar_zoom(base, caja, base)
        if r is not None:
            vista = indicador(vista, seg, auto, capturar_ya and auto)
        lado = panel(vista.shape[0], r, suav, producto_fijo, seg, px_por_cm, calibrado, fondo is not None, auto, zoom)
        cv2.imshow(VENTANA, np.hstack([vista, lado]))

        if capturar_ya and auto:
            ruta = guardar_captura(frame, r)
            print(f"Captura automática: {r['producto']} · {r['estado']} -> {ruta}")
            mostrar_lamina(ruta)

        tecla = cv2.waitKey(1) & 0xFF
        if tecla in (ord("q"), ord("Q"), 27):
            break
        if tecla == ord("0"):
            producto_fijo = None
            seg.reiniciar()
        elif ord("1") <= tecla <= ord("9") and tecla - ord("1") < len(PRODUCTOS):
            producto_fijo = PRODUCTOS[tecla - ord("1")]
            suav = None
            seg.reiniciar()
        elif tecla in (ord("a"), ord("A")):
            auto = not auto
            seg.capturada = None
        elif tecla in (ord("e"), ord("E")):
            if r is None:
                print("Enseñar: no hay producto a la vista.")
            elif producto_fijo is None:
                print("Enseñar: primero diga qué producto es con las teclas 1-7, y luego pulse E.")
            else:
                ejemplos.append({"producto": PRODUCTOS.index(producto_fijo), "rasgos": r["rasgos"]})
                guardar_ejemplos(ejemplos)
                n = sum(e["producto"] == PRODUCTOS.index(producto_fijo) for e in ejemplos)
                print(f"Ejemplo guardado: {producto_fijo.nombre} ({n}). Para volver al modo automático pulse 0.")
        elif tecla in (ord("z"), ord("Z")):
            zoom = not zoom
        elif tecla in (ord("d"), ord("D")):
            ver_discos = not ver_discos
        elif tecla in (ord("m"), ord("M")):
            ver_mascara = not ver_mascara
        elif tecla in (ord("b"), ord("B")):
            fondo = None if fondo is not None else frame.copy()
            seg.reiniciar()
            print("Fondo capturado." if fondo is not None else "Fondo desactivado.")
        elif tecla in (ord("k"), ord("K")):
            _, cont = vision.segmentar(frame, fondo, sens)
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
                ruta = guardar_captura(frame, r)
                print(f"Captura guardada: {ruta}")
                mostrar_lamina(ruta)

        if cv2.getWindowProperty(VENTANA, cv2.WND_PROP_VISIBLE) < 1:
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
