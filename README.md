# Sistema automatizado de inspección de productos agrícolas
Proyecto de **Cálculo Integral**: áreas y volúmenes aplicados a la visión por computador.

La cámara observa el producto (frutas y verduras) y el programa calcula:

| Magnitud | Concepto de Cálculo Integral | Fórmula |
|---|---|---|
| Área de la silueta | Área entre curvas | A = ∫ₐᵇ [f(x) − g(x)] dx |
| Volumen | Sólido de revolución, método de discos | V = π ∫ₐᵇ r(x)² dx, con r(x) = [f(x) − g(x)]/2 |
| Largo de un producto curvo (banano) | Longitud de arco del eje c(x) = [f(x) + g(x)]/2 | L = ∫ₐᵇ √(1 + c′(x)²) dx |
| Volumen de un producto curvo | Discos perpendiculares al eje curvo | V = π ∫ r⊥(s)² ds = π ∫ₐᵇ r⊥(x)² √(1 + c′(x)²) dx |
| Volumen de una hoja (espinaca) | Lámina delgada: área entre curvas × grosor | V = e · ∫ₐᵇ [f(x) − g(x)] dx |
| Cálculo con píxeles | Suma de Riemann (Δx = 1 píxel) | A ≈ Σ [f(xᵢ) − g(xᵢ)] Δx |
| Área dañada | Suma doble de Riemann (cada píxel = (1/k)² cm²) | A_daño ≈ Σ ΔA |
| Peso estimado | Volumen × densidad | m = ρ V |

Con eso clasifica el producto como **BUENO / REGULAR / INMADURO / DESCARTE** y asigna un calibre.

**Productos incluidos** (`productos.py`): 14 de los 16 de la **tabla de colores** (ver abajo; el tomate y el aguacate no se incluyen).
- Frutas: naranja, limón (amarillo o lima verde), manzana roja, manzana verde/amarilla, mango, **banano** y **pera**.
- Verduras: **papa**, **zanahoria**, **cebolla** (dorada, roja o blanca), **pepino**, **pimiento** (rojo o verde), **espinaca** y **repollo**.
- *Genérico* para cualquier otro producto: mide área, volumen y daño sin evaluar madurez.

Todo es **automático**:
- **Detección en cualquier lugar**: no hace falta recuadro guía ni hoja blanca. El programa aprende los colores del fondo a partir del borde de la imagen y elige la región que más parece un producto (tamaño razonable, forma compacta o alargada pero gruesa, que no toque el borde). Ignora sombras, lápices y objetos cortados.
- **Reconocimiento del producto** (ver abajo), con votación entre cuadros para que no salte. Si ningún perfil coincide, usa *Genérico*. Se puede elegir a mano.
- **Captura automática**: cuando el producto se queda quieto ~1 s se guarda la captura y la lámina; vuelve a capturar al poner otro producto.
- **Daño sin confundir sombras**: se estima cómo cae la luz sobre la fruta (superficie cúbica ajustada por mínimos cuadrados, ignorando las manchas) y es mancha lo que queda bastante más oscuro que *esa* luz local. Así la sombra del lado no iluminado no cuenta como daño.
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
- **Probar sin cámara**: la pantalla inicial muestra las 14 fotos de la tabla de colores, cada una con su paleta; al tocar una se analiza. Su escala es **supuesta** (se eligió para que cada producto mida su tamaño típico, p. ej. una naranja de 7.8 cm), así que sus medidas son ilustrativas. Enlaces directos para compartir: `/?ejemplo=pera` (claves: `naranja`, `limon`, `manzana-roja`, `manzana-verde`, `mango`, `banano`, `papa`, `zanahoria`, `cebolla`, `pepino`, `pimiento`, `espinaca`, `pera`, `repollo`), `/?tabla` (la tabla completa) y `/?como` (las fórmulas).
- Junto a los resultados se ven los **colores medidos** en la piel (los 4 principales, con su %) al lado de la **paleta de la tabla** del producto; la lámina también los muestra.
- En el celular, el producto, su estado y el área, el volumen y el peso se muestran **sobre la cámara**, para no tener que bajar mientras se apunta; la barra inferior tiene Cámara, Foto, Capturar, Cambiar y Auto.

## Productos curvos: el eje curvo (banano)
El método de discos clásico gira la silueta alrededor de un eje **recto**. Un banano es curvo, y con eje recto su volumen sale mal (los discos verticales cortan el banano en diagonal y lo "engordan"). Por eso, para productos alargados y curvos:

1. **Eje curvo**: la línea media de la silueta, c(x) = [f(x) + g(x)]/2, suavizada con un polinomio de grado 3 (mínimos cuadrados).
2. **Largo real = longitud de arco**: L = ∫ √(1 + c′(x)²) dx. La cuerda (eje recto) subestima el largo del banano.
3. **Radio perpendicular**: si la tangente forma un ángulo θ con el eje x (tan θ = c′(x)), el grosor vertical f − g mide 2r/cos θ, así que r⊥ = [(f − g)/2]·cos θ.
4. **Volumen**: discos de grosor ds perpendiculares a la curva: V = π ∫ r⊥(s)² ds = π ∫ r⊥(x)² √(1 + c′(x)²) dx.

Si el producto es recto, c′(x) = 0 y todo se reduce al método de discos normal (los resultados de la demo no cambian). La lámina muestra los discos perpendiculares al eje curvo y el sólido 3D como un tubo que sigue la curva.

Validación con bananos sintéticos de volumen y largo exactos:

| Banano sintético | Volumen con eje recto | Volumen con eje curvo | Largo por la cuerda | Largo por el arco (real) |
|---|---|---|---|---|
| Curvo (flecha 0.15) | +6.2 % | +2.9 % | 18.3 cm | 19.2 cm (19.0) |
| Muy curvo (flecha 0.22) | +10.3 % | +3.4 % | 16.6 cm | 18.0 cm (18.0) |

Con el flujo completo (detección + alineación + eje curvo), el error medio de volumen fue −1.8 % (banano maduro), −0.2 % (banano verde), −2.8 % (zanahoria) y −1.1 % (pepino).

## La tabla de colores: entrenamiento base
La tabla *Configuración de colores en frutas y verduras* (`web/ejemplos/tabla-colores.jpg`) es la base del reconocimiento: "cada fruta y verdura tiene una combinación única de colores que permite identificarla".
- **Productos y paletas**: 14 de los 16 productos de la tabla (sin tomate ni aguacate) y sus 4 colores (campo `paleta` en `productos.py`, medidos en los círculos de la tabla).
- **Fotos de ejemplo**: las 14 fotos se recortaron de la tabla (`web/ejemplos/*.jpg`; la papa y la zanahoria de adelante se separaron de las de atrás). `ejemplos.json` guarda la escala supuesta de cada una.
- **Entrenamiento**: `python entrenar_tabla.py` analiza las 14 fotos con el mismo proceso que la cámara y guarda sus rasgos en `entrenamiento_tabla.json`. El reconocimiento los usa como ejemplos de referencia (vecino más cercano, con un umbral estricto porque son fotos de estudio).
- **Perfiles ajustados con la tabla**: las reglas de cada producto se ajustaron para reconocer esas fotos sin empeorar las pruebas anteriores.

Resultados: las 14 fotos de la tabla se reconocen todas, también borrosas, oscuras, con luz cálida o fría, comprimidas, giradas o con ruido (224/224). Solo con las reglas (sin los ejemplos de la tabla) acierta 13/14 con la cámara calibrada y 12/14 sin calibrar; los casos ambiguos son manzana roja (se parece al pimiento rojo) y repollo (ver limitaciones).

## Cómo reconoce el producto
1. **Corrige el color de la luz** (balance de blancos) si el fondo alrededor del producto es claro y neutro (hoja, pared, mesa gris): así una manzana roja con luz amarilla no parece naranja.
2. **Mide rasgos**: histograma de tonos de la piel, saturación, brillo, palidez (piel casi sin color: papa, cebolla blanca), zonas casi negras, **alargamiento** (eje mayor/eje menor de la elipse de momentos), **curvatura** del eje (banano), **asimetría** (el cuello de la pera), **extensión** y **solidez** de la silueta (una hoja o un manojo no es redondo ni macizo) y **grosor en cm**.
3. **Ejemplos enseñados** (si hay): si la fruta se parece lo suficiente a un ejemplo guardado, gana ese producto (vecino más cercano).
4. **Fotos de la tabla**: si se parece mucho a una de las 14 fotos de la tabla de colores, ese producto.
5. **Reglas** de cada ficha (`productos.py`): puntaje = color × forma × curvatura × viveza × brillo × palidez × tamaño (× asimetría, extensión y solidez si la ficha las usa). Una ficha puede tener **variantes** (p. ej. *Limón*: limón amarillo alargado o lima verde redonda).
6. La sección **"¿Por qué?"** muestra los 3 candidatos (con su paleta) y el método usado, para revisar cualquier confusión.

**Calibrar mejora el reconocimiento**: con la escala real, el tamaño separa productos de color y forma parecidos (una lima mide ~4-5 cm; una manzana, 7-8 cm). El tamaño solo *ayuda*: si la escala no corresponde a la distancia actual (calibró a otra altura o el celular está en la mano), no puede descartar al producto correcto. **Enseñar** (botón *Guardar ejemplo* o tecla `E`) con 2-3 ejemplos por producto adapta el programa a sus frutas y su luz; en la web se guardan en el navegador y en escritorio en `entrenamiento.json`.

Prueba con productos sintéticos (16 tipos × 4 escenas de luz/fondo, calibrado y sin calibrar): acierta el 97 %; el único fallo es la cebolla blanca sobre hoja blanca, que no se detecta (blanco sobre blanco) y se resuelve con el modo **Fondo** (`B`). Frutas que no se usaron para ajustar: 100 %. Con luz cálida sobre madera (el color no se puede corregir) acierta el 80 %, y el 100 % tras enseñar 2 ejemplos por producto. La versión de reconocimiento original acertaba el 53 % en las frutas (confundía siempre la manzana verde con limón).

Productos nuevos de la tabla (sintéticos, 4 escenas): la pera, la hoja de espinaca y el pimiento rojo se reconocen siempre; el pimiento verde y el repollo, siempre que la cámara esté **calibrada** (su color y forma son como los de una lima o una manzana verde: lo que los separa es el tamaño); la cebolla dorada falla sobre madera, que es de su mismo color.

## Recomendaciones para la cámara real
- Un fondo de color **distinto** al producto (mesa, mantel u hoja) y buena luz. Que el producto no toque el borde de la imagen.
- Calibre la escala una vez: ponga **sola** una tarjeta de color (carnet o tarjeta de crédito, 8.56 cm) frente a la cámara, a la misma distancia que las frutas, y pulse **K**. Se guarda en `calibracion.json`. Si cambia la altura de la cámara, vuelva a calibrar.
- Para productos de color parecido al fondo (cebolla blanca sobre hoja blanca, papa o zanahoria sobre madera), pulse **B** con la escena vacía y luego ponga el producto, o use un fondo de otro color.
- Los productos largos (banano, pepino, zanahoria) deben caber completos en la imagen, sin tocar el borde.
- Si la detección falla, pulse **M** para ver la máscara y mueva la barra *Sensibilidad* (más alta = detecta productos más pálidos; más baja = ignora más sombras).

## Teclas
`0` reconocer automáticamente · `1-9` elegir producto (los primeros 9) · `N`/`P` producto siguiente/anterior · `E` enseñar ejemplo · `A` captura automática · `Z` zoom · `C`/`Espacio` capturar a mano · `K` calibrar · `B` fondo · `D` discos · `M` máscara · `Q`/`Esc` salir

Cada captura guarda en `capturas/`: la foto, una **lámina con las gráficas de cálculo** (área entre curvas, discos, sólido 3D y convergencia de Riemann) y una fila en `resultados.csv` (se abre con Excel).

## Agregar otros productos
Edite `productos.py` y agregue una ficha antes de *Genérico* (densidad, color de madurez, umbrales, calibre por diámetro o por largo, eje curvo si lo necesita, su paleta, y el perfil de reconocimiento: colores típicos, alargamiento, curvatura, saturación, brillo, palidez y diámetro). El cálculo de áreas y volúmenes es el mismo para cualquier producto. Si agrega su foto a `web/ejemplos/` y a `ejemplos.json`, corra `python entrenar_tabla.py` para que también sea un ejemplo de referencia.

## Limitaciones (para mencionar en el informe)
- El método de discos supone secciones **circulares** alrededor del eje (recto o curvo). Funciona bien con frutas redondas, banano, zanahoria, pepino, papa, cebolla y repollo. El **pimiento** es hueco: se usa una densidad *efectiva* (0.5 g/cm³ = peso real / volumen de la silueta). La **espinaca** se mide como una hoja (lámina de 0.5 mm): con una hoja extendida el área es exacta; de un manojo solo se mide la silueta, no el peso real. Brócoli y lechuga no están incluidos.
- La cámara ve una proyección 2D. La silueta está un poco más cerca de la cámara que la hoja, así que la escala tiene un pequeño error de perspectiva.
- El reconocimiento usa reglas de color, forma y tamaño más ejemplos (los de la tabla y los que usted enseñe, por vecino más cercano), no una red neuronal. Los grupos más difíciles son **manzana roja / pimiento rojo** y, sin calibrar, **lima / manzana verde / repollo / pimiento verde**: calibre (el tamaño los separa), enseñe 2-3 ejemplos de cada uno o elija el producto a mano. Las fotos de la tabla son de estudio: con la cámara real decide sobre todo el perfil de cada producto. Las pruebas son con frutas sintéticas: con frutas reales los porcentajes pueden ser menores.
- En pieles oscuras (pepino) o en hojas, las grietas y sombras naturales son casi negras: allí el umbral de daño baja con la luz y se ignoran las grietas finas, así que solo cuentan las manchas grandes y muy oscuras.
- Densidades aproximadas: para mejorar el peso estimado hay que pesar algunas frutas reales y ajustar la densidad en `productos.py`.

## Archivos
- `calculo.py`: las integrales (área, volumen y sumas de Riemann)
- `vision.py`: detección automática, reconocimiento, alineación del eje, manchas, madurez y clasificación
- `camara.py`: aplicación en vivo
- `reporte.py`: lámina de gráficas
- `demo_sintetica.py`: simulación de validación
- `productos.py`: fichas de producto (con la paleta de la tabla de colores)
- `entrenar_tabla.py` → `entrenamiento_tabla.json`: entrenamiento base con las fotos de la tabla
- `web/ejemplos/`: la tabla de colores, 14 fotos recortadas de ella y `ejemplos.json`
