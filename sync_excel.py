"""
Sincroniza filas NUEVAS del Excel hacia Turso, sin duplicar las que ya están.

    python sync_excel.py Data.xlsx

Seguro de re-correr: compara por (fecha, concepto, descripcion, monto).
Lo que ya está en la base se saltea; solo inserta lo que falta. No toca los
movimientos que cargaste por la app.

Nota: dos filas idénticas en todo (misma fecha, categoría, descripción y
monto) se consideran la misma. Si tenés gastos legítimamente repetidos,
diferencialos con la descripción.
"""
import sys
import pandas as pd
from migrate import get_conn


def main(xlsx_path):
    conn = get_conn()

    # Detalle crudo -> categoría de las 11 (columna 'Key' del Excel), que es
    # lo que hoy vive en la tabla categorias tras la reducción a 11.
    key = pd.read_excel(xlsx_path, sheet_name="key")
    canon = {str(c).strip().lower(): str(k).strip()
             for c, k in zip(key["Concepto"], key["Key"])}
    validas = {r[0] for r in conn.execute("SELECT concepto FROM categorias").fetchall()}

    mov = pd.read_excel(xlsx_path, sheet_name="Movimientos")
    mov["concepto"] = mov["Detalle"].astype(str).str.strip().str.lower().map(canon)
    mov["fecha"] = pd.to_datetime(mov["Date"]).dt.date.astype(str)
    mov["descripcion"] = mov["Descripción"].where(mov["Descripción"].notna(), None)
    mov["monto"] = mov["Monto"].astype(float)

    ok = mov["Monto"].notna() & mov["concepto"].notna() & mov["concepto"].isin(validas)
    filas = mov.loc[ok, ["fecha", "concepto", "descripcion", "monto"]].values.tolist()

    # Lo que ya está en la base.
    existentes = set(
        (f, c, d, float(m))
        for f, c, d, m in conn.execute(
            "SELECT fecha, concepto, descripcion, monto FROM movimientos"
        ).fetchall()
    )
    nuevas = [r for r in filas if (r[0], r[1], r[2], r[3]) not in existentes]

    # Insertar en lotes (INSERT multi-fila, un round-trip por lote).
    chunk = 100
    for i in range(0, len(nuevas), chunk):
        lote = nuevas[i:i + chunk]
        ph = ", ".join(["(?, ?, ?, ?)"] * len(lote))
        params = [v for fila in lote for v in fila]
        conn.execute(
            "INSERT INTO movimientos (fecha, concepto, descripcion, monto) VALUES " + ph,
            params,
        )
        conn.commit()

    print(f"Filas válidas en el Excel: {len(filas)}")
    print(f"Ya estaban en la base:     {len(filas) - len(nuevas)}")
    print(f"Nuevas insertadas:         {len(nuevas)}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "Data.xlsx")
