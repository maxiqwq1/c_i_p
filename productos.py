"""
Fichas de producto.

Para inspeccionar un producto nuevo (otra fruta, verdura, tubérculo, etc.)
solo hay que agregar una ficha a la lista PRODUCTOS. El cálculo de área y
volumen es el mismo para todos; la ficha solo cambia la densidad (para
estimar el peso), los colores de madurez, los umbrales de clasificación y
el PERFIL con el que el programa reconoce el producto automáticamente.

Los tonos (hue) usan la escala de OpenCV: 0-179
  rojo: 0-8 y 165-179 | naranja: 8-20 | amarillo: 20-32 | verde-amarillo: 32-45 | verde: 45-85

Perfil de reconocimiento automático (ver vision.reconocer):
  colores       [(h_min, h_max, peso)]: tonos típicos del producto, maduro o verde.
                peso = qué tanto ese tono indica ESTE producto (0-1).
  alargamiento  (min, max) de eje mayor / eje menor: 1.0 = redondo, 1.4 = alargado.
                Una manzana vista de lado llega a ~1.15.
  saturacion    (min, max) de la saturación mediana (0-255): qué tan "vivo" es el color.
  diametro      (min, max) en cm. Solo se usa si la cámara está CALIBRADA; es lo que
                mejor separa productos de color y forma parecidos (lima vs. manzana verde).

Si el reconocimiento por reglas se equivoca con sus frutas o su luz, use
"Enseñar": guarde 2-3 ejemplos reales de cada producto y el programa los usa
primero (vecino más cercano).
"""
from dataclasses import dataclass, field

ROJO = [(0, 8), (165, 179)]


@dataclass
class Producto:
    nombre: str
    densidad: float                    # g/cm³ (aproximada; ajústela pesando frutas reales)
    rangos_maduro: list | None         # [(h_min, h_max), ...] o None si no aplica
    madurez_min: float = 60.0          # % mínimo de superficie con color maduro
    factor_oscuro: float = 0.55        # píxel con brillo < factor * brillo típico => mancha/daño
    dano_regular: float = 5.0          # % de área dañada a partir del cual es REGULAR
    dano_descarte: float = 15.0        # % de área dañada a partir del cual es DESCARTE
    calibres: list = field(default_factory=list)  # [(nombre, diámetro mínimo en cm)] de mayor a menor
    colores: list = field(default_factory=list)   # perfil de reconocimiento (ver arriba)
    alargamiento: tuple = (1.0, 1.2)
    saturacion: tuple = (60, 255)
    diametro: tuple = (3.0, 12.0)
    # Variantes del mismo producto con perfiles distintos (p. ej. limón amarillo alargado y
    # lima verde redonda). Cada una es un dict con colores/alargamiento/saturacion/diametro;
    # lo que falte se toma de la ficha. El puntaje del producto es el de su mejor variante.
    variantes: list = field(default_factory=list)


PRODUCTOS = [
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
             colores=[(0, 10, 1.0), (160, 179, 1.0), (10, 24, 0.7), (24, 45, 0.4)],
             alargamiento=(1.0, 1.16), saturacion=(60, 200), diametro=(5.5, 10.0)),
    Producto("Manzana verde", 0.80, None,       # variedades verdes o amarillas: la madurez no se mide por color
             calibres=[("Grande", 7.5), ("Mediana", 6.5), ("Pequeña", 0.0)],
             colores=[(22, 32, 0.8), (32, 45, 1.0), (45, 55, 0.6), (0, 10, 0.3), (165, 179, 0.3), (12, 22, 0.4)],
             alargamiento=(1.0, 1.18), saturacion=(40, 240), diametro=(5.8, 10.0)),
    Producto("Mango", 1.00, [(10, 35)],
             calibres=[("Grande", 10.0), ("Mediano", 8.0), ("Pequeño", 0.0)],
             colores=[(10, 35, 0.9), (35, 70, 0.6), (0, 10, 0.5), (165, 179, 0.5)],
             alargamiento=(1.22, 2.0), saturacion=(80, 255), diametro=(5.5, 12.0)),
    # Cualquier otro producto: mide área, volumen y daño sin evaluar madurez.
    # Se elige automáticamente cuando ningún perfil coincide (p. ej. papa, cebolla).
    Producto("Genérico", 1.00, None),
]
