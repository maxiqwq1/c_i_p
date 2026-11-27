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
    i = int(f.get("producto", -1))                    # -1 = reconocer automáticamente
    return {
        "frame": frame, "fondo": fondo,
        "producto": PRODUCTOS[i] if 0 <= i < len(PRODUCTOS) else None,
        "px_por_cm": max(float(f.get("px_por_cm", 12.0)), 0.1),
        "sensibilidad": int(f.get("sensibilidad", 50)),
        "calibrado": f.get("calibrado") == "1",
        "ejemplos": leer_ejemplos(f.get("ejemplos")),
    }


def leer_ejemplos(texto, maximo=300):
    """Ejemplos enseñados por el usuario (vienen del navegador). Se descartan los mal formados."""
    if not texto:
        return None
    try:
        datos = json.loads(texto)
    except ValueError:
        return None
    por_nombre = {p.nombre: i for i, p in enumerate(PRODUCTOS)}
    validos = []
    for e in datos[:maximo] if isinstance(datos, list) else []:
        try:
            # el nombre manda (si se agregan o quitan productos, los índices cambian); el índice es
            # respaldo. Un nombre que ya no existe (producto quitado) da -1 y se descarta.
            i = por_nombre.get(e["nombre"], -1) if e.get("nombre") else int(e["producto"])
            r = e["rasgos"]
            rasgos = {"hist": [float(v) for v in r["hist"]], "calibrado": bool(r.get("calibrado")),
                      **{k: float(r[k]) for k in ("palidez", "sat", "val", "alarg", "diam_cm")}}
            if len(r.get("hist_suave", [])) == 18:
                rasgos["hist_suave"] = [float(v) for v in r["hist_suave"]]
            for k in ("oscuro", "curvatura", "sat_global", "asimetria", "extension", "solidez"):
                if k in r:
                    rasgos[k] = float(r[k])
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
        if 0 <= i < len(PRODUCTOS) and len(rasgos["hist"]) == 18 and rasgos["alarg"] > 0:
            validos.append({"producto": i, "rasgos": rasgos})
    return validos or None


def analizar(p):
    try:
        r = vision.analizar(p["frame"], p["producto"], p["px_por_cm"], p["fondo"], p["sensibilidad"],
                            p["calibrado"], p["ejemplos"])
    except cv2.error:
        return None
    if r is not None and request.form.get("auto") == "1":
        r["automatico"] = True      # la página eligió el producto por votación del reconocimiento
    return r


def poligono(contorno, tolerancia=1.5):
    return cv2.approxPolyDP(contorno, tolerancia, True).reshape(-1, 2).tolist()


def numero(v, dec):
    return None if v is None else round(float(v), dec)


def resumen(r):
    red = r.get("frescura") or {}
    return {
        "red_veredicto": red.get("veredicto"),                     # lo que ve la red neuronal
        "red_podrido_pct": numero(100 * red["podrido"], 1) if red else None,
        "estado_calculo": r["estado_calculo"], "motivo": r["motivo"],   # estado solo con el daño, y por qué
        "area_cm2": numero(r["area_cm2"], 2), "volumen_cm3": numero(r["volumen_cm3"], 1),
        "largo_cm": numero(r["largo_cm"], 2),
        "diametro_cm": numero(r["diametro_cm"], 2), "area_dano_cm2": numero(r["area_dano_cm2"], 2),
        "dano_pct": numero(r["dano_pct"], 1), "dano_color_pct": numero(r["dano_color_pct"], 1),
        "madurez_pct": numero(r["madurez_pct"], 1),
        "calibre": r["calibre"], "estado": r["estado"], "producto": r["producto"],
        "producto_id": r["producto_id"], "automatico": r["automatico"],
        "metodo_volumen": r["metodo_volumen"],
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


@app.get("/ejemplos/<path:archivo>")
def ejemplos(archivo):
    """Fotos de la tabla de colores (ejemplos.json dice su escala supuesta) para probar sin cámara.
    La lista (ejemplos.json) no se guarda en caché: cambia cuando se agregan o quitan productos."""
    return send_from_directory(os.path.join(CARPETA_WEB, "ejemplos"), archivo,
                               max_age=0 if archivo.endswith(".json") else 86400)


@app.get("/api/productos")
def productos():
    return jsonify([{"id": i, "nombre": p.nombre, "categoria": p.categoria, "madurez": p.rangos_maduro is not None,
                     "paleta": p.paleta}                                  # colores de la tabla
                    for i, p in enumerate(PRODUCTOS)])


@app.post("/api/analizar")
def api_analizar():
    """Analiza un cuadro y devuelve medidas + geometría para dibujar sobre el video."""
    try:
        p = parametros()
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    H, W = p["frame"].shape[:2]
    salida = {"ancho": W, "alto": H, "detectado": False}

    r = analizar(p)
    if request.form.get("mascara") == "1":
        masc = r["mascara"] if r is not None else None
        salida["mascara"] = jpeg_data_url(masc if masc is not None else np.zeros((H, W), np.uint8))
    if r is not None:
        dano_c, _ = cv2.findContours(r["dano"], cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        discos, eje = vision.geometria(r)
        salida.update({
            "detectado": True, "resultados": resumen(r),
            "contorno": poligono(r["contorno"]),
            "danos": [poligono(c, 1.0) for c in dano_c if len(c) >= 3],
            "discos": discos, "eje": eje,
            "caja": list(cv2.boundingRect(r["contorno"])),          # para el zoom al producto
            "reconocido_id": r["reconocido_id"], "reconocimiento": r["reconocimiento"],
            "rasgos": r["rasgos"],                                  # la página los guarda al "Enseñar"
            "colores": r["colores"],                                # colores medidos (para compararlos con la tabla)
            "frescura": r["frescura"],                              # lo que ve la red neuronal (o None)
        })
    return jsonify(salida)


@app.post("/api/calibrar")
def api_calibrar():
    """Mide el lado largo de la tarjeta (8.56 cm) para obtener la escala en px/cm."""
    try:
        p = parametros()
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    _, cont = vision.segmentar(p["frame"], p["fondo"], p["sensibilidad"])
    if cont is None:
        return jsonify({"ok": False, "mensaje": "No se detectó la tarjeta. Póngala sola frente a la cámara."})
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
    vista = vision.anotar(p["frame"], r)       # reporte.generar hace el zoom al producto
    buf = io.BytesIO()
    reporte.generar(vista, r, buf)
    buf.seek(0)
    resp = send_file(buf, mimetype="image/png")
    resp.headers["X-Resultados"] = json.dumps(resumen(r))      # ASCII: va en una cabecera HTTP
    return resp


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), debug=False)
