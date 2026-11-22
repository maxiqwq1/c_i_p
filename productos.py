"""
Fichas de producto.

Para inspeccionar un producto nuevo (otra fruta, verdura, tubérculo, etc.)
solo hay que agregar una ficha a la lista PRODUCTOS. El cálculo de área y
volumen es el mismo para todos; la ficha solo cambia la densidad (para
estimar el peso), los colores de madurez y los umbrales de clasificación.

Los tonos (hue) usan la escala de OpenCV: 0-179
  rojo: 0-8 y 165-179 | naranja: 8-22 | amarillo: 22-35 | verde: 35-85
"""
from dataclasses import dataclass, field


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


PRODUCTOS = [
    Producto("Naranja", 0.90, [(5, 22)],
             calibres=[("Grande", 8.0), ("Mediana", 6.5), ("Pequeña", 0.0)]),
    Producto("Tomate", 0.98, [(0, 8), (165, 179)],
             calibres=[("Grande", 7.0), ("Mediano", 5.5), ("Pequeño", 0.0)]),
    Producto("Limón", 0.95, [(28, 60)],
             calibres=[("Grande", 5.5), ("Mediano", 4.5), ("Pequeño", 0.0)]),
    Producto("Manzana roja", 0.80, [(0, 10), (160, 179)],
             calibres=[("Grande", 7.5), ("Mediana", 6.5), ("Pequeña", 0.0)]),
    Producto("Mango", 1.00, [(10, 35)],
             calibres=[("Grande", 10.0), ("Mediano", 8.0), ("Pequeño", 0.0)]),
    # Cualquier otro producto: mide área, volumen y daño sin evaluar madurez.
    Producto("Genérico", 1.00, None),
]
