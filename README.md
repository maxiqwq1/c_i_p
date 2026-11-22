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

Todo es **automático**:
- **Detección en cualquier lugar**: no hace falta recuadro guía ni hoja blanca. El programa aprende los colores del fondo a partir del borde de la imagen y elige la región que más parece un producto (tamaño razonable, forma compacta, que no toque el borde). Ignora sombras, lápices y objetos cortados.
- **Reconocimiento del producto** (ver abajo), con votación entre cuadros para que no salte. Si ningún perfil coincide, usa *Genérico*. Se puede elegir a mano.
- **Captura automática**: cuando el producto se queda quieto ~1 s se guarda la captura y la lámina; vuelve a capturar al poner otro producto.
- **Zoom al producto**: la vista se acerca a la fruta (con un minimapa de la vista completa) y la foto de la lámina también.

## Cómo ejecutarlo (VS Code)
1. Abra esta carpeta en VS Code.
2. Pulse **F5** (o el menú *Ejecutar y depurar*) y elija:
   - **1. Cámara en vivo**: inspección real con la cámara web.
   - **2. Simulación de validación**: frutas artificiales de tamaño conocido; compara la integral numérica con las fórmulas exactas (πR², 4/3πab²). El error es menor al 1 %.

Desde la terminal también funciona: `python camara.py` (o `python camara.py 1` si tiene otra cámara).

Instalación para escritorio: `pip install -r requirements-escritorio.txt`

## Versión web (celular o cualquier navegador)
La página usa la cámara **del navegador** (en el celular, la trasera) o una foto subida, y el servidor aplica los mismos cálculos.
- Local: `pip install flask` y luego `python app.py` → abrir http://localhost:8000
- Railway: *New Project → Deploy from GitHub repo* → elegir este repositorio → *Settings → Networking → Generate Domain*. La configuración ya está en `railway.json` (usa `requirements.txt` con OpenCV sin pantalla).
- La cámara del navegador solo funciona con HTTPS (Railway lo da) o en `localhost`.
- La calibración y el historial de capturas se guardan en el navegador de cada dispositivo.

## Cómo reconoce el producto
1. **Corrige el color de la luz** (balance de blancos) si el fondo alrededor del producto es claro y neutro (hoja, pared, mesa gris): así una manzana roja con luz amarilla no parece naranja.
2. **Mide rasgos**: histograma de tonos de la piel, saturación, brillo, **alargamiento** (eje mayor/eje menor de la elipse de momentos) y **diámetro en cm**.
3. **Ejemplos enseñados** (si hay): si la fruta se parece lo suficiente a un ejemplo guardado, gana ese producto (vecino más cercano).
4. **Reglas** de cada ficha (`productos.py`): puntaje = color × forma × viveza × tamaño. Una ficha puede tener **variantes** (p. ej. *Limón*: limón amarillo alargado o lima verde redonda).
5. La línea **"Por qué"** muestra los 3 candidatos y el método usado, para revisar cualquier confusión.

**Calibrar mejora el reconocimiento**: con la escala real, el tamaño separa productos de color y forma parecidos (una lima mide ~4-5 cm; una manzana, 7-8 cm). **Enseñar** (botón *Guardar ejemplo* o tecla `E`) con 2-3 ejemplos por producto adapta el programa a sus frutas y su luz; en la web se guardan en el navegador y en escritorio en `entrenamiento.json`.

Prueba con frutas sintéticas (9 tipos × 4 escenas de luz/fondo, calibrado y sin calibrar): la versión anterior acertaba el 53 % (confundía siempre la manzana verde con limón); la actual, el 100 %, y el 100 % también con 8 frutas que no se usaron para ajustar los perfiles. Con luz cálida sobre madera (el color no se puede corregir) acierta el 85 %, y el 94 % tras enseñar 2 ejemplos por fruta.

## Recomendaciones para la cámara real
- Un fondo de color **distinto** al producto (mesa, mantel u hoja) y buena luz. Que el producto no toque el borde de la imagen.
- Calibre la escala una vez: ponga **sola** una tarjeta de color (carnet o tarjeta de crédito, 8.56 cm) frente a la cámara, a la misma distancia que las frutas, y pulse **K**. Se guarda en `calibracion.json`. Si cambia la altura de la cámara, vuelva a calibrar.
- Para productos de color parecido al fondo (papa sobre madera, cebolla sobre hoja), pulse **B** con la escena vacía y luego ponga el producto.
- Si la detección falla, pulse **M** para ver la máscara y mueva la barra *Sensibilidad* (más alta = detecta productos más pálidos; más baja = ignora más sombras).

## Teclas
`0` reconocer automáticamente · `1-7` elegir producto · `E` enseñar ejemplo · `A` captura automática · `Z` zoom · `C`/`Espacio` capturar a mano · `K` calibrar · `B` fondo · `D` discos · `M` máscara · `Q`/`Esc` salir

Cada captura guarda en `capturas/`: la foto, una **lámina con las gráficas de cálculo** (área entre curvas, discos, sólido 3D y convergencia de Riemann) y una fila en `resultados.csv` (se abre con Excel).

## Agregar otros productos
Edite `productos.py` y agregue una ficha (densidad, color de madurez, umbrales, calibres y el perfil de reconocimiento: colores típicos, alargamiento y saturación). El cálculo de áreas y volúmenes es el mismo para cualquier producto.

## Limitaciones (para mencionar en el informe)
- El método de discos supone que el producto es **simétrico alrededor de su eje mayor**. Funciona bien con naranja, tomate, limón, manzana o mango, y mal con banano.
- La cámara ve una proyección 2D. La silueta está un poco más cerca de la cámara que la hoja, así que la escala tiene un pequeño error de perspectiva.
- El reconocimiento usa reglas de color, forma y tamaño más los ejemplos que usted enseñe (vecino más cercano), no una red neuronal. Los pares más difíciles son **tomate / manzana roja** y, sin calibrar, **lima / manzana verde**. Calibre y enseñe 2-3 ejemplos de cada uno, o elija el producto a mano. Las pruebas son con frutas sintéticas: con frutas reales los porcentajes pueden ser menores.
- Densidades aproximadas: para mejorar el peso estimado hay que pesar algunas frutas reales y ajustar la densidad en `productos.py`.

## Archivos
- `calculo.py`: las integrales (área, volumen y sumas de Riemann)
- `vision.py`: detección automática, reconocimiento, alineación del eje, manchas, madurez y clasificación
- `camara.py`: aplicación en vivo
- `reporte.py`: lámina de gráficas
- `demo_sintetica.py`: simulación de validación
- `productos.py`: fichas de producto
