-- ============================================================
--  Esquema de la base de finanzas (SQLite / libSQL / Turso)
-- ============================================================
-- Dos tablas:
--   categorias  = catálogo de conceptos. Alimenta el dropdown y define,
--                 para cada concepto, si es Ingreso o Egreso.
--   movimientos = cada fila es un gasto o ingreso. La clasificacion se
--                 deriva por JOIN contra categorias (no se guarda redundante).
-- ============================================================

CREATE TABLE IF NOT EXISTS categorias (
    concepto      TEXT PRIMARY KEY,   -- lo que elegís en el dropdown
    clasificacion TEXT NOT NULL CHECK (clasificacion IN ('Ingreso','Egreso'))
);

CREATE TABLE IF NOT EXISTS movimientos (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha         DATE NOT NULL,                       -- 'YYYY-MM-DD'
    concepto      TEXT NOT NULL REFERENCES categorias(concepto),
    descripcion   TEXT,
    monto         REAL NOT NULL CHECK (monto >= 0),
    creado_en     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_mov_fecha ON movimientos(fecha);
