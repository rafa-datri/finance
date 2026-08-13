"""
Reduce las categorías a las 11 normalizadas: colapsa los 6 alias
(Otros, Food OUT, Food MET, Suscripciones, Regalo, Farmacia) sobre su
categoría real, sin perder ningún movimiento.

Se corre UNA vez:   python recategorize.py

Reutiliza la conexión de migrate.py (lee el mismo .streamlit/secrets.toml).
"""
from migrate import get_conn


def main():
    conn = get_conn()

    # 1. Remapear los movimientos que apuntan a un alias -> su categoría real.
    #    (Los alias son exactamente las filas de 'categorias' con concepto != categoria.)
    conn.execute(
        """
        UPDATE movimientos
        SET concepto = (
            SELECT categoria FROM categorias c WHERE c.concepto = movimientos.concepto
        )
        WHERE concepto IN (
            SELECT concepto FROM categorias WHERE concepto <> categoria
        )
        """
    )

    # 2. Borrar los alias del catálogo. Quedan sólo las 11 canónicas
    #    (aquellas donde concepto == categoria).
    conn.execute("DELETE FROM categorias WHERE concepto <> categoria")
    conn.commit()

    # 3. Verificación.
    n = conn.execute("SELECT COUNT(*) FROM categorias").fetchone()[0]
    cats = [r[0] for r in conn.execute(
        "SELECT concepto FROM categorias ORDER BY clasificacion, concepto"
    ).fetchall()]
    huerfanos = conn.execute(
        """
        SELECT COUNT(*) FROM movimientos m
        LEFT JOIN categorias c ON m.concepto = c.concepto
        WHERE c.concepto IS NULL
        """
    ).fetchone()[0]

    print(f"categorias ahora: {n}")
    print(cats)
    print(f"movimientos huérfanos (debe ser 0): {huerfanos}")


if __name__ == "__main__":
    main()
