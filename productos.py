"""
Fichas de producto (frutas y verduras).

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
                None = no importa.
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
  eje_curvo     True: el volumen se calcula con discos perpendiculares al eje curvo
                (banano). Los productos alargados y curvos lo usan aunque sea False.
  calibre_por   "diametro" o "largo" (el banano y el pepino se clasifican por largo).

Si el reconocimiento por reglas se equivoca con sus productos o su luz, use
"Enseñar": guarde 2-3 ejemplos reales de cada producto y el programa los usa
primero (vecino más cercano).
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
    # perfil de reconocimiento (ver arriba)
    colores: list = field(default_factory=list)
    alargamiento: tuple = (1.0, 1.2)
    curvatura: tuple | None = None
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
             colores=[(9, 20, 1.0), (20, 26, 0.5), (26, 45, 0.25)],
             alargamiento=(1.0, 1.12), saturacion=(140, 255), diametro=(5.5, 10.5)),
    Producto("Tomate", 0.98, ROJO,
             calibres=[("Grande", 7.0), ("Mediano", 5.5), ("Pequeño", 0.0)],
             colores=[(0, 7, 1.0), (168, 179, 1.0), (7, 13, 0.6), (35, 70, 0.3)],
             alargamiento=(1.0, 1.25), saturacion=(160, 255), diametro=(2.0, 10.0)),
    # Limón amarillo (alargado, con puntas) o lima / limón verde (más redondo y pequeño)
    Producto("Limón", 0.95, [(22, 60)],
             calibres=[("Grande", 5.5), ("Mediano", 4.5), ("Pequeño", 0.0)],
             saturacion=(120, 255),
             variantes=[
                 {"colores": [(20, 34, 1.0), (34, 45, 0.5)], "alargamiento": (1.2, 1.7), "diametro": (4.0, 7.0)},
                 {"colores": [(34, 45, 0.5), (45, 65, 1.0)], "alargamiento": (1.0, 1.2), "diametro": (3.0, 5.8)},
             ]),
    Producto("Manzana roja", 0.80, [(0, 10), (160, 179)],
             calibres=[("Grande", 7.5), ("Mediana", 6.5), ("Pequeña", 0.0)],
             colores=[(0, 10, 1.0), (166, 179, 1.0), (160, 166, 0.5), (10, 24, 0.7), (24, 45, 0.4)],
             alargamiento=(1.0, 1.16), saturacion=(60, 200), diametro=(5.5, 10.0)),
    Producto("Manzana verde", 0.80, None,       # variedades verdes o amarillas: la madurez no se mide por color
             calibres=[("Grande", 7.5), ("Mediana", 6.5), ("Pequeña", 0.0)],
             colores=[(22, 32, 0.8), (32, 45, 1.0), (45, 55, 0.6), (0, 10, 0.3), (165, 179, 0.3), (12, 22, 0.4)],
             alargamiento=(1.0, 1.18), saturacion=(40, 240), diametro=(5.8, 10.0)),
    Producto("Mango", 1.00, [(10, 35)],
             calibres=[("Grande", 10.0), ("Mediano", 8.0), ("Pequeño", 0.0)],
             colores=[(10, 35, 0.9), (35, 70, 0.6), (0, 10, 0.5), (165, 179, 0.5)],
             alargamiento=(1.22, 2.0), saturacion=(110, 255), brillo=(110, 255), diametro=(5.5, 12.0)),
    # Banano: curvo, se mide sobre el eje curvo y se clasifica por largo. Las pecas de
    # un banano maduro son normales: solo cuentan como daño las manchas muy oscuras.
    Producto("Banano", 0.95, [(18, 34)], factor_oscuro=0.45, dano_regular=8.0, dano_descarte=25.0,
             calibres=[("Extra", 20.0), ("Primera", 17.0), ("Segunda", 0.0)], calibre_por="largo",
             eje_curvo=True,
             colores=[(18, 34, 1.0), (34, 48, 0.9), (12, 18, 0.4)],
             alargamiento=(2.0, 6.5), curvatura=(0.06, 0.4), saturacion=(90, 255), brillo=(100, 255),
             diametro=(2.6, 4.8)),
    # Aguacate: común (verde brillante) o Hass (casi negro al madurar). Forma de pera.
    Producto("Aguacate", 1.00, None,
             calibres=[("Grande", 9.0), ("Mediano", 7.0), ("Pequeño", 0.0)],
             saturacion=(40, 230),
             variantes=[
                 {"colores": [(30, 45, 0.6), (45, 75, 1.0)], "alargamiento": (1.15, 1.9),
                  "brillo": (35, 170), "diametro": (6.0, 13.0)},
                 {"colores": [(25, 90, 0.8), (120, 179, 0.8)], "alargamiento": (1.1, 1.7),
                  "brillo": (0, 110), "oscuro": (0.15, 1.0), "diametro": (5.0, 9.5)},
             ]),
    # ------------------------------------------------------------------ verduras
    Producto("Papa", 1.08, None, categoria="Verdura",
             calibres=[("Primera", 6.0), ("Segunda", 4.5), ("Tercera", 0.0)],
             # papa común (beige/café) o roja: color opaco y poco saturado, forma ovalada
             colores=[(8, 30, 1.0), (0, 8, 0.8), (168, 179, 0.8)], palido=True,
             alargamiento=(1.05, 2.0), saturacion=(50, 150), brillo=(70, 235), palidez=(0.0, 0.8),
             diametro=(3.0, 10.0)),
    Producto("Zanahoria", 1.03, None, categoria="Verdura",
             calibres=[("Grande", 3.5), ("Mediana", 2.5), ("Pequeña", 0.0)],
             colores=[(4, 18, 1.0), (18, 24, 0.4)],
             alargamiento=(2.5, 10.0), curvatura=(0.0, 0.12), saturacion=(150, 255), brillo=(110, 255),
             diametro=(1.5, 5.0)),
    # Cebolla cabezona: roja/morada o blanca (casi sin color)
    Producto("Cebolla", 0.95, None, categoria="Verdura",
             calibres=[("Grande", 8.0), ("Mediana", 6.0), ("Pequeña", 0.0)],
             alargamiento=(1.0, 1.35), diametro=(4.0, 11.0),
             variantes=[
                 {"colores": [(140, 165, 1.0), (165, 175, 0.6), (0, 4, 0.3)],
                  "saturacion": (50, 210), "brillo": (50, 210)},
                 {"colores": [(10, 35, 1.0)], "palido": True, "palidez": (0.4, 1.0),
                  "saturacion": (0, 90), "brillo": (170, 255)},
             ]),
    Producto("Pepino", 0.96, None, categoria="Verdura",
             calibres=[("Grande", 22.0), ("Mediano", 17.0), ("Pequeño", 0.0)], calibre_por="largo",
             colores=[(38, 50, 0.6), (50, 85, 1.0)],
             alargamiento=(2.2, 6.0), curvatura=(0.0, 0.12), saturacion=(60, 230), brillo=(40, 175),
             diametro=(2.5, 6.5)),
    # ------------------------------------------------------------------ otros
    # Cualquier otro producto: mide área, volumen y daño sin evaluar madurez.
    # Se elige automáticamente cuando ningún perfil coincide. DEBE IR AL FINAL.
    Producto("Genérico", 1.00, None, categoria="Otro"),
]
