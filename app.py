"""
App de finanzas personales — Streamlit + Turso (libSQL).

Correr local:   streamlit run app.py
Deploy:         Streamlit Community Cloud (ver README.md)

Notas de arquitectura (lo distinto vs. un script Python normal):

  * Streamlit RE-EJECUTA este archivo entero de arriba a abajo en cada
    interacción (cada click, cada tecla). Por eso la conexión a la base
    se cachea con @st.cache_resource: se crea UNA vez y se reutiliza en
    todas las re-ejecuciones, en vez de abrir una conexión nueva por click.

  * NO cacheo las lecturas (los SELECT). Con ~1000 filas la query es
    instantánea, y así el dashboard siempre refleja el último INSERT sin
    tener que invalidar caches. Si algún día crece mucho, ahí sí conviene
    @st.cache_data con TTL.

  * Los secretos (URL, token, password) viven en st.secrets, NO en el
    código. Local: archivo .streamlit/secrets.toml. En la nube: se pegan
    en la UI de Streamlit Cloud. Nunca se commitean.
"""
import datetime as dt

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import libsql

st.set_page_config(page_title="Finanzas", page_icon="💸", layout="wide")

# Paleta simple y consistente para Ingreso/Egreso.
COLOR_ING = "#2E8B57"
COLOR_EGR = "#C0392B"


# ----------------------------------------------------------------------
# Conexión (cacheada como recurso: una sola por proceso)
# ----------------------------------------------------------------------
@st.cache_resource
def get_conn():
    return libsql.connect(
        database=st.secrets["TURSO_DATABASE_URL"],
        auth_token=st.secrets["TURSO_AUTH_TOKEN"],
    )


def query_df(sql, params=()):
    """Ejecuta un SELECT y devuelve un DataFrame (columnas desde el cursor)."""
    cur = get_conn().execute(sql, params)
    cols = [d[0] for d in cur.description]
    return pd.DataFrame(cur.fetchall(), columns=cols)


def fmt(x):
    """Formato de plata: $ 1.234.567 (separador de miles con punto)."""
    return f"$ {x:,.0f}".replace(",", ".")


# ----------------------------------------------------------------------
# Password gate (básico: una contraseña compartida, no es auth real)
# ----------------------------------------------------------------------
def check_password():
    if st.session_state.get("auth"):
        return True
    pw = st.text_input("Contraseña", type="password")
    if pw:
        if pw == st.secrets["APP_PASSWORD"]:
            st.session_state["auth"] = True
            st.rerun()
        else:
            st.error("Contraseña incorrecta")
    return False


if not check_password():
    st.stop()


# ----------------------------------------------------------------------
# Cargar catálogo de conceptos (para el dropdown)
# ----------------------------------------------------------------------
cat = query_df(
    "SELECT concepto, clasificacion FROM categorias ORDER BY clasificacion, concepto"
)
concepto_info = cat.set_index("concepto")[["clasificacion"]].to_dict("index")

st.title("💸 Finanzas")

tab_cargar, tab_dash, tab_detalle = st.tabs(["➕ Cargar", "📊 Dashboard", "📋 Detalle"])


# ======================================================================
# TAB 1 — Cargar un movimiento
# ======================================================================
with tab_cargar:
    st.subheader("Nuevo movimiento")
    with st.form("nuevo", clear_on_submit=True):
        c1, c2 = st.columns(2)
        fecha = c1.date_input("Fecha", value=dt.date.today())
        concepto = c2.selectbox("Categoría", cat["concepto"].tolist())
        info = concepto_info[concepto]
        c2.caption(f"→ **{info['clasificacion']}**")
        descripcion = st.text_input("Descripción", placeholder="ej: Super Día")
        monto = st.number_input("Monto", min_value=0.0, step=1000.0, format="%.0f")
        ok = st.form_submit_button("Guardar", type="primary", use_container_width=True)

    if ok:
        if monto <= 0:
            st.warning("El monto tiene que ser mayor a 0.")
        else:
            conn = get_conn()
            conn.execute(
                "INSERT INTO movimientos (fecha, concepto, descripcion, monto) "
                "VALUES (?, ?, ?, ?)",
                (fecha.isoformat(), concepto, descripcion or None, float(monto)),
            )
            conn.commit()
            st.success(f"Guardado: {concepto} · {fmt(monto)} ({info['clasificacion']})")


# ======================================================================
# TAB 2 — Dashboard
# ======================================================================
with tab_dash:
    # Base: todos los movimientos con su clasificacion (JOIN sólo para saber
    # si el concepto es Ingreso o Egreso).
    df = query_df(
        """
        SELECT m.fecha,
               strftime('%Y-%m', m.fecha) AS mes,
               m.concepto,
               c.clasificacion,
               m.monto
        FROM movimientos m
        JOIN categorias c ON m.concepto = c.concepto
        """
    )

    if df.empty:
        st.info("Todavía no hay datos. Cargá el primer movimiento en la pestaña ➕.")
        st.stop()

    # Filtros del dashboard: concepto (multi, vacío = todos) y mes.
    fc, fm = st.columns([2, 1])
    conceptos_all = sorted(df["concepto"].unique())
    sel = fc.multiselect("Categorías", conceptos_all,
                         placeholder="Todas las categorías")
    if sel:
        df = df[df["concepto"].isin(sel)]

    meses = sorted(df["mes"].unique())
    mes_sel = fm.selectbox("Mes", meses, index=len(meses) - 1)
    dmes = df[df["mes"] == mes_sel]

    ing = dmes.loc[dmes.clasificacion == "Ingreso", "monto"].sum()
    egr = dmes.loc[dmes.clasificacion == "Egreso", "monto"].sum()
    neto = ing - egr

    # --- KPIs ---------------------------------------------------------
    k1, k2, k3 = st.columns(3)
    k1.metric("Ingresos", fmt(ing))
    k2.metric("Egresos", fmt(egr))
    k3.metric("Neto (ahorro)", fmt(neto))

    st.divider()
    izq, der = st.columns(2)

    # --- (A) Balance ingreso/egreso por mes ---------------------------
    with izq:
        st.markdown("**Balance ingreso/egreso por mes**")
        bal = (
            df.groupby(["mes", "clasificacion"])["monto"].sum().reset_index()
        )
        fig = px.bar(
            bal, x="mes", y="monto", color="clasificacion", barmode="group",
            color_discrete_map={"Ingreso": COLOR_ING, "Egreso": COLOR_EGR},
        )
        fig.update_layout(showlegend=True, xaxis_title=None, yaxis_title=None,
                          legend_title=None, height=320, margin=dict(t=10))
        st.plotly_chart(fig, use_container_width=True)

    # --- (B) Egresos por concepto (del mes seleccionado) --------------
    with der:
        st.markdown(f"**Egresos por concepto · {mes_sel}**")
        eg = (
            dmes[dmes.clasificacion == "Egreso"]
            .groupby("concepto")["monto"].sum().reset_index()
            .sort_values("monto", ascending=False)
        )
        if eg.empty:
            st.caption("Sin egresos este mes.")
        else:
            figp = px.pie(eg, values="monto", names="concepto", hole=0.45)
            figp.update_traces(textposition="inside", textinfo="percent+label")
            figp.update_layout(showlegend=False, height=320, margin=dict(t=10))
            st.plotly_chart(figp, use_container_width=True)

    # --- (C) Evolución / tendencia del neto mensual -------------------
    st.markdown("**Evolución del neto mensual (ahorro)**")
    piv = (
        df.pivot_table(index="mes", columns="clasificacion", values="monto",
                       aggfunc="sum", fill_value=0)
        .reset_index()
    )
    piv["neto"] = piv.get("Ingreso", 0) - piv.get("Egreso", 0)
    piv["media_movil_3"] = piv["neto"].rolling(3, min_periods=1).mean()

    figl = go.Figure()
    figl.add_bar(x=piv["mes"], y=piv["neto"], name="Neto",
                 marker_color=[COLOR_ING if v >= 0 else COLOR_EGR for v in piv["neto"]])
    figl.add_scatter(x=piv["mes"], y=piv["media_movil_3"], name="Media móvil 3m",
                     mode="lines+markers", line=dict(color="#34495E", width=2))
    figl.update_layout(height=340, xaxis_title=None, yaxis_title=None,
                       legend_title=None, margin=dict(t=10))
    st.plotly_chart(figl, use_container_width=True)


# ======================================================================
# TAB 3 — Detalle filtrable + búsqueda
# ======================================================================
with tab_detalle:
    st.subheader("Detalle de movimientos")

    base = query_df(
        """
        SELECT m.id, m.fecha, m.concepto, c.clasificacion,
               m.descripcion, m.monto
        FROM movimientos m
        JOIN categorias c ON m.concepto = c.concepto
        ORDER BY m.fecha DESC, m.id DESC
        """
    )

    if base.empty:
        st.info("Sin datos aún.")
        st.stop()

    base["mes"] = base["fecha"].str.slice(0, 7)

    f1, f2, f3 = st.columns(3)
    meses_f = ["(todos)"] + sorted(base["mes"].unique(), reverse=True)
    mes_f = f1.selectbox("Mes", meses_f)
    cats_sel = f2.multiselect("Categorías", sorted(base["concepto"].unique()),
                              placeholder="Todas")
    clas_f = f3.selectbox("Tipo", ["(todos)", "Ingreso", "Egreso"])
    texto = st.text_input("Buscar en descripción", placeholder="ej: nafta")

    view = base.copy()
    if mes_f != "(todos)":
        view = view[view["mes"] == mes_f]
    if cats_sel:
        view = view[view["concepto"].isin(cats_sel)]
    if clas_f != "(todos)":
        view = view[view["clasificacion"] == clas_f]
    if texto:
        view = view[view["descripcion"].fillna("").str.contains(texto, case=False)]

    st.caption(f"{len(view)} movimientos · total {fmt(view['monto'].sum())}")
    st.dataframe(
        view[["fecha", "concepto", "descripcion", "monto"]],
        use_container_width=True, hide_index=True,
        column_config={
            "concepto": st.column_config.TextColumn("categoría"),
            "monto": st.column_config.NumberColumn("monto", format="$ %d"),
        },
    )
