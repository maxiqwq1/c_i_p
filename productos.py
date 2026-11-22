"""
Fichas de producto.

Para inspeccionar un producto nuevo (otra fruta, verdura, tubérculo, etc.)
solo hay que agregar una ficha a la lista PRODUCTOS. El cálculo de área y
volumen es el mismo para todos; la ficha solo cambia la densidad (para
estimar el peso), los colores de madurez, los umbrales de clasificación y
el PERFIL con el que el programa reconoce el producto automáticamente.

Los tonos (hue) usan la escala de OpenCV: 0-179
  rojo: 0-8 y 165-179 | naranja: 8-22 | amarillo: 22-35 | verde: 35-85

Perfil de reconocimiento automático (ver vision.reconocer):
  colores       [(h_min, h_max, peso)]: tonos típicos del producto, maduro o verde.
                peso = qué tanto ese tono indica este producto (0-1).
  alargamiento  (min, max) de largo / diámetro: 1.0 = redondo, 1.5 = alargado.
  saturacion    (min, max) de la saturación mediana: un tomate es más "vivo"
                que una manzana del mismo color.
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


PRODUCTOS = [
    Producto("Naranja", 0.90, [(5, 22)],
             calibres=[("Grande", 8.0), ("Mediana", 6.5), ("Pequeña", 0.0)],
             colores=[(9, 22, 1.0), (22, 32, 0.5), (32, 60, 0.35)],
             alargamiento=(1.0, 1.15), saturacion=(130, 255)),
    Producto("Tomate", 0.98, ROJO,
             calibres=[("Grande", 7.0), ("Mediano", 5.5), ("Pequeño", 0.0)],
             colores=[(0, 8, 1.0), (165, 179, 1.0), (8, 14, 0.6), (35, 70, 0.3)],
             alargamiento=(1.0, 1.3), saturacion=(150, 255)),
    Producto("Limón", 0.95, [(28, 60)],
             calibres=[("Grande", 5.5), ("Mediano", 4.5), ("Pequeño", 0.0)],
             colores=[(24, 65, 1.0), (20, 24, 0.5)],
             alargamiento=(1.12, 1.7), saturacion=(80, 255)),
    Producto("Manzana roja", 0.80, [(0, 10), (160, 179)],
             calibres=[("Grande", 7.5), ("Mediana", 6.5), ("Pequeña", 0.0)],
             colores=[(0, 10, 1.0), (160, 179, 1.0), (10, 30, 0.6), (30, 50, 0.3)],
             alargamiento=(1.0, 1.2), saturacion=(50, 165)),
    Producto("Mango", 1.00, [(10, 35)],
             calibres=[("Grande", 10.0), ("Mediano", 8.0), ("Pequeño", 0.0)],
             colores=[(10, 35, 0.9), (35, 70, 0.6), (0, 10, 0.4), (165, 179, 0.4)],
             alargamiento=(1.25, 1.9), saturacion=(90, 255)),
    # Cualquier otro producto: mide área, volumen y daño sin evaluar madurez.
    # Se elige automáticamente cuando ningún perfil coincide (p. ej. papa, cebolla).
    Producto("Genérico", 1.00, None),
]
