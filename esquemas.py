"""Esquema pandera de plata_pedidos (YaLlegó Delivery)."""
import pandas as pd
from pandera.pandas import Column, Check, DataFrameSchema

ZONAS_OFICIALES = [
    "Centro", "Cala Cala", "Queru Queru", "Sarco", "Tupuraya", "Muyurina",
    "Hipódromo", "Pacata", "Temporal", "Tiquipaya", "Sacaba", "Quillacollo",
]

esquema_plata_pedidos = DataFrameSchema(
    columns={
        # Integridad: un pedido = una fila, con formato de código válido
        "pedido_id": Column(str, checks=Check.str_matches(r"^P\d{6}$"), unique=True, nullable=False),
        # Todo el dataset es de 2025
        "fecha_hora": Column("datetime64[ns]", checks=[
            Check.greater_than_or_equal_to(pd.Timestamp("2025-01-01")),
            Check.less_than(pd.Timestamp("2026-01-01")),
        ], nullable=False),
        "cod_cliente": Column(str, checks=Check.str_matches(r"^C\d{5}$"), nullable=False),
        "cod_rest": Column(str, checks=Check.str_matches(r"^R\d{3}$"), nullable=False),
        "restaurante_valido": Column(bool, nullable=False),
        "zona_entrega": Column(str, checks=Check.isin(ZONAS_OFICIALES), nullable=False),
        # rider_id puede ser nulo (300 casos en diciembre); se marca en rider_asignado
        "rider_id": Column(str, checks=Check.str_matches(r"^RD\d{3}$"), nullable=True),
        "rider_asignado": Column(bool, nullable=False),
        # Dinero: el monto siempre es positivo; envío y propina pueden ser 0
        "monto_bs": Column(float, checks=Check.greater_than(0), nullable=False),
        "costo_envio_bs": Column(float, checks=Check.greater_than_or_equal_to(0), nullable=False),
        "propina_bs": Column(float, checks=Check.greater_than_or_equal_to(0), nullable=False),
        # Los tiempos imposibles (<0, 999) ya se pasaron a nulo en plata
        "tiempo_entrega_min": Column(float, checks=Check.in_range(1, 240), nullable=True),
        # 'en_camino' (copias duplicadas de abril) no debe llegar a plata
        "estado": Column(str, checks=Check.isin(["entregado", "cancelado"]), nullable=False),
        "calificacion": Column(float, checks=Check.in_range(1.0, 5.0), nullable=True),
        "metodo_pago": Column(str, checks=Check.isin(["QR", "efectivo", "tarjeta"]), nullable=False),
        "archivo_origen": Column(str, nullable=False),
    },
    checks=[
        # Regla de negocio: un pedido cancelado no tiene tiempo de entrega ni calificación
        Check(
            lambda df: ~((df["estado"] == "cancelado")
                         & (df["calificacion"].notna() | df["tiempo_entrega_min"].notna())),
            name="cancelado_sin_calificacion_ni_tiempo",
        ),
    ],
    strict=False,
    coerce=True,
)
