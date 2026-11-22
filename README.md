# Sistema automatizado de inspección de productos agrícolas
Proyecto de **Cálculo Integral**: áreas y volúmenes aplicados a la visión por computador.

La cámara del PC observa el producto (por ahora frutas) y el programa calcula:

| Magnitud | Concepto de Cálculo Integral | Fórmula |
|---|---|---|
| Área de la silueta | Área entre curvas | A = ∫ₐᵇ [f(x) − g(x)] dx |
| Volumen | Sólido de revolución, método de discos | V = π ∫ₐᵇ r(x)² dx, con r(x) = [f(x) − g(x)]/2 |
| Cálculo con píxeles | Suma de Riemann (Δx = 1 píxel) | A ≈ Σ [f(xᵢ) − g(xᵢ)] Δx |
| Área dañada | Suma doble de Riemann (cada píxel = (1/k)² cm²) | A_daño ≈ Σ ΔA |
| Peso estimado | Volumen × densidad | m = ρ V |

Con eso clasifica el producto como **BUENO / REGULAR / INMADURO / DESCARTE** y asigna un calibre.

## Cómo ejecutarlo (VS Code)
1. Abra esta carpeta en VS Code.
2. Pulse **F5** (o el menú *Ejecutar y depurar*) y elija:
   - **1. Cámara en vivo**: inspección real con la cámara web.
   - **2. Simulación de validación**: frutas artificiales de tamaño conocido; compara la integral numérica con las fórmulas exactas (πR², 4/3πab²). El error es menor al 1 %.

Desde la terminal también funciona: `python camara.py` (o `python camara.py 1` si tiene otra cámara).

## Recomendaciones para la cámara real
- Fondo **claro y liso** (una hoja blanca) y buena luz, sin sombras fuertes.
- Calibre la escala una vez: ponga **sola** una tarjeta de color (carnet o tarjeta de crédito, 8.56 cm) en el recuadro y pulse **K**. Se guarda en `calibracion.json`. Si cambia la altura de la cámara, vuelva a calibrar.
- Para productos pálidos (papa, cebolla), pulse **B** con el fondo vacío y luego ponga el producto.
- Si la detección falla, pulse **M** para ver la máscara y mueva las barras *Saturacion min* / *Oscuro max*.

## Teclas
`1-6` producto · `C`/`Espacio` capturar · `K` calibrar · `B` fondo · `D` discos · `M` máscara · `Q`/`Esc` salir

Cada captura guarda en `capturas/`: la foto, una **lámina con las gráficas de cálculo** (área entre curvas, discos, sólido 3D y convergencia de Riemann) y una fila en `resultados.csv` (se abre con Excel).

## Agregar otros productos
Edite `productos.py` y agregue una ficha (densidad, color de madurez, umbrales y calibres). El cálculo de áreas y volúmenes es el mismo para cualquier producto.

## Limitaciones (para mencionar en el informe)
- El método de discos supone que el producto es **simétrico alrededor de su eje mayor**. Funciona bien con naranja, tomate, limón, manzana o mango, y mal con banano.
- La cámara ve una proyección 2D. La silueta está un poco más cerca de la cámara que la hoja, así que la escala tiene un pequeño error de perspectiva.
- Densidades aproximadas: para mejorar el peso estimado hay que pesar algunas frutas reales y ajustar la densidad en `productos.py`.

## Archivos
- `calculo.py`: las integrales (área, volumen y sumas de Riemann)
- `vision.py`: segmentación, alineación del eje, manchas, madurez y clasificación
- `camara.py`: aplicación en vivo
- `reporte.py`: lámina de gráficas
- `demo_sintetica.py`: simulación de validación
- `productos.py`: fichas de producto
