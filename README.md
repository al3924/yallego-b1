# YaLlegó Delivery — Pipeline de Datos 2025

Pipeline que toma los ~75 mil pedidos de 2025 de YaLlegó Delivery (Cochabamba, Bolivia), los limpia y deja tablas listas para responder 5 preguntas de la gerencia. Se corre con un solo comando y todo queda en DuckDB.

---

## Integrantes

| Nombre | Carrera |
|---|---|
| Aliendre Pinto Andy Gabriel | Analítica Gerencial de Datos — UPB |
| Sevilla Ordoñez Alessandra | Analítica Gerencial de Datos — UPB |
| Morales Merida Christopher Anghelo | Analítica Gerencial de Datos — UPB |

---

## Cómo correrlo

Requisitos:

```bash
pip install pandas numpy duckdb pandera openpyxl requests matplotlib seaborn scipy
```

Para abrir `analisis.ipynb` en tu computador también necesitas Jupyter (`pip install jupyter`). En Colab ya viene instalado.

Pasos:

```bash
# 1. Clona el repo
git clone https://github.com/al3924/yallego-b1
cd yallego-b1

# 2. Pon YaLlego_datos.zip en la raíz del proyecto o en data/ (los datos no están en el repo)

# 3. Corre el pipeline
python pipeline.py
```

Si la carpeta `YaLlego/` no existe, el pipeline descomprime el ZIP solo. Crea `yallego.duckdb` desde cero, así que puedes correrlo las veces que quieras y da lo mismo.

### En Google Colab

```python
!git clone https://github.com/al3924/yallego-b1
%cd yallego-b1
# Sube YaLlego_datos.zip al panel de archivos, luego:
!pip install -q pandera duckdb openpyxl
!python pipeline.py
```

---

## Análisis

Con las tablas oro listas, `analisis.ipynb` responde las 5 preguntas de Valeria. Cada una tiene su consulta y gráfico, una celda de control, el número clave, la frase para Valeria y el abogado del diablo (riesgos revisados y qué cambiamos). El resumen de una página está en `memo.md`.

---

## Capas de datos

```
┌─────────────────────────────────────────────────────────────┐
│  FUENTES                                                    │
│  raw/pedidos/ (12 archivos CSV/JSON)                        │
│  restaurantes.xlsx · riders_api.json · zonas.csv            │
│  clima_cbba_2025.json · feriados (API, con respaldo)        │
└────────────────────────┬────────────────────────────────────┘
                         │  extraer()
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  🟫 BRONCE  (crudo, sin tocar)                              │
│  bronce_pedidos — 76.232 filas                              │
│  Todo como texto + columna archivo_origen.                  │
│  Si cambia una regla de limpieza, se rehace plata desde acá │
│  sin volver a leer los archivos.                            │
└────────────────────────┬────────────────────────────────────┘
                         │  transformar() + validar()
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  🥈 PLATA  (limpia y validada con Pandera)                  │
│  plata_pedidos        — 75.332 filas (sin los 900 de abril) │
│  plata_restaurantes   — 40 filas                            │
│  plata_riders         — 120 filas                           │
│  plata_zonas          — 12 filas                            │
│  plata_clima          — 365 filas                           │
│  plata_feriados       — 12 filas  [fuente: API]             │
│  rechazos_pedidos     — 0 filas (con columna motivo)        │
└────────────────────────┬────────────────────────────────────┘
                         │  cargar() — JOINs y agregaciones SQL
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  🥇 ORO  (lista para analizar)                              │
│  oro_pedidos                    — 75.332 filas              │
│  oro_diario                     — 365 filas (1 por día)     │
│  oro_rendimiento_restaurantes   — 40 filas                  │
│  oro_rendimiento_riders         — 120 filas                 │
└─────────────────────────────────────────────────────────────┘
```

---

## Puntos de control

Resultado de correr `python pipeline.py` **dos veces seguidas**, con los mismos conteos:

| Control | Esperado | ✔/✘ |
|---|---|---|
| `bronce_pedidos` | 76.232 filas | ✔ |
| `plata_pedidos` | 75.332 filas | ✔ |
| `oro_diario` | 365 filas | ✔ |
| Días con lluvia ≥ 1 mm | 81 | ✔ |
| Miércoles con promo (desde el 2/7) | 27 | ✔ |
| Suma de `monto_bs` | Bs 4.421.271 (±1) | ✔ |
| Fuente de feriados | `api` | ✔ |

### Evidencia de las dos corridas

Las dos corridas imprimieron lo mismo: feriados desde la **API** (12 registros), las 12 tablas con los conteos del diagrama y los 6 controles en ✔.

```
=== PUNTOS DE CONTROL ===
✔ bronce_pedidos = 76.232
✔ plata_pedidos = 75.332
✔ oro_diario = 365 filas
✔ 81 días con lluvia >= 1 mm
✔ 27 miércoles con promo (desde el 2/7)
✔ suma monto_bs ~ 4.421.271 (+-1)
Fuente de los feriados: api
```

**Corrida 1:** extracción, validación y conteo de tablas.

![Corrida 1: extracción, validación y conteos](capturas/pipeline_1.png)

**Fin de la corrida 1 e inicio de la corrida 2:** la segunda borra la base anterior y la crea de nuevo.

![Controles de la corrida 1 e inicio de la corrida 2](capturas/pipeline_2.png)

**Corrida 2:** mismos conteos y controles.

![Corrida 2: conteos y puntos de control](capturas/pipeline_3.png)

---

## Atrapé a la IA

**Caso 1: la escala de calificaciones de septiembre**

- **Qué pedimos:** limpiar `calificacion` en septiembre, donde del 15 al 30 la escala pasa de 1–5 a 1–10.
- **Qué hizo mal:** dividió entre 2 solo las calificaciones mayores a 5. Las que valían 3, 4 o 5 en escala 1–10 quedaron sin convertir.
- **Cómo lo detectamos:** desde el 15/09 hay 2.299 calificaciones, pero la regla solo tocaba 2.080. Con esa regla el promedio del 15 al 30 daba 4,16; el correcto es 3,94.
- **Cómo lo corregimos:** la regla pasó a ser por fecha (del 15/09 al 30/09) y no por valor.

**Caso 2: la promo "Miércoles sin envío"**

- **Qué pedimos:** marcar los días con la promo en las tablas oro.
- **Qué hizo mal:** marcó todos los miércoles del año (53), pero la promo empezó el 2/7.
- **Cómo lo detectamos:** revisamos el costo de envío. Desde el 2/7 es 0 en todos los miércoles, y antes del 2/7 en ninguno (0 de 4.037). Las marcas correctas son 27, no 53.
- **Cómo lo corregimos:** la promo se marca solo en miércoles con fecha desde el 2025-07-02.

---

## Declaración de uso de IA

Usamos Claude, ChatGPT y Gemini para escribir y corregir código, consultas SQL y gráficos, y para revisar nuestras conclusiones (abogado del diablo). `calidad.md`, las conclusiones del notebook y el memo se redactaron con ayuda de IA, y los revisamos y ajustamos nosotros. Las decisiones de negocio son nuestras.

### Prompts principales

**Misión 1 — Perfilado:**
```
Soy estudiante y estoy aprendiendo ingeniería de datos con pandas en Google Colab.
Tengo 12 archivos de pedidos en YaLlego/raw/pedidos/ (11 CSV y 1 JSON).
Escribe código que para cada archivo muestre: filas, columnas, tipos, nulos y 3 ejemplos.
Explícame cada línea. No limpies nada.
```

**Misión 3 — Plata (fechas Unix de enero):**
```
En mi tabla de pedidos, la columna fecha_hora del archivo pedidos_2025_01.csv
tiene valores como: 1735762813, 1735769200, 1735780045.
Quiero convertirlos a datetime sin afectar los otros meses que ya vienen en ISO.
Escribe una función pandas y dime cómo verifico que funcionó.
```

**Misión 3 — Plata (montos de febrero):**
```
La columna monto_bs de febrero tiene valores como "Bs 15,00", "Bs 44,97", "Bs 120,50".
Quiero convertirlos a float limpio. Escribe la función y dime cómo verifico.
```

**Misión 4 — Pandera:**
```
Tengo plata_pedidos con estas columnas y tipos: [dtypes].
Escribe un esquema pandera con lazy=True que valide:
pedido_id único, monto_bs > 0, calificacion entre 1.0 y 5.0,
estado solo "entregado" o "cancelado", zonas dentro de las 12 oficiales,
tiempo_entrega_min entre 1 y 240 (o nulo), y que un pedido cancelado
no tenga calificación ni tiempo. Guarda los rechazos con columna motivo.
```

**Misión 7 — Revisión del análisis (abogado del diablo):**
```
Revisa mi analisis.ipynb y mi memo.md contra lo que pide el enunciado.
Recalcula los números clave y dime qué conclusiones no se sostienen
o necesitan un control antes de llevárselas a Valeria.
```

**Misión 6 — pipeline.py:**
```
Junté el código de las misiones 2 a 5. Conviértelo en pipeline.py
con funciones extraer(), transformar(), validar() y cargar(),
que se ejecute con "python pipeline.py", cree yallego.duckdb desde cero
y al final imprima cuántas filas tiene cada tabla. No cambies las reglas de limpieza.
```

---

## Estructura del repositorio

```
yallego-b1/
├── README.md           ← este archivo
├── pipeline.py         ← ETL completo (crea yallego.duckdb)
├── esquemas.py         ← esquema Pandera de plata_pedidos
├── calidad.md          ← los 8 problemas, filas afectadas y decisiones
├── analisis.ipynb      ← P1–P5: consulta, gráfico, control, número, frase y abogado del diablo
├── memo.md             ← memo de 1 página para Valeria Rocha
├── capturas/           ← capturas de las 2 corridas del pipeline
├── .gitignore          ← excluye data/ y yallego.duckdb
└── data/               ← datos, NO subidos al repo
```

`yallego.duckdb` tampoco está en el repo: se genera con `python pipeline.py`.
