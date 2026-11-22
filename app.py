"""
VERSIÓN WEB (para publicar en Railway u otro servidor)

La cámara la abre el NAVEGADOR (celular o PC de quien visita la página) y
envía cada cuadro a este servidor, que aplica exactamente los mismos
cálculos que la aplicación de escritorio (calculo.py, vision.py, reporte.py).

Local:   python app.py            ->  http://localhost:8000
Railway: gunicorn app:app          (ver railway.json y gunicorn.conf.py)
"""
import base64
import io
import json
import os

import cv2
import numpy as np
from flask import Flask, jsonify, request, send_file, send_from_directory

import reporte
import vision
from productos import PRODUCTOS

CARPETA_WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
REFERENCIA_CM = 8.56          # lado largo de una tarjeta tipo carnet o crédito

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024


# ---------------------------------------------------------------- utilidades
def leer_imagen(campo):
    archivo = request.files.get(campo)
    if archivo is None:
        return None
    datos = np.frombuffer(archivo.read(), np.uint8)
    return cv2.imdecode(datos, cv2.IMREAD_COLOR) if datos.size else None


def parametros():
    """Lee el cuadro, el fondo opcional y los ajustes enviados por la página."""
    frame = leer_imagen("imagen")
    if frame is None:
        raise ValueError("No se recibió una imagen válida.")
    fondo = leer_imagen("fondo")
    if fondo is not None and fondo.shape != frame.shape:
        fondo = cv2.resize(fondo, (frame.shape[1], frame.shape[0]))
    f = request.form
    i = min(max(int(f.get("producto", 0)), 0), len(PRODUCTOS) - 1)
    H, W = frame.shape[:2]
    return {
        "frame": frame, "fondo": fondo, "producto": PRODUCTOS[i],
        "px_por_cm": max(float(f.get("px_por_cm", 12.0)), 0.1),
        "s_min": int(f.get("s_min", 60)), "v_osc": int(f.get("v_osc", 70)),
        "roi": (int(W * 0.06), int(H * 0.06), int(W * 0.94), int(H * 0.94)),
    }


def analizar(p):
    try:
        return vision.analizar(p["frame"], p["producto"], p["px_por_cm"], p["fondo"],
                               p["roi"], p["s_min"], p["v_osc"])
    except cv2.error:
        return None


def poligono(contorno, tolerancia=1.5):
    return cv2.approxPolyDP(contorno, tolerancia, True).reshape(-1, 2).tolist()


def numero(v, dec):
    return None if v is None else round(float(v), dec)


def resumen(r):
    return {
        "area_cm2": numero(r["area_cm2"], 2), "volumen_cm3": numero(r["volumen_cm3"], 1),
        "peso_g": numero(r["peso_g"], 0), "largo_cm": numero(r["largo_cm"], 2),
        "diametro_cm": numero(r["diametro_cm"], 2), "area_dano_cm2": numero(r["area_dano_cm2"], 2),
        "dano_pct": numero(r["dano_pct"], 1), "madurez_pct": numero(r["madurez_pct"], 1),
        "calibre": r["calibre"], "estado": r["estado"], "producto": r["producto"],
    }


def jpeg_data_url(img, calidad=70):
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, calidad])
    return "data:image/jpeg;base64," + base64.b64encode(buf).decode() if ok else None


# ---------------------------------------------------------------- rutas
@app.get("/")
def inicio():
    return send_from_directory(CARPETA_WEB, "index.html")


@app.get("/salud")
def salud():
    return "ok"


@app.get("/api/productos")
def productos():
    return jsonify([{"id": i, "nombre": p.nombre, "madurez": p.rangos_maduro is not None}
                    for i, p in enumerate(PRODUCTOS)])


@app.post("/api/analizar")
def api_analizar():
    """Analiza un cuadro y devuelve medidas + geometría para dibujar sobre el video."""
    try:
        p = parametros()
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    H, W = p["frame"].shape[:2]
    salida = {"ancho": W, "alto": H, "roi": p["roi"], "detectado": False}

    if request.form.get("mascara") == "1":
        masc, _ = vision.segmentar(p["frame"], p["fondo"], p["roi"], p["s_min"], p["v_osc"])
        salida["mascara"] = jpeg_data_url(masc if masc is not None else np.zeros((H, W), np.uint8))

    r = analizar(p)
    if r is not None:
        dano_c, _ = cv2.findContours(r["dano"], cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        discos, eje = vision.geometria(r)
        salida.update({
            "detectado": True, "resultados": resumen(r),
            "contorno": poligono(r["contorno"]),
            "danos": [poligono(c, 1.0) for c in dano_c if len(c) >= 3],
            "discos": discos, "eje": eje,
        })
    return jsonify(salida)


@app.post("/api/calibrar")
def api_calibrar():
    """Mide el lado largo de la tarjeta (8.56 cm) para obtener la escala en px/cm."""
    try:
        p = parametros()
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    _, cont = vision.segmentar(p["frame"], p["fondo"], p["roi"], p["s_min"], p["v_osc"])
    if cont is None:
        return jsonify({"ok": False, "mensaje": "No se detectó la tarjeta. Póngala sola dentro del recuadro."})
    (_, _), (w, h), _ = cv2.minAreaRect(cont)
    lado = max(w, h)
    return jsonify({"ok": True, "px_por_cm": lado / REFERENCIA_CM, "lado_px": lado})


@app.post("/api/reporte")
def api_reporte():
    """Genera la lámina PNG con las gráficas de cálculo integral de la captura."""
    try:
        p = parametros()
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    r = analizar(p)
    if r is None:
        return jsonify({"error": "No hay producto detectado para capturar."}), 422
    vista = vision.anotar(p["frame"], r)
    buf = io.BytesIO()
    reporte.generar(vista, r, buf)
    buf.seek(0)
    resp = send_file(buf, mimetype="image/png")
    resp.headers["X-Resultados"] = json.dumps(resumen(r))      # ASCII: va en una cabecera HTTP
    return resp


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), debug=False)
