"""
ENTRENAMIENTO BASE con la tabla "Configuración de colores en frutas y verduras".

Las fotos de las 9 frutas de la tabla (web/ejemplos/*.jpg, recortadas de web/ejemplos/tabla-colores.jpg)
se analizan con el mismo proceso que la cámara y sus RASGOS (colores, forma, tamaño)
se guardan en entrenamiento_tabla.json. El reconocimiento los usa como ejemplos de
referencia (vecino más cercano) antes de las reglas de productos.py.

Uso:  python entrenar_tabla.py        (vuelva a correrlo si cambia una foto o los rasgos)
"""
import json
import os

import cv2

import vision
from productos import PRODUCTOS

RAIZ = os.path.dirname(os.path.abspath(__file__))
CARPETA = os.path.join(RAIZ, "web", "ejemplos")


def entrenar():
    with open(os.path.join(CARPETA, "ejemplos.json"), encoding="utf-8") as f:
        info = json.load(f)
    nombres = {p.nombre for p in PRODUCTOS}
    ejemplos = []
    for e in info["ejemplos"]:
        if e["nombre"] not in nombres:
            print(f"  {e['nombre']}: no hay ficha en productos.py, se omite")
            continue
        img = cv2.imread(os.path.join(CARPETA, e["foto"]))
        # escala supuesta (tamaño típico): así el tamaño también queda en el ejemplo
        r = vision.analizar(img, None, e["px_por_cm"], calibrado=True, ejemplos=None) if img is not None else None
        if r is None:
            print(f"  {e['nombre']}: no se detectó el producto en {e['foto']}, se omite")
            continue
        ejemplos.append({"nombre": e["nombre"], "foto": "ejemplos/" + e["foto"], "rasgos": r["rasgos"],
                         "colores": r["colores"]})
        print(f"  {e['nombre']:14s} alarg {r['rasgos']['alarg']:.2f}  sat {r['rasgos']['sat']:.0f}  "
              f"brillo {r['rasgos']['val']:.0f}  colores {' '.join(c['hex'] for c in r['colores'])}")
    salida = {"fuente": info["fuente"], "ejemplos": ejemplos}
    with open(vision.RUTA_TABLA, "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, indent=1)
    print(f"{len(ejemplos)} ejemplos guardados en {os.path.basename(vision.RUTA_TABLA)}")


if __name__ == "__main__":
    entrenar()
