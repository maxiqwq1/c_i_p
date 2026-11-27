# Sistema automatizado de inspección de productos agrícolas
Proyecto de **Cálculo Integral**: áreas y volúmenes aplicados a la visión por computador.

La cámara observa la fruta y el programa calcula:

| Magnitud | Concepto de Cálculo Integral | Fórmula |
|---|---|---|
| Área de la silueta | Área entre curvas | A = ∫ₐᵇ [f(x) − g(x)] dx |
| Volumen | Sólido de revolución, método de discos | V = π ∫ₐᵇ r(x)² dx, con r(x) = [f(x) − g(x)]/2 |
| Largo de un producto curvo (banano) | Longitud de arco del eje c(x) = [f(x) + g(x)]/2 | L = ∫ₐᵇ √(1 + c′(x)²) dx |
| Volumen de un producto curvo | Discos perpendiculares al eje curvo | V = π ∫ r⊥(s)² ds = π ∫ₐᵇ r⊥(x)² √(1 + c′(x)²) dx |
| Cálculo con píxeles | Suma de Riemann (Δx = 1 píxel) | A ≈ Σ [f(xᵢ) − g(xᵢ)] Δx |
| Área dañada | Suma doble de Riemann (cada píxel = (1/k)² cm²) | A_daño ≈ Σ ΔA |
| Comprobación de área y volumen | Teorema de Fubini (el orden de integración no cambia el resultado) | ∬_R F dA = ∫[∫F dy]dx = ∫[∫F dx]dy |

Con eso clasifica el producto como **BUENO / REGULAR / INMADURO / DESCARTE** y asigna un calibre. En manzana, banano y naranja, una **red neuronal** entrenada con fotos reales decide el estado junto con el daño medido (ver *El estado: red neuronal + daño medido*).

**Productos incluidos** (`productos.py`): **solo frutas** de la **tabla de colores** (ver abajo). Las verduras de la tabla, el tomate y el aguacate se quitaron.
- Frutas: naranja, limón (amarillo o lima verde), manzana roja, manzana verde/amarilla, mango, **banano** y **pera**.
- *Genérico* para cualquier otro producto: mide área, volumen y daño sin evaluar madurez.

Todo es **automático**:
- **Detección en cualquier lugar**: no hace falta recuadro guía ni hoja blanca. El programa aprende los colores del fondo a partir del borde de la imagen y elige la región que más parece un producto (tamaño razonable, forma compacta o alargada pero gruesa, que no toque el borde). Ignora sombras, lápices y objetos cortados.
- **Reconocimiento del producto** (ver abajo), con votación entre cuadros para que no salte. Si ningún perfil coincide, usa *Genérico*. Se puede elegir a mano.
- **Captura automática**: cuando el producto se queda quieto ~1 s se guarda la captura y la lámina; vuelve a capturar al poner otro producto.
- **Daño sin confundir sombras**: se estima cómo cae la luz sobre la fruta (superficie cúbica ajustada por mínimos cuadrados, ignorando las manchas) y es mancha lo que queda bastante más oscuro que *esa* luz local. Así la sombra del lado no iluminado no cuenta como daño.
- **Zoom al producto**: la vista se acerca a la fruta (con un minimapa de la vista completa) y la foto de la lámina también.
- **Cámara estable**: el zoom sigue una caja *estabilizada* (zona muerta: el temblor de unos píxeles de la silueta se ignora; un cambio grande se sigue con una transición suave de ~0.45 s) y su aumento máximo es ~2x. Las medidas son la mediana de las últimas 7 lecturas con un promedio suave; el estado y el calibre son los más repetidos; el producto reconocido necesita ~6 cuadros parecidos para decidirse o cambiar; y si la detección falla en un cuadro suelto se sostiene la anterior (sin parpadeo).

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
- **Probar sin cámara**: la pantalla inicial muestra las 7 fotos de frutas de la tabla de colores, cada una con su paleta; al tocar una se analiza. Su escala es **supuesta** (se eligió para que cada producto mida su tamaño típico, p. ej. una naranja de 7.8 cm), así que sus medidas son ilustrativas. Enlaces directos para compartir: `/?ejemplo=pera` (claves: `naranja`, `limon`, `manzana-roja`, `manzana-verde`, `mango`, `banano`, `pera`), `/?tabla` (la tabla completa) y `/?como` (las fórmulas).
- Junto a los resultados se ven los **colores medidos** en la piel (los 4 principales, con su %) al lado de la **paleta de la tabla** del producto; la lámina también los muestra.
- En el celular, el producto, su estado y el área y el volumen se muestran **sobre la cámara**, para no tener que bajar mientras se apunta; la barra inferior tiene Cámara, Foto, Capturar, Cambiar y Auto.

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

Con el flujo completo (detección + alineación + eje curvo), el error medio de volumen fue −1.8 % (banano maduro) y −0.2 % (banano verde).

## Teorema de Fubini (en la lámina)
Fubini dice que una integral doble se puede calcular como dos integrales seguidas, **en cualquier orden**: ∬_R F dA = ∫ₐᵇ[∫ F dy]dx = ∫_c^d[∫ F dx]dy. La integral de adentro recorre un *corte* de la región (una columna o una fila). La lámina de cada captura tiene una sección que lo comprueba con la fruta medida (`calculo.fubini`):

1. **Área en los dos órdenes**: por columnas, ∫ₐᵇ[∫_{g(x)}^{f(x)} dy]dx = ∫(f − g)dx (lo que mide el programa), y por filas, ∫_c^d[largo del corte horizontal]dy. Dan exactamente lo mismo. Ojo con el **banano**: una fila horizontal lo cruza en **2 tramos**, y la integral de adentro es la suma de los dos, no "derecha − izquierda" (eso daría 69.2 cm² en vez de 51.3 cm² con la foto de ejemplo). Por eso el programa integra por columnas, a lo largo del eje.
2. **Volumen: discos = capas cilíndricas**. En el plano (x, ρ) la región es 0 ≤ ρ ≤ r(x) y cada punto aporta 2πρ (el anillo de radio ρ). Integrando primero ρ salen los discos, ∫[∫₀^{r(x)} 2πρ dρ]dx = π∫r²dx; integrando primero x salen las capas, ∫₀^R 2πρ ℓ(ρ) dρ, con ℓ(ρ) = largo de la parte más gruesa que ρ. Así Fubini **justifica el método de discos**.
3. **Volumen como integral doble sobre la silueta**: sobre cada punto de la foto el sólido tiene un grosor 2√(r² − v²) (v = distancia al eje), así que V = ∬ 2√(r² − v²) dA = ∫[∫_{−r}^{r} 2√(r² − v²) dv]dx = ∫ πr² dx (la integral de adentro es el área del círculo). Se suma con cuadritos de 1 píxel.

Con las 7 fotos de la tabla, los tres volúmenes coinciden con una diferencia de 0.03 % como máximo (por ejemplo, naranja 250.7 cm³ por los tres caminos). En el banano (eje curvo) x pasa a ser s, la posición sobre el arco, y r pasa a ser r⊥.

## La tabla de colores: entrenamiento base
La tabla *Configuración de colores en frutas y verduras* (`web/ejemplos/tabla-colores.jpg`) es la base del reconocimiento: "cada fruta y verdura tiene una combinación única de colores que permite identificarla".
- **Productos y paletas**: las 7 frutas de la tabla (sin tomate ni aguacate) y sus 4 colores (campo `paleta` en `productos.py`, medidos en los círculos de la tabla).
- **Fotos de ejemplo**: las fotos de las 7 frutas se recortaron de la tabla (`web/ejemplos/*.jpg`). `ejemplos.json` guarda la escala supuesta de cada una.
- **Entrenamiento**: `python entrenar_tabla.py` analiza las 7 fotos con el mismo proceso que la cámara y guarda sus rasgos en `entrenamiento_tabla.json`. El reconocimiento los usa como ejemplos de referencia (vecino más cercano, con un umbral estricto porque son fotos de estudio).
- **Perfiles ajustados con la tabla**: las reglas de cada producto se ajustaron para reconocer esas fotos sin empeorar las pruebas anteriores.

Resultados: las 7 fotos de la tabla se reconocen todas, también borrosas, oscuras, con luz cálida o fría, comprimidas, giradas o con ruido, con la cámara calibrada y sin calibrar (112/112). Solo con las reglas (sin los ejemplos de la tabla) también acierta 7/7, calibrada y sin calibrar.

## Cómo reconoce el producto
1. **Corrige el color de la luz** (balance de blancos) si el fondo alrededor del producto es claro y neutro (hoja, pared, mesa gris): así una manzana roja con luz amarilla no parece naranja.
2. **Mide rasgos**: histograma de tonos de la piel, saturación, brillo, palidez (piel casi sin color), zonas casi negras, **alargamiento** (eje mayor/eje menor de la elipse de momentos), **curvatura** del eje (banano), **asimetría** (el cuello de la pera), **extensión** y **solidez** de la silueta (qué tan llena y maciza es) y **grosor en cm**.
3. **Ejemplos enseñados** (si hay): si la fruta se parece lo suficiente a un ejemplo guardado, gana ese producto (vecino más cercano).
4. **Fotos de la tabla**: si se parece mucho a una de las 7 fotos de frutas de la tabla de colores, ese producto.
5. **Reglas** de cada ficha (`productos.py`): puntaje = color × forma × curvatura × viveza × brillo × palidez × tamaño (× asimetría, extensión y solidez si la ficha las usa). Una ficha puede tener **variantes** (p. ej. *Limón*: limón amarillo alargado o lima verde redonda).
6. La sección **"¿Por qué?"** muestra los 3 candidatos (con su paleta) y el método usado, para revisar cualquier confusión.

**Calibrar mejora el reconocimiento**: con la escala real, el tamaño separa productos de color y forma parecidos (una lima mide ~4-5 cm; una manzana, 7-8 cm). El tamaño solo *ayuda*: si la escala no corresponde a la distancia actual (calibró a otra altura o el celular está en la mano), no puede descartar al producto correcto. **Enseñar** (botón *Guardar ejemplo* o tecla `E`) con 2-3 ejemplos por producto adapta el programa a sus frutas y su luz; en la web se guardan en el navegador y en escritorio en `entrenamiento.json`.

Prueba con frutas sintéticas (18 tipos de fruta × 4 escenas de luz/fondo, calibrado y sin calibrar, incluidas la pera y frutas que no se usaron para ajustar): acierta el 100 % (288/288). Con luz cálida sobre madera (el color no se puede corregir) acierta el 87.5 % —confunde la manzana amarilla con la roja y la lima con la manzana verde— y el 100 % tras enseñar ejemplos. La versión de reconocimiento original acertaba el 53 % en las frutas (confundía siempre la manzana verde con limón).

## El estado: red neuronal + daño medido
El daño se mide con cálculo integral: el área dañada es una suma doble de Riemann sobre los píxeles dañados. Al principio solo contaban las **manchas oscuras**, y con fotos reales de fruta podrida eso no basta: el **moho blanco o verde**, la **piel arrugada** o el **café claro o parejo** no son "manchas más oscuras que la luz". Con 758 fotos de prueba de fruta real, una manzana podrida daba en promedio 0.5 % de daño, y decidir solo con el daño mandaba a DESCARTE apenas el **3.5 %** de las frutas podridas (la mayoría salían BUENO o INMADURO). Por eso se hicieron dos cosas: el área dañada ahora también cuenta la **piel con color de podrido**, y una **red neuronal** decide el estado junto con el daño.

**El área dañada: manchas oscuras + color de podrido.** En manzana, banano y naranja, se aprendió de las fotos de Kaggle qué colores aparecen mucho más en la piel podrida que en la sana (`entrenar_colores_dano.py` → `colores_dano.json`): para cada color de la piel (espacio Lab, 8 × 32 × 32 casillas) se calcula la razón r = ln( P(color | fruta podrida) / P(color | fruta fresca) ). Un píxel es "color de podrido" si r supera un umbral, y el umbral sale del **teorema de Bayes**: si la red ve la fruta fresca, solo cuentan los colores claramente de podrido (umbral elegido con validación para que casi ninguna fruta fresca llegue a 5 % de daño); si la ve podrida o duda, también los dudosos (umbral 1.2, elegido mirando fotos de prueba). La página muestra el daño separado en "color de podrido" y "manchas oscuras".

| Fotos de prueba (758 casos) | Daño típico antes | Daño típico ahora |
|---|---|---|
| Manzanas podridas | 0.5 % | **33 %** |
| Bananos podridos | 5.8 % | **59 %** |
| Naranjas podridas | 0 % | **15 %** |
| Frutas frescas | 0-0.1 % | 0-0.2 % (3 % de las manzanas y naranjas frescas llega a 5 %) |

Con el área nueva, decidir *solo con el daño* ya manda a DESCARTE el 74.6 % de las frutas podridas (antes 3.5 %) sin descartar ninguna fresca. Una manzana con media piel café y agrietada pasó de 2 % a 46 % de daño.

**La red neuronal decide junto con el daño.**

En **manzana, banano y naranja**, una **red neuronal** que aprendió de fotos reales calcula la probabilidad de que la fruta esté podrida, P(podrido), y el estado se decide con las dos cosas:

| Lo que ve la red | Estado |
|---|---|
| P(podrido) ≥ 50 % (la ve podrida) | **DESCARTE** |
| 40 % ≤ P(podrido) < 50 % (duda) | **REGULAR** (o DESCARTE si el daño medido ya lo exige) |
| P(podrido) < 40 % (la ve fresca) | decide el **daño medido**, como siempre: BUENO, REGULAR o DESCARTE (e INMADURO por el color) |

Los dos umbrales se eligieron con las fotos de **validación** y se midieron con las de **prueba**. La página, la lámina y el CSV muestran también el estado que daría *solo el daño* y el motivo de la decisión. Con las demás frutas (limón, mango, pera), que la red no conoce, decide solo el daño medido.

Resultados con fotos reales que la red nunca vio (227 fotos de prueba, cada una sobre su fondo original, gris, madera y oscuro; 758 casos):

| Cómo se decide | Acierto (descartar o no) | Podridas → DESCARTE | Frescas → DESCARTE (error) |
|---|---|---|---|
| Solo el daño (solo manchas oscuras, como antes) | 45.5 % | 3.5 % | 0 % |
| Solo el daño (manchas oscuras + color de podrido) | 85.6 % | 74.6 % | 0 % |
| **Red neuronal + daño** | **98.4 %** | **98.8 %** | **2.1 %** |

Por fondo, con red + daño: original 99.0 %, gris 98.4 %, madera 97.8 %, oscuro 98.4 %. Con baja resolución, ruido o luz cálida, fría u oscura (como una cámara web), la red acierta fresco/podrido entre el 98.2 y el 99.6 %. Las 7 fotos reales de la tabla de colores (frescas) siguen en BUENO.

**La red**
- **Datos**: el dataset de Kaggle *Fruits fresh and rotten for classification* (`sriramr/fruits-fresh-and-rotten-for-classification`): 6 clases (manzana, banano y naranja, frescas y podridas).
- **Red**: MobileNetV2 preentrenada con ImageNet, con la última capa cambiada a 6 salidas (transferencia de aprendizaje), entrenada 12 épocas. P(podrido) = suma de las probabilidades (softmax) de las 3 clases podridas. Acierta fresco/podrido el 99.1 % de las fotos de prueba.
- **En la página**: el modelo (`modelo_frescura.onnx`, 9 MB) lo ejecuta OpenCV, sin PyTorch en el servidor, y tarda unos 5-15 ms por cuadro. Recibe un cuadrado alrededor del producto detectado.
- **Una trampa del dataset**: de sus 13 599 imágenes solo 1 511 son fotos distintas; las demás son copias giradas, espejadas, desplazadas o con ruido, repartidas al azar entre `train` y `test` (1 310 fotos tienen copias en los dos lados). Medir con ese `test` es medir con fotos ya vistas. Aquí se separó **por foto original**: 70 % entrenamiento, 15 % validación y 15 % prueba, sin copias compartidas. (El notebook de Kaggle que usa este dataset, además, planteaba mal la salida —una sola salida sí/no para 6 clases— y acertaba el 14.5 %, menos que al azar).
- **Otra trampa: el fondo**. En el dataset las frutas frescas casi siempre están sobre fondo blanco, y las podridas muchas veces sobre madera o tela: una red entrenada así aprende "fondo de color = podrido" y se equivoca con una fruta fresca sobre la mesa. Por eso, al entrenar, cada fruta se recorta con el mismo detector de la página y se pega sobre fondos al azar (colores, degradados, rayas tipo madera o tela, texturas de otras fotos, a veces con sombra). Con eso, las frutas frescas mandadas por error a DESCARTE bajaron del 3.3 % al 2.1 %, y sobre madera el acierto subió del 96.7 % al 97.8 %.

Para volver a entrenar (unos 8 minutos con una tarjeta NVIDIA RTX 2080 Ti):
```
pip install -r requirements-entrenamiento.txt
python entrenar_frescura.py "C:\ruta\del\dataset\dataset"
python entrenar_colores_dano.py "C:\ruta\del\dataset\dataset"
```
La ruta es la carpeta que tiene `train` y `test`. Si el entrenamiento se corta al final, `python entrenar_frescura.py "C:\ruta..." --solo-evaluar` termina con el mejor punto guardado. Las fotos del dataset no se suben al repositorio (en Kaggle su licencia figura como desconocida): solo el modelo entrenado. `modelo_frescura.json` y `colores_dano.json` guardan los resultados de la prueba. `entrenar_colores_dano.py` no necesita PyTorch (tarda menos de un minuto).

## Recomendaciones para la cámara real
- Un fondo de color **distinto** al producto (mesa, mantel u hoja) y buena luz. Que el producto no toque el borde de la imagen.
- Calibre la escala una vez: ponga **sola** una tarjeta de color (carnet o tarjeta de crédito, 8.56 cm) frente a la cámara, a la misma distancia que las frutas, y pulse **K**. Se guarda en `calibracion.json`. Si cambia la altura de la cámara, vuelva a calibrar.
- Para frutas de color parecido al fondo (por ejemplo, una manzana verde sobre un mantel verde), pulse **B** con la escena vacía y luego ponga el producto, o use un fondo de otro color.
- El banano debe caber completo en la imagen, sin tocar el borde.
- Si la detección falla, pulse **M** para ver la máscara y mueva la barra *Sensibilidad* (más alta = detecta productos más pálidos; más baja = ignora más sombras).

## Teclas
`0` reconocer automáticamente · `1-9` elegir producto (los primeros 9) · `N`/`P` producto siguiente/anterior · `E` enseñar ejemplo · `A` captura automática · `Z` zoom · `C`/`Espacio` capturar a mano · `K` calibrar · `B` fondo · `D` discos · `M` máscara · `Q`/`Esc` salir

Cada captura guarda en `capturas/`: la foto, una **lámina con las gráficas de cálculo** (área entre curvas, discos, sólido 3D, convergencia de Riemann y teorema de Fubini) y una fila en `resultados.csv` (se abre con Excel).

## Agregar otros productos
Edite `productos.py` y agregue una ficha antes de *Genérico* (color de madurez, umbrales, calibre por diámetro o por largo, eje curvo si lo necesita, su paleta, y el perfil de reconocimiento: colores típicos, alargamiento, curvatura, saturación, brillo, palidez y diámetro). El cálculo de áreas y volúmenes es el mismo para cualquier producto. Si agrega su foto a `web/ejemplos/` y a `ejemplos.json`, corra `python entrenar_tabla.py` para que también sea un ejemplo de referencia.

## Limitaciones (para mencionar en el informe)
- El método de discos supone secciones **circulares** alrededor del eje (recto o curvo). Funciona bien con las frutas redondas y con el banano (eje curvo). Productos que no son sólidos de revolución (una hoja, un brócoli) o que son huecos (un pimiento) no están incluidos: se medirían como *Genérico*.
- La **red neuronal** solo decide en manzana, banano y naranja, y actúa cuando el producto se reconoce o se elige a mano. Una fruta muy podrida pierde su color, y el reconocimiento por color puede confundirla con otro producto: en ese caso, elija el producto a mano. Con limón, mango y pera decide solo el daño medido, que no ve el moho ni la piel arrugada. Las fotos del dataset son de internet, casi todas de estudio: con la cámara real puede acertar menos (pruébela con frutas frescas y podridas de verdad).
- El **color de podrido** se aprendió solo para manzana, banano y naranja. El moho blanco o verde de las naranjas se detecta solo en parte: se parece a los brillos de la luz y a las hojas verdes que aparecen en las fotos de frutas frescas. El área dañada usa la pista de la red (si la ve podrida, cuentan los colores dudosos), así que no es una medida independiente de ella.
- La cámara ve una proyección 2D. La silueta está un poco más cerca de la cámara que la hoja, así que la escala tiene un pequeño error de perspectiva.
- El reconocimiento usa reglas de color, forma y tamaño más ejemplos (los de la tabla y los que usted enseñe, por vecino más cercano), no una red neuronal (la red neuronal decide fresco / podrido, no qué fruta es). Los pares más difíciles son **lima / manzana verde** (sin calibrar; el tamaño los separa) y, con luz cálida, **manzana amarilla / manzana roja**: calibre, enseñe 2-3 ejemplos de cada uno o elija el producto a mano. Las fotos de la tabla son de estudio: con la cámara real decide sobre todo el perfil de cada producto. Las pruebas son con frutas sintéticas: con frutas reales los porcentajes pueden ser menores.
- Las pecas de un banano maduro son normales: en el banano solo cuentan como daño las manchas muy oscuras. En las zonas con poca luz el umbral de daño baja con la luz y se ignoran las grietas finas, así que solo cuentan las manchas grandes.

## Archivos
- `calculo.py`: las integrales (área, volumen, sumas de Riemann y la comprobación con el teorema de Fubini)
- `vision.py`: detección automática, reconocimiento, alineación del eje, manchas, madurez y clasificación
- `camara.py`: aplicación en vivo
- `reporte.py`: lámina de gráficas
- `demo_sintetica.py`: simulación de validación
- `productos.py`: fichas de producto (con la paleta de la tabla de colores)
- `entrenar_tabla.py` → `entrenamiento_tabla.json`: entrenamiento base con las fotos de la tabla
- `frescura.py`: red neuronal fresco / podrido (ejecuta `modelo_frescura.onnx` con OpenCV) y la decisión del estado junto con el daño
- `entrenar_colores_dano.py` → `colores_dano.json`: los colores de piel podrida (manzana, banano y naranja) que suma el área dañada
- `datos_frutas.py`: el dataset de Kaggle para los dos entrenamientos (división por foto original y siluetas)
- `entrenar_frescura.py` → `modelo_frescura.onnx` + `modelo_frescura.json`: entrenamiento de la red con el dataset de Kaggle (necesita `requirements-entrenamiento.txt`)
- `web/ejemplos/`: la tabla de colores, las fotos recortadas de las 7 frutas y `ejemplos.json`
