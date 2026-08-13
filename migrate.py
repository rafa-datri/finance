"""
Migración única: carga tu Data.xlsx existente a la base Turso.

Se corre UNA vez, desde tu máquina (no en Streamlit). En Windows,
completá antes .streamlit/secrets.toml (URL + token) y:

    python migrate.py Data.xlsx

(Toma las credenciales de .streamlit/secrets.toml. Si preferís variables
de entorno, también las lee de ahí y tienen prioridad.)

Qué hace:
  1. Crea las tablas (ejecutando schema.sql statement por statement).
  2. Carga la hoja 'key' en 'categorias'.
  3. Carga la hoja 'Movimientos' en 'movimientos', normalizando cada
     'Detalle' crudo al concepto canónico de la key (case-insensitive)
     y salteando filas con Monto nulo.

Notas de rendimiento:
  * Las inserciones van con executemany (un solo lote), no fila por fila:
    con Turso remoto, cada execute() suelto es un round-trip de red, así
    que batchear ~1000 inserts es la diferencia real de velocidad.
  * La transformación es vectorizada en pandas (nada de iterrows()).
"""
import os
import re
import sys
import pandas as pd
import libsql

# Anclar rutas al directorio del script, no al directorio actual, para que
# funcione aunque lo corras desde otra carpeta.
HERE = os.path.dirname(os.path.abspath(__file__))
SECRETS_PATH = os.path.join(HERE, ".streamlit", "secrets.toml")
SCHEMA_PATH = os.path.join(HERE, "schema.sql")


def _read_secrets_toml(path):
    """Lee las claves del secrets.toml. Usa tomllib (Python 3.11+) y si no
    está disponible, cae a un parseo mínimo de líneas KEY = "valor"."""
    if not os.path.exists(path):
        return {}
    try:
        import tomllib  # Python 3.11+
        with open(path, "rb") as f:
            return tomllib.load(f)
    except ModuleNotFoundError:
        out = {}
        with open(path, encoding="utf-8") as f:
            for line in f:
                m = re.match(r'\s*(\w+)\s*=\s*"([^"]*)"', line)
                if m:
                    out[m.group(1)] = m.group(2)
        return out


def get_conn():
    secrets = _read_secrets_toml(SECRETS_PATH)
    # Entorno primero; secrets.toml como respaldo.
    url = os.environ.get("TURSO_DATABASE_URL") or secrets.get("TURSO_DATABASE_URL")
    token = os.environ.get("TURSO_AUTH_TOKEN") or secrets.get("TURSO_AUTH_TOKEN")
    if not url or not token:
        sys.exit(
            "Faltan TURSO_DATABASE_URL / TURSO_AUTH_TOKEN.\n"
            "Completalos en .streamlit/secrets.toml (copiá el .example) o "
            "definilos como variables de entorno."
        )
    # Pasar la URL remota como 'database' => conexión directa a la nube.
    return libsql.connect(database=url, auth_token=token)


def run_schema(conn, path):
    """Ejecuta el .sql statement por statement. Evita executescript(), que
    puede no estar implementado en el cliente libsql de Python."""
    with open(path, encoding="utf-8") as f:
        sql = f.read()
    for chunk in sql.split(";"):
        # Descartar líneas que son sólo comentario para no ejecutar vacíos.
        cuerpo = "\n".join(
            ln for ln in chunk.splitlines() if not ln.strip().startswith("--")
        ).strip()
        if cuerpo:
            conn.execute(cuerpo)
    conn.commit()


def load_categorias(conn, xlsx_path):
    key = pd.read_excel(xlsx_path, sheet_name="key").rename(
        columns={"Concepto": "concepto", "Key": "categoria",
                 "Clasificación": "clasificacion"}
    )
    for c in ["concepto", "categoria", "clasificacion"]:
        key[c] = key[c].astype(str).str.strip()

    rows = key[["concepto", "categoria", "clasificacion"]].values.tolist()
    conn.executemany(
        "INSERT OR REPLACE INTO categorias (concepto, categoria, clasificacion) "
        "VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()
    print(f"categorias: {len(rows)} filas cargadas")
    # Mapa case-insensitive: 'detalle crudo' -> concepto canónico
    return {c.lower(): c for c in key["concepto"]}


def load_movimientos(conn, xlsx_path, canon, chunk=100):
    mov = pd.read_excel(xlsx_path, sheet_name="Movimientos")

    # Transformación vectorizada (sin iterrows).
    mov["concepto"] = mov["Detalle"].astype(str).str.strip().str.lower().map(canon)
    mov["fecha"] = pd.to_datetime(mov["Date"]).dt.date.astype(str)   # 'YYYY-MM-DD'
    mov["descripcion"] = mov["Descripción"].where(mov["Descripción"].notna(), None)
    mov["monto"] = mov["Monto"].astype(float)

    valido = mov["Monto"].notna() & mov["concepto"].notna()
    sin_mapear = sorted(
        set(mov.loc[mov["Monto"].notna() & mov["concepto"].isna(), "Detalle"].astype(str))
    )

    rows = mov.loc[valido, ["fecha", "concepto", "descripcion", "monto"]].values.tolist()

    # Insertar en lotes con INSERT ... VALUES multi-fila: un solo round-trip
    # de red por lote (~10 en total), en vez de una request gigante o 989
    # inserts sueltos. Con progreso para ver que avanza.
    total = 0
    for i in range(0, len(rows), chunk):
        lote = rows[i:i + chunk]
        placeholders = ", ".join(["(?, ?, ?, ?)"] * len(lote))
        params = [v for fila in lote for v in fila]   # aplanar las tuplas
        conn.execute(
            "INSERT INTO movimientos (fecha, concepto, descripcion, monto) VALUES "
            + placeholders,
            params,
        )
        conn.commit()
        total += len(lote)
        print(f"  ... {total}/{len(rows)} movimientos")

    print(f"movimientos: {total} insertadas, {int((~valido).sum())} salteadas")
    if sin_mapear:
        print("  OJO, Detalle sin mapear en la key:", sin_mapear)


def main(xlsx_path):
    conn = get_conn()
    run_schema(conn, SCHEMA_PATH)

    # Guarda: si ya hay movimientos, no dupliques.
    ya = conn.execute("SELECT COUNT(*) FROM movimientos").fetchone()[0]
    if ya:
        sys.exit(f"La tabla movimientos ya tiene {ya} filas. Abortando para no duplicar.")

    canon = load_categorias(conn, xlsx_path)
    load_movimientos(conn, xlsx_path, canon)


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "Data.xlsx"
    main(path)