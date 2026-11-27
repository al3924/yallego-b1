# Auditoría de Calidad de Datos — YaLlegó Delivery (2025)

## 1. Perfilado de los 12 archivos crudos (Capa Bronce)

Revisamos **12 archivos** en `YaLlego/raw/pedidos/` (11 CSV y 1 JSON) sin modificar nada y sumaron **76.232 filas** en `bronce_pedidos`.

| Archivo | Filas crudas | Qué vimos al revisar el archivo |
|---|---:|---|
| `pedidos_2025_01.csv` | 6.103 | `fecha_hora` viene en segundos Unix (ej. `1735762813`). |
| `pedidos_2025_02.csv` | 5.806 | `monto_bs` viene como texto con `"Bs "` y coma decimal (ej. `"Bs 15,00"`). |
| `pedidos_2025_03.csv` | 6.055 | Formato limpio; nulos en `tiempo_entrega_min` (295) y `calificacion` (1.850). |
| `pedidos_2025_04.csv` | 6.512 | Hay **900 `pedido_id` repetidos**. En cada par uno figura `en_camino` (con tiempos y calificaciones vacíos) y otro como `entregado`. |
| `pedidos_2025_05.csv` | 5.790 | Formato limpio; nulos en `tiempo_entrega_min` (237) y `calificacion` (1.796). |
| `pedidos_2025_06.csv` | 5.709 | `zona_entrega` tiene variaciones de texto (mayúsculas, espacios, guiones, abreviaturas como `"Quilla"` o `"quillacollo "`); 951 filas no coinciden literal con el nombre oficial. |
| `pedidos_2025_07.csv` | 6.082 | Formato limpio; nulos en `tiempo_entrega_min` (249) y `calificacion` (1.850). Desde el 2 de julio empieza la promo *"Miércoles sin envío"*. |
| `pedidos_2025_08.csv` | 6.552 | Aparecen valores negativos (`< 0`, 80 filas) y `999` (80 filas) en `tiempo_entrega_min`. |
| `pedidos_2025_09.csv` | 6.105 | Desde el 15 de septiembre las calificaciones cambian a escala 1–10 en vez de 1–5. |
| `pedidos_2025_10.csv` | 6.698 | Estructura limpia; hay envíos en `0.0` desde julio por la promo y pedidos cancelados. |
| `pedidos_2025_11.json` | 6.936 | Viene en JSON con vacíos como `null` (2.230 en `calificacion` y 352 en `tiempo_entrega_min`), que al leer como `str` quedan como `"nan"`. |
| `pedidos_2025_12.csv` | 7.884 | Trae la columna extra `version_app` (que no está en los otros meses) y 300 pedidos sin `rider_id` (285 `entregado` y 15 `cancelado`). |

### ¿Qué mes pareció más raro y por qué?

`pedidos_2025_04.csv` y `pedidos_2025_12.csv` fueron los más raros. En abril hay 900 `pedido_id` repetidos y aparece `en_camino`, un estado que no se ve en otros meses y explica por qué abril acumula tantos nulos en `tiempo_entrega_min` (1.183) y `calificacion` (2.711). En diciembre aparece `version_app` rompiendo el esquema de los demás meses y hay 285 pedidos marcados como `entregado` sin `rider_id`, algo que en delivery no cuadra sin un repartidor asignado.

---

## 2. Los 8 problemas y cómo los limpiamos en Plata

| # | Problema | Qué encontramos (ejemplos) | Filas afectadas | Regla en `plata_pedidos` |
|---|---|---|---:|---|
| 1 | Fechas en Unix (enero) | Segundos Unix como `1735762813` en `fecha_hora`. | 6.103 | Pasar Unix a `datetime` y unir con el formato ISO (`YYYY-MM-DD HH:MM:SS`). No restamos UTC-4 porque las horas (7 a 23) ya coinciden con la hora local de Cochabamba. |
| 2 | Montos con texto (febrero) | Cadenas tipo `"Bs 15,00"` o `"Bs 44,97"`. | 5.806 | Quitar `"Bs"`, quitar espacios, cambiar `,` por `.` y convertir a `float`. |
| 3 | Duplicados en abril | 900 `pedido_id` repetidos (`en_camino` vs. estado final). | 900 filas descartadas | Ordenar dejando `en_camino` al final y usar `drop_duplicates(subset=["pedido_id"], keep="first")`. Quedan **75.332** pedidos únicos. |
| 4 | Zonas distintas en junio | Variantes como `"quillacollo "`, `"Quilla"`, `"Cala-Cala"`, `"Queru-Queru"` o `" Sacaba"`. | 951 (de 5.709 del mes) | Limpiar espacios/mayúsculas y mapear a las **12 zonas oficiales** de `zonas.csv`. |
| 5 | Tiempos imposibles en agosto | Valores `< 0` (80 filas) y `999` (80 filas) en `tiempo_entrega_min` (lo válido del mes va de 8,0 a 60,9 min). | 160 | Pasar `< 0` y `== 999` a `NaN` sin borrar el pedido. |
| 6 | Escala 1–10 en septiembre | Desde el `2025-09-15` al `2025-09-30` las notas vienen en escala 1–10 (incluyendo 219 notas entre 3 y 5 que también son sobre 10; 2.080 son `> 5`). | 2.299 | Dividir entre 2 todas las calificaciones con `fecha_hora` entre `2025-09-15` y `2025-09-30` (el promedio de esa quincena pasa a 3,94 vs. 4,22 de la primera). |
| 7 | JSON y `"nan"` en noviembre | Archivo JSON con `null` que quedan como `"nan"` al leer `dtype=str`. | 6.936 (archivo) / 2.582 vacíos | Aplanar el JSON y reemplazar `"nan"`, `"NaN"`, `"None"` y `""` por `NaN` real antes de convertir tipos. |
| 8 | Columna extra y `rider_id` nulo en diciembre | Columna `version_app` y 300 `rider_id` nulos (285 entregados y 15 cancelados). | 7.884 (columna) / 300 nulos | Sacar `version_app` de `plata_pedidos` (queda en bronce) y crear `rider_asignado = rider_id.notna()` conservando los pedidos. |

### Puntos de control verificados en Plata
- Pedidos únicos: **75.332**.
- Suma de `monto_bs`: **Bs 4.421.271,12** (sin deduplicar abril sería Bs 4.473.517,89).
- Zonas: **12** iguales a `zonas.csv`; fechas entre `2025-01-01` y `2025-12-31`; calificaciones entre `1.0` y `5.0`; `0` montos nulos; los 120 `rider_id` están en `riders_api.json`.

---

## 3. Decisiones del equipo

1. **Restaurantes fuera del catálogo (`R041`):** `restaurantes.xlsx` (encabezado en fila 3) tiene 40 restaurantes válidos y aparecen **140 pedidos** (142 en crudo) con `R041`. Los dejamos en `plata_pedidos` con `restaurante_valido = False` para no alterar las 75.332 filas ni el total de `monto_bs`, y en Oro usamos `LEFT JOIN` para no mezclarlos en métricas por restaurante o cocina.
2. **Tiempos `< 0` o `999`:** Los convertimos a `NaN` en vez de borrar la fila. Borrar el pedido nos haría perder ventas y conteos reales, y dejar `-5` o `999` arruinaría el tiempo promedio de entrega.
3. **Escala 1–10 en septiembre:** Dividimos entre 2 según la fecha (`2025-09-15` a `2025-09-30`) y no solo cuando `calificacion > 5`, porque hay notas de 3, 4 y 5 en esa quincena que también estaban en escala de 10. Así no perdemos esos datos ni inflamos el promedio.
4. **Duplicados de abril:** Nos quedamos con el estado final y descartamos `en_camino` porque es un estado intermedio antes de cerrar el pedido, no por "menos nulos" (si mañana llega una fila `en_camino` más completa, la regla por estado sigue siendo la correcta).
5. **Pedidos entregados sin `rider_id` en diciembre (285 filas):** Se mantienen en ventas y totales de pedidos con `rider_asignado = False`, pero se excluyen de rankings y métricas por rider porque no hay repartidor asignado al que imputarle el servicio.

---

## 4. Capa Bronce y validación con Pandera

* **¿Para qué sirve la capa bronce si los datos están sucios?** Sirve para guardar tal cual lo que llegó de los archivos (con `archivo_origen`) y poder volver a correr Plata desde cero si encontramos un error nuevo o cambiamos una regla, sin tocar los archivos originales.
* **Regla de Pandera más importante para Valeria y por qué:** Validar `monto_bs > 0` (no nulo), `pedido_id` único y `fecha_hora` en 2025. Si entra un monto negativo, nulo o un pedido duplicado, se altera directamente cuánto vendió YaLlegó y cuánto costó o rindió la promo *"Miércoles sin envío"*.
* **Reglas en `esquemas.py` (`lazy=True`):** Formato de IDs (`P` + 6 dígitos, `C` + 5 dígitos, `R` + 3 dígitos, `RD` + 3 dígitos), `pedido_id` único, fechas en 2025, `monto_bs > 0`, `costo_envio_bs >= 0` y `propina_bs >= 0`, zonas dentro de las 12 oficiales, `estado` solo en `{"entregado", "cancelado"}` (bloqueando `en_camino`), `calificacion` en `1.0–5.0`, `tiempo_entrega_min` en `1–240` (o nulo), `metodo_pago` en `{"QR", "efectivo", "tarjeta"}` y una regla de fila para que un pedido `cancelado` no tenga calificación ni tiempo de entrega.
* **Rechazos y prueba de falla:** En `plata_pedidos` quedaron **75.332** filas válidas y **0** en `rechazos_pedidos` (la tabla existe con su columna `motivo`) porque limpiamos antes de validar. En la prueba intencional con 4 filas rotas (`monto_bs = -50`, `calificacion = 7`, `estado = "en_camino"` y un `cancelado` con calificación) y eliminando la columna `monto_bs`, Pandera detectó todos los fallos.
