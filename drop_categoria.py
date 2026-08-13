"""
Elimina la columna redundante 'categoria' de la tabla 'categorias'.
Ahora que concepto == categoria, la columna no aporta nada.

Se corre UNA vez, DESPUÉS de actualizar app.py:   python drop_categoria.py

Reutiliza la conexión de migrate.py (mismo .streamlit/secrets.toml).
"""
from migrate import get_conn


def main():
    conn = get_conn()

    cols = [r[1] for r in conn.execute("PRAGMA table_info(categorias)").fetchall()]
    if "categoria" not in cols:
        print("La columna 'categoria' ya no existe. Nada que hacer.")
        return

    try:
        # SQLite/libSQL modernos soportan DROP COLUMN directo.
        conn.execute("ALTER TABLE categorias DROP COLUMN categoria")
        conn.commit()
    except Exception:
        # Respaldo universal: recrear la tabla sin la columna.
        conn.execute("ALTER TABLE categorias RENAME TO categorias_old")
        conn.execute(
            "CREATE TABLE categorias ("
            "  concepto TEXT PRIMARY KEY,"
            "  clasificacion TEXT NOT NULL CHECK (clasificacion IN ('Ingreso','Egreso'))"
            ")"
        )
        conn.execute(
            "INSERT INTO categorias (concepto, clasificacion) "
            "SELECT concepto, clasificacion FROM categorias_old"
        )
        conn.execute("DROP TABLE categorias_old")
        conn.commit()

    cols = [r[1] for r in conn.execute("PRAGMA table_info(categorias)").fetchall()]
    print("Columnas de 'categorias' ahora:", cols)
    print("Categorías:", [r[0] for r in conn.execute(
        "SELECT concepto FROM categorias ORDER BY clasificacion, concepto").fetchall()])


if __name__ == "__main__":
    main()
