"""
Consola SQL interactiva contra tu base Turso.

    python consulta.py

Escribís una consulta, Enter, y ves el resultado como tabla.
'salir' (o Ctrl+C) para terminar. Consultas de una línea.

Ejemplos para arrancar:
    SELECT * FROM movimientos LIMIT 10;
    SELECT concepto, SUM(monto) AS total FROM movimientos GROUP BY concepto ORDER BY total DESC;
    SELECT * FROM movimientos WHERE strftime('%Y-%m', fecha) = '2026-07' ORDER BY monto DESC;
"""
import pandas as pd
from migrate import get_conn

conn = get_conn()
pd.set_option("display.max_rows", 100)
pd.set_option("display.width", 200)

print("Consola SQL (escribí 'salir' para terminar)\n")
while True:
    try:
        sql = input("sql> ").strip()
    except (EOFError, KeyboardInterrupt):
        break
    if sql.lower() in ("salir", "exit", "quit"):
        break
    if not sql:
        continue
    try:
        cur = conn.execute(sql)
        if cur.description:                      # fue un SELECT: hay columnas
            cols = [d[0] for d in cur.description]
            df = pd.DataFrame(cur.fetchall(), columns=cols)
            print(df.to_string(index=False))
            print(f"({len(df)} filas)\n")
        else:                                    # INSERT/UPDATE/DELETE
            conn.commit()
            print("OK\n")
    except Exception as e:
        print("Error:", e, "\n")
