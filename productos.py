"""
Fichas de producto (frutas y verduras).

Los productos y sus PALETAS vienen de la tabla "Configuración de colores en
frutas y verduras" (web/ejemplos/tabla-colores.jpg): 14 de sus 16 productos (el
tomate y el aguacate no se incluyen). Cada producto tiene una combinación de
colores que ayuda a identificarlo. Las fotos de esa tabla son
también el ENTRENAMIENTO BASE del reconocimiento (ver entrenar_tabla.py).

Para inspeccionar un producto nuevo solo hay que agregar una ficha a la lista
PRODUCTOS (antes de "Genérico", que debe ir al final). El cálculo de área y
volumen es el mismo para todos; la ficha solo cambia los colores de madurez,
los umbrales de clasificación, el calibre y el PERFIL con el que el programa reconoce el producto automáticamente.

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
  brillo        (min, max) del brillo mediano (0-255): pepino y espinaca son oscuros.
  palidez       (min, max) fracción de piel casi sin color (cebolla blanca, papa).
  oscuro        (min, max) fracción de piel casi negra (una papa sana casi no tiene).
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

@dataclass
class Producto:
    nombre: str
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
    Producto("Naranja", [(5, 22)],
             calibres=[("Grande", 8.0), ("Mediana", 6.5), ("Pequeña", 0.0)],
             paleta=["#fc6b01", "#fd9102", "#fec327", "#fedf71"],
             colores=[(9, 20, 1.0), (20, 26, 0.5), (26, 45, 0.25)],
             alargamiento=(1.0, 1.12), saturacion=(200, 255), diametro=(5.5, 10.5)),
    # Limón amarillo (alargado, con puntas) o lima / limón verde (más redondo y pequeño)
    Producto("Limón", [(22, 60)],
             calibres=[("Grande", 5.5), ("Mediano", 4.5), ("Pequeño", 0.0)],
             paleta=["#fee504", "#b5d402", "#63b707", "#2b9b01"],
             saturacion=(120, 255), asimetria=(0.0, 0.2),
             variantes=[
                 {"colores": [(20, 34, 1.0), (34, 45, 0.5)], "alargamiento": (1.2, 1.7), "diametro": (4.0, 7.0)},
                 {"colores": [(34, 45, 0.5), (45, 65, 1.0)], "alargamiento": (1.0, 1.2), "diametro": (3.0, 5.8)},
             ]),
    Producto("Manzana roja", [(0, 10), (160, 179)],
             calibres=[("Grande", 7.5), ("Mediana", 6.5), ("Pequeña", 0.0)],
             paleta=["#b40700", "#c0382f", "#e97774", "#fe9da2"],
             colores=[(0, 10, 1.0), (166, 179, 1.0), (160, 166, 0.5), (10, 24, 0.7), (24, 45, 0.4)],
             alargamiento=(1.0, 1.16), saturacion=(60, 200), diametro=(5.5, 10.0)),
    Producto("Manzana verde", None,       # variedades verdes o amarillas: la madurez no se mide por color
             calibres=[("Grande", 7.5), ("Mediana", 6.5), ("Pequeña", 0.0)],
             paleta=["#70a201", "#93c224", "#68b121", "#2c7d03"],
             colores=[(22, 32, 0.8), (32, 45, 1.0), (45, 55, 0.6), (0, 10, 0.3), (165, 179, 0.3), (12, 22, 0.4)],
             alargamiento=(1.0, 1.18), asimetria=(0.0, 0.25), extension=(0.72, 0.86), solidez=(0.9, 1.0),
             saturacion=(40, 240), diametro=(5.8, 10.0)),
    Producto("Mango", [(10, 35)],
             calibres=[("Grande", 10.0), ("Mediano", 8.0), ("Pequeño", 0.0)],
             paleta=["#fd6901", "#fd9f02", "#ddbf19", "#7a9b01"],
             colores=[(10, 35, 0.9), (35, 70, 0.6), (0, 10, 0.5), (165, 179, 0.5)],
             alargamiento=(1.22, 2.0), curvatura=(0.0, 0.12), asimetria=(0.0, 0.3), saturacion=(110, 255), brillo=(110, 255),
             diametro=(5.5, 12.0)),
    # Banano: curvo, se mide sobre el eje curvo y se clasifica por largo. Las pecas de
    # un banano maduro son normales: solo cuentan como daño las manchas muy oscuras.
    Producto("Banano", [(18, 34)], factor_oscuro=0.45, dano_regular=8.0, dano_descarte=25.0,
             calibres=[("Extra", 20.0), ("Primera", 17.0), ("Segunda", 0.0)], calibre_por="largo",
             eje_curvo=True,
             paleta=["#fee065", "#f5d163", "#e1b94a", "#dcb54d"],
             colores=[(18, 34, 1.0), (34, 48, 0.9), (12, 18, 0.4)],
             alargamiento=(2.0, 6.5), curvatura=(0.06, 0.4), saturacion=(90, 255), brillo=(120, 255),
             diametro=(2.6, 4.8)),
    # ------------------------------------------------------------------ verduras
    Producto("Papa", None, categoria="Verdura",
             calibres=[("Primera", 6.0), ("Segunda", 4.5), ("Tercera", 0.0)],
             paleta=["#ecc48d", "#deb37a", "#b88241", "#7d4b18"],
             # papa común (beige/café) o roja: color opaco y poco saturado, forma ovalada
             colores=[(8, 30, 1.0), (0, 8, 0.8), (168, 179, 0.8)], palido=True,
             alargamiento=(1.05, 2.0), saturacion=(50, 150), brillo=(70, 235), palidez=(0.0, 0.8),
             oscuro=(0.0, 0.15), diametro=(3.0, 10.0)),
    Producto("Zanahoria", None, categoria="Verdura",
             calibres=[("Grande", 3.5), ("Mediana", 2.5), ("Pequeña", 0.0)],
             paleta=["#fe7501", "#fe9c02", "#ada001", "#4d9101"],
             colores=[(4, 18, 1.0), (18, 24, 0.4)],
             alargamiento=(2.5, 10.0), curvatura=(0.0, 0.12), saturacion=(150, 255), brillo=(110, 255),
             diametro=(1.5, 5.0)),
    # Cebolla cabezona: dorada (la de la tabla), roja/morada o blanca (casi sin color)
    Producto("Cebolla", None, categoria="Verdura",
             calibres=[("Grande", 8.0), ("Mediana", 6.0), ("Pequeña", 0.0)],
             paleta=["#e0ac7a", "#deae7c", "#af723b", "#7c4213"],
             alargamiento=(1.0, 1.35), diametro=(4.0, 11.0),
             variantes=[
                 {"colores": [(5, 22, 1.0)], "saturacion": (90, 200), "brillo": (100, 245)},
                 {"colores": [(140, 165, 1.0), (165, 175, 0.6), (0, 4, 0.3)],
                  "saturacion": (50, 210), "brillo": (50, 210)},
                 {"colores": [(10, 35, 1.0)], "palido": True, "palidez": (0.4, 1.0),
                  "saturacion": (0, 90), "brillo": (170, 255)},
             ]),
    Producto("Pepino", None, categoria="Verdura", factor_oscuro=0.4,
             calibres=[("Grande", 22.0), ("Mediano", 17.0), ("Pequeño", 0.0)], calibre_por="largo",
             paleta=["#256402", "#357b08", "#b8d773", "#a4b23e"],
             colores=[(36, 50, 0.8), (50, 85, 1.0)],
             alargamiento=(2.2, 6.0), curvatura=(0.0, 0.12), saturacion=(60, 230), brillo=(40, 150),
             diametro=(2.5, 6.5)),
    # Pimiento (pimentón) rojo o verde. Es HUECO: el volumen medido es el de su silueta.
    Producto("Pimiento", [(0, 30), (165, 179)], categoria="Verdura",
             calibres=[("Grande", 8.0), ("Mediano", 6.5), ("Pequeño", 0.0)],
             paleta=["#e00200", "#c91102", "#357702", "#498203"],
             alargamiento=(1.0, 1.35), saturacion=(110, 255), diametro=(7.5, 11.5),
             variantes=[
                 {"colores": [(0, 6, 0.9), (172, 179, 0.9), (6, 12, 0.4), (35, 85, 0.3)], "saturacion": (170, 255)},
                 {"colores": [(50, 80, 0.9), (40, 50, 0.4)], "saturacion": (150, 255), "brillo": (40, 200)},
             ]),
    # Espinaca: hoja (lámina delgada). El área es la de la silueta; el volumen, área × grosor.
    Producto("Espinaca", None, categoria="Verdura", lamina_cm=0.05, factor_oscuro=0.15,
             calibres=[("Grande", 15.0), ("Mediana", 10.0), ("Pequeña", 0.0)], calibre_por="largo",
             paleta=["#2b5b02", "#3b7703", "#87bd32", "#d5eb7e"],
             colores=[(35, 45, 0.8), (45, 85, 1.0)],
             alargamiento=(1.1, 3.0), extension=(0.5, 0.74), solidez=(0.5, 0.97),
             saturacion=(90, 255), brillo=(30, 160), diametro=(3.0, 20.0)),
    Producto("Pera", [(15, 30)], madurez_min=40.0,
             calibres=[("Grande", 7.0), ("Mediana", 6.0), ("Pequeña", 0.0)],
             paleta=["#ecd403", "#9fad02", "#cfcf37", "#e4d763"],
             colores=[(18, 45, 1.0), (12, 18, 0.5), (45, 55, 0.5), (0, 12, 0.3), (170, 179, 0.3)],
             alargamiento=(1.15, 1.8), asimetria=(0.22, 1.0), saturacion=(60, 245), diametro=(5.0, 9.5)),
    # Repollo: verde pálido, redondo y GRANDE. Sin calibrar se parece a una manzana verde;
    # con la cámara calibrada el tamaño los separa.
    Producto("Repollo", None, categoria="Verdura",
             calibres=[("Grande", 18.0), ("Mediano", 14.0), ("Pequeño", 0.0)],
             paleta=["#337601", "#2c7402", "#7ebe3e", "#c1e881"],
             colores=[(28, 40, 0.75), (40, 75, 0.9)],
             alargamiento=(1.0, 1.22), extension=(0.74, 0.86), solidez=(0.93, 1.0),
             saturacion=(40, 185), brillo=(145, 250), diametro=(11.0, 26.0)),
    # ------------------------------------------------------------------ otros
    # Cualquier otro producto: mide área, volumen y daño sin evaluar madurez.
    # Se elige automáticamente cuando ningún perfil coincide. DEBE IR AL FINAL.
    Producto("Genérico", None, categoria="Otro"),
]
