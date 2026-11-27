# -*- coding: utf-8 -*-
import os
import sys
import glob
import json
import zipfile
import requests
import numpy as np
import pandas as pd
import duckdb
import pandera.pandas as pa
import esquemas

ZIP_CANDIDATOS = ["/content/YaLlego_datos.zip", "data/YaLlego_datos.zip", "YaLlego_datos.zip"]
EXTRACT_PATH = "."
DATOS_DIR = next((d for d in ["YaLlego", "data/YaLlego"] if os.path.exists(d)), "YaLlego")
DB_PATH = "yallego.duckdb"
INICIO_PROMO = "2025-07-02"
URL_FERIADOS = "https://date.nager.at/api/v3/PublicHolidays/2025/BO"

MAPA_ZONAS = {
    "centro": "Centro", "cala cala": "Cala Cala", "cala-cala": "Cala Cala", "calacala": "Cala Cala",
    "queru queru": "Queru Queru", "queru-queru": "Queru Queru", "sarco": "Sarco",
    "tupuraya": "Tupuraya", "muyurina": "Muyurina", "hipódromo": "Hipódromo", "hipodromo": "Hipódromo",
    "pacata": "Pacata", "temporal": "Temporal", "tiquipaya": "Tiquipaya", "sacaba": "Sacaba",
    "quillacollo": "Quillacollo", "quilla": "Quillacollo",
}

COLS_PLATA = [
    "pedido_id", "fecha_hora", "cod_cliente", "cod_rest", "restaurante_valido",
    "zona_entrega", "rider_id", "rider_asignado", "monto_bs", "costo_envio_bs", "propina_bs",
    "tiempo_entrega_min", "estado", "calificacion", "metodo_pago", "archivo_origen",
]


def extraer():
    print("--- INICIANDO EXTRACCIÓN ---")
    if not os.path.exists(DATOS_DIR):
        zip_path = next((z for z in ZIP_CANDIDATOS if os.path.exists(z)), None)
        if zip_path is None:
            raise FileNotFoundError(f"No existe '{DATOS_DIR}' ni el ZIP: {ZIP_CANDIDATOS}")
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(EXTRACT_PATH)
    else:
        print("El directorio 'YaLlego' ya existe.")

    frames = []
    for ruta in sorted(glob.glob(f"{DATOS_DIR}/raw/pedidos/*")):
        nombre = os.path.basename(ruta)
        ext = os.path.splitext(nombre)[1].lower()
        if ext == ".csv":
            df = pd.read_csv(ruta, dtype=str)
        elif ext == ".json":
            try:
                df = pd.read_json(ruta, dtype=str)
            except ValueError:
                with open(ruta, "r", encoding="utf-8") as f:
                    data = json.load(f)
                df = pd.json_normalize(data) if isinstance(data, (list, dict)) else pd.DataFrame(data)
        else:
            continue
        df["archivo_origen"] = nombre
        frames.append(df)

    bronce_pedidos = pd.concat(frames, ignore_index=True)
    print(f"Leídos {len(bronce_pedidos)} registros en bruto desde los archivos de pedidos.")

    restaurantes = pd.read_excel(f"{DATOS_DIR}/restaurantes.xlsx", header=2)
    with open(f"{DATOS_DIR}/riders_api.json", "r", encoding="utf-8") as f:
        riders_raw = json.load(f)
    zonas = pd.read_csv(f"{DATOS_DIR}/zonas.csv")
    with open(f"{DATOS_DIR}/clima_cbba_2025.json", "r", encoding="utf-8") as f:
        clima_raw = json.load(f)

    try:
        resp = requests.get(URL_FERIADOS, timeout=10)
        resp.raise_for_status()
        feriados_list = resp.json()
        if not feriados_list:
            raise ValueError("la API respondió vacío")
        fuente_feriados = "api"
    except Exception as e:
        print(f"API de feriados falló ({e}). Usando respaldo local...")
        with open(f"{DATOS_DIR}/feriados_bo_2025_respaldo.json", "r", encoding="utf-8") as f:
            feriados_list = json.load(f)
        fuente_feriados = "respaldo"

    print(f"Feriados: {len(feriados_list)} registros | FUENTE = {fuente_feriados}")

    return {
        "bronce_pedidos": bronce_pedidos,
        "restaurantes": restaurantes,
        "riders_raw": riders_raw,
        "zonas": zonas,
        "clima_raw": clima_raw,
        "feriados_list": feriados_list,
        "fuente_feriados": fuente_feriados,
    }


def transformar(datos_crudos):
    print("\n--- INICIANDO TRANSFORMACIÓN ---")
    bronce = datos_crudos["bronce_pedidos"]
    df = bronce.copy()

    df = df.replace({"nan": np.nan, "NaN": np.nan, "None": np.nan, "": np.nan})

    es_unix = df["fecha_hora"].str.fullmatch(r"\d{9,11}", na=False)
    fecha_unix = pd.to_datetime(pd.to_numeric(df["fecha_hora"].where(es_unix)), unit="s")
    fecha_iso = pd.to_datetime(df["fecha_hora"].where(~es_unix), format="%Y-%m-%d %H:%M:%S", errors="coerce")
    df["fecha_hora"] = fecha_unix.fillna(fecha_iso)

    for col in ["monto_bs", "costo_envio_bs", "propina_bs"]:
        limpio = (
            df[col].astype(str)
            .str.replace("Bs", "", regex=False)
            .str.replace(" ", "", regex=False)
            .str.replace(",", ".", regex=False)
        )
        df[col] = pd.to_numeric(limpio, errors="coerce")

    df["tiempo_entrega_min"] = pd.to_numeric(df["tiempo_entrega_min"], errors="coerce")
    df["calificacion"] = pd.to_numeric(df["calificacion"], errors="coerce")

    df["_orden"] = (df["estado"] == "en_camino").astype(int)
    df = (
        df.sort_values(["pedido_id", "_orden"])
        .drop_duplicates(subset=["pedido_id"], keep="first")
        .drop(columns="_orden")
        .reset_index(drop=True)
    )

    df["zona_entrega"] = df["zona_entrega"].astype(str).str.strip().str.lower().map(MAPA_ZONAS)

    malos = (df["tiempo_entrega_min"] < 0) | (df["tiempo_entrega_min"] == 999)
    df.loc[malos, "tiempo_entrega_min"] = np.nan

    esc10 = (df["fecha_hora"] >= "2025-09-15") & (df["fecha_hora"] < "2025-10-01")
    df.loc[esc10, "calificacion"] = df.loc[esc10, "calificacion"] / 2.0

    restaurantes_clean = datos_crudos["restaurantes"].dropna(subset=["cod_rest"])
    rest_validos = restaurantes_clean["cod_rest"].unique()
    df["restaurante_valido"] = df["cod_rest"].isin(rest_validos)

    df["rider_asignado"] = df["rider_id"].notna()

    plata_pedidos_df = df[COLS_PLATA].copy()

    riders_df = pd.json_normalize(datos_crudos["riders_raw"]["data"]).rename(
        columns={"id": "rider_id", "perfil.nombre": "nombre", "perfil.vehiculo": "vehiculo"}
    )
    riders_df["alta"] = pd.to_datetime(riders_df["alta"])

    cli = datos_crudos["clima_raw"]["daily"]
    clima_df = pd.DataFrame({
        "fecha": pd.to_datetime(cli["time"]),
        "temp_media_c": cli["temperature_2m_mean"],
        "lluvia_mm": cli["precipitation_sum"],
    })

    feriados_df = pd.DataFrame(datos_crudos["feriados_list"])
    if "global" in feriados_df.columns:
        feriados_df = feriados_df[feriados_df["global"].fillna(True).astype(bool)]
    feriados_df["fecha"] = pd.to_datetime(feriados_df["date"])
    feriados_df = feriados_df.groupby("fecha", as_index=False).agg(
        nombre_feriado=("localName", lambda s: " / ".join(s))
    )
    feriados_df["fuente"] = datos_crudos["fuente_feriados"]

    print("Transformación finalizada con éxito.")
    return {
        "bronce_pedidos_raw": bronce,
        "plata_pedidos": plata_pedidos_df,
        "restaurantes": restaurantes_clean,
        "riders": riders_df,
        "zonas": datos_crudos["zonas"],
        "clima": clima_df,
        "feriados": feriados_df,
    }


def validar(datos_transformados):
    print("\n--- INICIANDO VALIDACIÓN CON PANDERA ---")
    df_plata = datos_transformados["plata_pedidos"].reset_index(drop=True)
    try:
        valido = esquemas.esquema_plata_pedidos.validate(df_plata, lazy=True)
        rechazos = df_plata.iloc[0:0].copy()
        rechazos["motivo"] = pd.Series(dtype=str)
        print("✔ Validación exitosa. Cero (0) filas rechazadas.")
        return valido, rechazos
    except pa.errors.SchemaErrors as err:
        fc = err.failure_cases
        sin_indice = fc[fc["index"].isna()]
        if len(sin_indice):
            raise ValueError(f"Errores de esquema a nivel de columna o tabla:\n{sin_indice}") from err
        reglas_fila = {c.name for c in esquemas.esquema_plata_pedidos.checks}
        col = fc["column"].fillna("(fila)").astype(str).where(~fc["check"].isin(reglas_fila), "(fila)")
        fc = fc.assign(_m=col + ": " + fc["check"].astype(str)).drop_duplicates(["index", "_m"])
        motivos = fc.groupby("index")["_m"].agg("; ".join)
        idx = motivos.index.astype(int)
        rechazos = df_plata.loc[idx].copy()
        rechazos["motivo"] = motivos.values
        valido = df_plata.drop(index=idx).reset_index(drop=True)
        print(f"⚠ Validación finalizada: {len(valido)} válidos, {len(rechazos)} rechazados.")
        return valido, rechazos.reset_index(drop=True)


def cargar(datos_transformados, plata_validada, rechazos_df):
    print("\n--- INICIANDO CARGA EN DUCKDB ---")
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"Base de datos '{DB_PATH}' existente eliminada para inicialización limpia.")

    con = duckdb.connect(DB_PATH)
    try:
        con.register("bronce_pedidos_raw_df", datos_transformados["bronce_pedidos_raw"])
        con.register("plata_pedidos_val", plata_validada)
        con.register("rechazos_pedidos_val", rechazos_df)
        con.register("df_clima", datos_transformados["clima"])
        con.register("df_feriados", datos_transformados["feriados"])
        con.register("df_restaurantes", datos_transformados["restaurantes"])
        con.register("df_riders", datos_transformados["riders"])
        con.register("df_zonas", datos_transformados["zonas"])

        con.execute("CREATE TABLE bronce_pedidos AS SELECT * FROM bronce_pedidos_raw_df")
        con.execute("CREATE TABLE plata_pedidos AS SELECT * FROM plata_pedidos_val")
        con.execute("CREATE TABLE rechazos_pedidos AS SELECT * FROM rechazos_pedidos_val")

        con.execute("CREATE TABLE plata_restaurantes AS SELECT * FROM df_restaurantes")
        con.execute("CREATE TABLE plata_riders AS SELECT * FROM df_riders")
        con.execute("CREATE TABLE plata_zonas AS SELECT * FROM df_zonas")
        con.execute("CREATE TABLE plata_clima AS SELECT * FROM df_clima")
        con.execute("CREATE TABLE plata_feriados AS SELECT * FROM df_feriados")

        con.execute(f"""
        CREATE TABLE oro_pedidos AS
        SELECT
            p.*,
            CAST(p.fecha_hora AS DATE) AS fecha,
            EXTRACT(dow FROM p.fecha_hora) AS dia_semana,
            EXTRACT(hour FROM p.fecha_hora) AS hora,
            r.nombre AS restaurante_nombre,
            r.tipo_cocina AS restaurante_tipo_cocina,
            r.zona AS restaurante_zona,
            r.comision_pct AS restaurante_comision_pct,
            rd.nombre AS rider_nombre,
            rd.vehiculo AS rider_vehiculo,
            z.municipio AS zona_municipio,
            z.distancia_centro_km AS zona_distancia_centro_km,
            CASE WHEN p.estado = 'entregado' THEN p.monto_bs * r.comision_pct / 100.0 END AS comision_bs,
            CASE WHEN p.estado = 'entregado'
                 THEN COALESCE(p.monto_bs * r.comision_pct / 100.0, 0) + p.costo_envio_bs END AS ingreso_yallego_bs,
            (EXTRACT(dow FROM p.fecha_hora) = 3 AND CAST(p.fecha_hora AS DATE) >= DATE '{INICIO_PROMO}') AS es_promocion_miercoles
        FROM plata_pedidos p
        LEFT JOIN plata_restaurantes r ON p.cod_rest = r.cod_rest
        LEFT JOIN plata_riders rd ON p.rider_id = rd.rider_id
        LEFT JOIN plata_zonas z ON p.zona_entrega = z.zona
        """)

        con.execute(f"""
        CREATE TABLE oro_diario AS
        WITH pedidos_diarios AS (
            SELECT
                fecha,
                COUNT(pedido_id) AS total_pedidos,
                COUNT(CASE WHEN estado = 'entregado' THEN 1 END) AS pedidos_entregados,
                COUNT(CASE WHEN estado = 'cancelado' THEN 1 END) AS pedidos_cancelados,
                SUM(monto_bs) AS monto_total_bs,
                SUM(CASE WHEN estado = 'entregado' THEN monto_bs END) AS gmv_bs,
                SUM(comision_bs) AS comision_bs,
                SUM(CASE WHEN estado = 'entregado' THEN costo_envio_bs END) AS envio_cobrado_bs,
                SUM(ingreso_yallego_bs) AS ingreso_yallego_bs,
                SUM(propina_bs) AS total_propinas_bs,
                AVG(tiempo_entrega_min) AS tiempo_entrega_promedio_min,
                AVG(calificacion) AS calificacion_promedio
            FROM oro_pedidos
            GROUP BY 1
        )
        SELECT
            CAST(c.fecha AS DATE) AS fecha,
            COALESCE(p.total_pedidos, 0) AS total_pedidos,
            COALESCE(p.pedidos_entregados, 0) AS pedidos_entregados,
            COALESCE(p.pedidos_cancelados, 0) AS pedidos_cancelados,
            COALESCE(p.monto_total_bs, 0.0) AS monto_total_bs,
            COALESCE(p.gmv_bs, 0.0) AS gmv_bs,
            COALESCE(p.comision_bs, 0.0) AS comision_bs,
            COALESCE(p.envio_cobrado_bs, 0.0) AS envio_cobrado_bs,
            COALESCE(p.ingreso_yallego_bs, 0.0) AS ingreso_yallego_bs,
            COALESCE(p.total_propinas_bs, 0.0) AS total_propinas_bs,
            p.tiempo_entrega_promedio_min,
            p.calificacion_promedio,
            c.temp_media_c,
            c.lluvia_mm,
            (c.lluvia_mm >= 1.0) AS es_dia_lluvioso,
            (f.nombre_feriado IS NOT NULL) AS es_feriado,
            f.nombre_feriado,
            (EXTRACT(dow FROM c.fecha) = 3 AND CAST(c.fecha AS DATE) >= DATE '{INICIO_PROMO}') AS es_promocion_miercoles
        FROM plata_clima c
        LEFT JOIN pedidos_diarios p ON CAST(c.fecha AS DATE) = p.fecha
        LEFT JOIN plata_feriados f ON CAST(c.fecha AS DATE) = CAST(f.fecha AS DATE)
        ORDER BY c.fecha ASC
        """)

        con.execute("""
        CREATE TABLE oro_rendimiento_restaurantes AS
        SELECT
            cod_rest,
            restaurante_nombre,
            restaurante_tipo_cocina,
            restaurante_zona,
            restaurante_comision_pct,
            COUNT(pedido_id) AS total_pedidos,
            SUM(CASE WHEN estado = 'entregado' THEN monto_bs ELSE 0 END) AS gmv_entregado_bs,
            SUM(ingreso_yallego_bs) AS ingreso_yallego_bs,
            COUNT(CASE WHEN estado = 'cancelado' THEN 1 END) AS total_cancelados,
            ROUND(COUNT(CASE WHEN estado = 'cancelado' THEN 1 END) * 100.0 / COUNT(pedido_id), 2) AS tasa_cancelacion_pct,
            ROUND(AVG(calificacion), 2) AS calificacion_promedio,
            ROUND(AVG(tiempo_entrega_min), 2) AS tiempo_entrega_promedio_min
        FROM oro_pedidos
        WHERE restaurante_valido
        GROUP BY 1, 2, 3, 4, 5
        """)

        con.execute("""
        CREATE TABLE oro_rendimiento_riders AS
        SELECT
            rider_id,
            rider_nombre,
            rider_vehiculo,
            COUNT(pedido_id) AS total_pedidos_asignados,
            COUNT(CASE WHEN estado = 'entregado' THEN 1 END) AS total_entregados,
            COUNT(CASE WHEN estado = 'cancelado' THEN 1 END) AS total_cancelados,
            ROUND(COUNT(CASE WHEN estado = 'cancelado' THEN 1 END) * 100.0 / COUNT(pedido_id), 2) AS tasa_cancelacion_pct,
            ROUND(AVG(tiempo_entrega_min), 2) AS tiempo_entrega_promedio_min,
            ROUND(AVG(calificacion), 2) AS calificacion_promedio,
            ROUND(SUM(propina_bs), 2) AS total_propinas_acumuladas_bs
        FROM oro_pedidos
        WHERE rider_asignado
        GROUP BY 1, 2, 3
        """)

        print("✔ Carga de tablas completada con éxito.")

        tablas = con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_type = 'BASE TABLE' ORDER BY table_name"
        ).fetchall()
        conteos = {}
        print("\n================ RESUMEN DE CONTEOS DE TABLAS DUCKDB ================")
        for (tabla_nombre,) in tablas:
            conteos[tabla_nombre] = con.execute(f"SELECT COUNT(*) FROM {tabla_nombre}").fetchone()[0]
            print(f"Tabla: {tabla_nombre:<30} | Conteo de registros: {conteos[tabla_nombre]}")
        print("=====================================================================")

        dias_lluvia = con.execute("SELECT COUNT(*) FROM oro_diario WHERE lluvia_mm >= 1").fetchone()[0]
        dias_promo = con.execute("SELECT COUNT(*) FROM oro_diario WHERE es_promocion_miercoles").fetchone()[0]
        suma_monto = con.execute("SELECT ROUND(SUM(monto_bs), 2) FROM plata_pedidos").fetchone()[0]
        fuente = con.execute("SELECT ANY_VALUE(fuente) FROM plata_feriados").fetchone()[0]

        controles = [
            ("bronce_pedidos = 76.232", conteos["bronce_pedidos"] == 76232),
            ("plata_pedidos = 75.332", conteos["plata_pedidos"] == 75332),
            ("oro_diario = 365 filas", conteos["oro_diario"] == 365),
            ("81 días con lluvia >= 1 mm", dias_lluvia == 81),
            ("27 miércoles con promo (desde el 2/7)", dias_promo == 27),
            ("suma monto_bs ~ 4.421.271 (+-1)", abs(suma_monto - 4421271) <= 1),
        ]
        print("\n=== PUNTOS DE CONTROL ===")
        for nombre, ok in controles:
            print(("✔ " if ok else "✘ ") + nombre)
        print(f"Fuente de los feriados: {fuente}")
    finally:
        con.close()


if __name__ == "__main__":
    datos_crudos = extraer()
    datos_transformados = transformar(datos_crudos)
    plata_validada, rechazos_df = validar(datos_transformados)
    cargar(datos_transformados, plata_validada, rechazos_df)
    print("\n✔ ¡El pipeline.py se ha ejecutado de principio a fin de forma perfecta!")
