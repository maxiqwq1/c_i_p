"""
Fichas de producto (solo FRUTAS).

Las 9 frutas y sus PALETAS vienen de la tabla "Configuración de colores en
frutas y verduras" (web/ejemplos/tabla-colores.jpg): cada producto tiene una
combinación de colores que ayuda a identificarlo. Las fotos de esa tabla son
también el ENTRENAMIENTO BASE del reconocimiento (ver entrenar_tabla.py).
Las verduras de la tabla se quitaron: el programa solo inspecciona frutas
(si se pone una verdura, se mide como "Genérico").

Para inspeccionar un producto nuevo solo hay que agregar una ficha a la lista
PRODUCTOS (antes de "Genérico", que debe ir al final). El cálculo de área y
volumen es el mismo para todos; la ficha solo cambia la densidad (para
estimar el peso), los colores de madurez, los umbrales de clasificación, el
calibre y el PERFIL con el que el programa reconoce el producto automáticamente.

Los tonos (hue) usan la escala de OpenCV: 0-179
  rojo: 0-8 y 165-179 | naranja: 8-20 | amarillo: 20-32 | verde-amarillo: 32-45
  verde: 45-85 | azul: 85-130 | morado: 130-165

Perfil de reconocimiento automático (ver vision.reconocer). Cada factor vale 1
dentro del rango y baja suavemente fuera de él:
  colores       [(h_min, h_max, peso)]: tonos típicos del producto, maduro o verde.
                peso = qué tanto ese tono indica ESTE producto (0-1).
  alargamiento  (min, max) de eje mayor / eje menor: 1.0 = redondo, 1.4 = alargado.
                Una manzana vista de lado llega a ~1.15; un banano, a 3-6.
  curvatura     (min, max) flecha / cuerda del eje: 0 = recto; un banano, 0.08-0.3.
  asimetria     (min, max) diferencia de ancho entre las dos mitades del eje
                (0 = simétrico como un limón; una pera, con cuello, 0.3-0.5).
  extension     (min, max) área / rectángulo que la encierra: una elipse da 0.785;
                una hoja con punta, ~0.65-0.74.
  solidez       (min, max) área / envolvente convexa: 1 = convexo; un manojo de hojas, ~0.85.
                En los tres anteriores, None = no importa.
  saturacion    (min, max) de la saturación mediana (0-255): qué tan "vivo" es el color.
  brillo        (min, max) del brillo mediano (0-255): aguacate y pepino son oscuros.
  palidez       (min, max) fracción de piel casi sin color (cebolla blanca, papa).
  oscuro        (min, max) fracción de piel casi negra (aguacate Hass maduro).
  palido        True: los colores se miden también en la piel poco saturada.
  diametro      (min, max) en cm (grosor). Solo cuenta si la cámara está CALIBRADA, y
                solo ayuda: no puede descartar el producto (la escala puede no
                corresponder a la distancia actual).
  variantes     perfiles alternativos del mismo producto (p. ej. limón amarillo
                alargado y lima verde redonda); lo que falte se toma de la ficha.

Otros campos:
  paleta        los 4 colores de la tabla (se muestran junto a los colores medidos).
  eje_curvo     True: el volumen se calcula con discos perpendiculares al eje curvo
                (banano). Los productos alargados y curvos lo usan aunque sea False.
  lamina_cm     > 0 para hojas (espinaca): no es un sólido de revolución; su volumen
                es el de una lámina delgada, V = área × grosor.
  calibre_por   "diametro" o "largo" (el banano y el pepino se clasifican por largo).

Si el reconocimiento se equivoca con sus productos o su luz, use "Enseñar":
guarde 2-3 ejemplos reales de cada producto y el programa los usa primero
(vecino más cercano).
"""
from dataclasses import dataclass, field

ROJO = [(0, 8), (165, 179)]


@dataclass
class Producto:
    nombre: str
    densidad: float                    # g/cm³ (aproximada; ajústela pesando productos reales)
    rangos_maduro: list | None         # [(h_min, h_max), ...] o None si no aplica
    madurez_min: float = 60.0          # % mínimo de superficie con color maduro
    factor_oscuro: float = 0.55        # píxel con brillo < factor * luz local => mancha/daño
    dano_regular: float = 5.0          # % de área dañada a partir del cual es REGULAR
    dano_descarte: float = 15.0        # % de área dañada a partir del cual es DESCARTE
    calibres: list = field(default_factory=list)  # [(nombre, mínimo en cm)] de mayor a menor
    calibre_por: str = "diametro"      # "diametro" o "largo"
    categoria: str = "Fruta"           # "Fruta", "Verdura" u "Otro" (para agrupar en la lista)
    eje_curvo: bool = False
    lamina_cm: float = 0.0             # grosor de la hoja (solo productos laminares)
    paleta: list = field(default_factory=list)    # colores de la tabla, "#rrggbb"
    # perfil de reconocimiento (ver arriba)
    colores: list = field(default_factory=list)
    alargamiento: tuple = (1.0, 1.2)
    curvatura: tuple | None = None
    asimetria: tuple | None = None
    extension: tuple | None = None
    solidez: tuple | None = None
    saturacion: tuple = (60, 255)
    brillo: tuple = (0, 255)
    palidez: tuple = (0.0, 0.6)
    oscuro: tuple = (0.0, 0.4)
    palido: bool = False
    diametro: tuple = (3.0, 12.0)
    variantes: list = field(default_factory=list)


PRODUCTOS = [
    # ------------------------------------------------------------------ frutas
    Producto("Naranja", 0.90, [(5, 22)],
             calibres=[("Grande", 8.0), ("Mediana", 6.5), ("Pequeña", 0.0)],
             paleta=["#fc6b01", "#fd9102", "#fec327", "#fedf71"],
             colores=[(9, 20, 1.0), (20, 26, 0.5), (26, 45, 0.25)],
             alargamiento=(1.0, 1.12), saturacion=(200, 255), diametro=(5.5, 10.5)),
    # Tomate: rojo-naranja. El rojo carmesí (172-179) indica un poco más manzana que tomate.
    Producto("Tomate", 0.98, ROJO,
             calibres=[("Grande", 7.0), ("Mediano", 5.5), ("Pequeño", 0.0)],
             paleta=["#ec1701", "#f2421c", "#fe8655", "#fdba7f"],
             colores=[(0, 7, 1.0), (172, 179, 0.9), (168, 172, 0.7), (7, 13, 0.6), (35, 70, 0.3)],
             alargamiento=(1.0, 1.25), saturacion=(160, 255), diametro=(2.0, 8.0)),
    # Limón amarillo (alargado, con puntas) o lima / limón verde (más redondo y pequeño)
    Producto("Limón", 0.95, [(22, 60)],
             calibres=[("Grande", 5.5), ("Mediano", 4.5), ("Pequeño", 0.0)],
             paleta=["#fee504", "#b5d402", "#63b707", "#2b9b01"],
             saturacion=(120, 255), asimetria=(0.0, 0.2),
             variantes=[
                 {"colores": [(20, 34, 1.0), (34, 45, 0.5)], "alargamiento": (1.2, 1.7), "diametro": (4.0, 7.0)},
                 {"colores": [(34, 45, 0.5), (45, 65, 1.0)], "alargamiento": (1.0, 1.2), "diametro": (3.0, 5.8)},
             ]),
    Producto("Manzana roja", 0.80, [(0, 10), (160, 179)],
             calibres=[("Grande", 7.5), ("Mediana", 6.5), ("Pequeña", 0.0)],
             paleta=["#b40700", "#c0382f", "#e97774", "#fe9da2"],
             colores=[(0, 10, 1.0), (166, 179, 1.0), (160, 166, 0.5), (10, 24, 0.7), (24, 45, 0.4)],
             alargamiento=(1.0, 1.16), saturacion=(60, 200), diametro=(5.5, 10.0)),
    Producto("Manzana verde", 0.80, None,       # variedades verdes o amarillas: la madurez no se mide por color
             calibres=[("Grande", 7.5), ("Mediana", 6.5), ("Pequeña", 0.0)],
             paleta=["#70a201", "#93c224", "#68b121", "#2c7d03"],
             colores=[(22, 32, 0.8), (32, 45, 1.0), (45, 55, 0.6), (0, 10, 0.3), (165, 179, 0.3), (12, 22, 0.4)],
             alargamiento=(1.0, 1.18), asimetria=(0.0, 0.25), extension=(0.72, 0.86), solidez=(0.9, 1.0),
             saturacion=(40, 240), diametro=(5.8, 10.0)),
    Producto("Mango", 1.00, [(10, 35)],
             calibres=[("Grande", 10.0), ("Mediano", 8.0), ("Pequeño", 0.0)],
             paleta=["#fd6901", "#fd9f02", "#ddbf19", "#7a9b01"],
             colores=[(10, 35, 0.9), (35, 70, 0.6), (0, 10, 0.5), (165, 179, 0.5)],
             alargamiento=(1.22, 2.0), curvatura=(0.0, 0.12), asimetria=(0.0, 0.3), saturacion=(110, 255), brillo=(110, 255),
             diametro=(5.5, 12.0)),
    # Banano: curvo, se mide sobre el eje curvo y se clasifica por largo. Las pecas de
    # un banano maduro son normales: solo cuentan como daño las manchas muy oscuras.
    Producto("Banano", 0.95, [(18, 34)], factor_oscuro=0.45, dano_regular=8.0, dano_descarte=25.0,
             calibres=[("Extra", 20.0), ("Primera", 17.0), ("Segunda", 0.0)], calibre_por="largo",
             eje_curvo=True,
             paleta=["#fee065", "#f5d163", "#e1b94a", "#dcb54d"],
             colores=[(18, 34, 1.0), (34, 48, 0.9), (12, 18, 0.4)],
             alargamiento=(2.0, 6.5), curvatura=(0.06, 0.4), saturacion=(90, 255), brillo=(120, 255),
             diametro=(2.6, 4.8)),
    # Aguacate: común (verde brillante) o Hass (casi negro o café oscuro al madurar). Forma de
    # huevo o pera. La piel rugosa del Hass tiene grietas oscuras: solo cuenta como daño lo muy oscuro.
    Producto("Aguacate", 1.00, None, factor_oscuro=0.25,
             calibres=[("Grande", 9.0), ("Mediano", 7.0), ("Pequeño", 0.0)],
             paleta=["#5a6201", "#5b730b", "#9c9155", "#683e21"],
             saturacion=(40, 230), asimetria=(0.0, 0.4), extension=(0.74, 0.86),
             variantes=[
                 {"colores": [(30, 45, 0.6), (45, 75, 1.0)], "alargamiento": (1.15, 1.9),
                  "brillo": (35, 170), "diametro": (6.0, 13.0)},
                 {"colores": [(25, 90, 0.8), (120, 179, 0.8), (0, 25, 0.7)], "alargamiento": (1.1, 1.7),
                  "brillo": (0, 110), "oscuro": (0.15, 1.0), "diametro": (5.0, 9.5)},
             ]),
    Producto("Pera", 0.99, [(15, 30)], madurez_min=40.0,
             calibres=[("Grande", 7.0), ("Mediana", 6.0), ("Pequeña", 0.0)],
             paleta=["#ecd403", "#9fad02", "#cfcf37", "#e4d763"],
             colores=[(18, 45, 1.0), (12, 18, 0.5), (45, 55, 0.5), (0, 12, 0.3), (170, 179, 0.3)],
             alargamiento=(1.15, 1.8), asimetria=(0.22, 1.0), saturacion=(60, 245), diametro=(5.0, 9.5)),
    # ------------------------------------------------------------------ otros
    # Cualquier otro producto: mide área, volumen y daño sin evaluar madurez.
    # Se elige automáticamente cuando ningún perfil coincide. DEBE IR AL FINAL.
    Producto("Genérico", 1.00, None, categoria="Otro"),
]
