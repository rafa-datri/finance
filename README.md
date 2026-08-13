# Finanzas — Streamlit + Turso

App web de finanzas personales: formulario de carga (con dropdown de
categorías, adiós al tipeo inconsistente) + dashboard. La base es SQLite
hosteada (Turso/libSQL), así que persiste y entrás desde el celular
abriendo una URL, sin instalar nada.

## Estructura

```
app.py            # la app Streamlit (formulario + dashboard + detalle)
migrate.py        # carga única de tu Data.xlsx a Turso
schema.sql        # DDL de las tablas
requirements.txt  # dependencias
.streamlit/secrets.toml.example   # plantilla de secretos
```

## Puesta en marcha (una sola vez)

> **Windows:** no necesitás el CLI de Turso (ese exige WSL). Hacé todo
> desde el dashboard web + cmd/PowerShell, como está abajo.

### 1. Crear la base en Turso (desde el navegador)
1. Entrá a https://turso.tech y registrate (Sign up con GitHub).
2. En el dashboard, **Create Database** (nombre: `finanzas`).
3. En la página de la base, copiá:
   - la **URL** (empieza con `libsql://...`)
   - un **token**: botón *Create Token* / *Generate Token*.

(macOS/Linux, si preferís CLI: `brew install tursodatabase/tap/turso`,
`turso db create finanzas`, `turso db show finanzas --url`,
`turso db tokens create finanzas`.)

### 2. Configurar secretos localmente
Copiá `.streamlit/secrets.toml.example` a `.streamlit/secrets.toml` y pegá
tu URL, token y una contraseña. En cmd de Windows:
```cmd
copy .streamlit\secrets.toml.example .streamlit\secrets.toml
notepad .streamlit\secrets.toml
```

### 3. Instalar dependencias y migrar tus datos
```cmd
python -m pip install -r requirements.txt
python migrate.py Data.xlsx
```
`migrate.py` lee las credenciales del `secrets.toml` que completaste (no
hace falta setear variables de entorno). Crea las tablas y carga tus 989 filas.

### 4. Probar local
```cmd
python -m streamlit run app.py
```
Abre http://localhost:8501 en el navegador.

## Deploy para usar desde el celular

1. Subí el repo a GitHub (SIN `secrets.toml` ni `Data.xlsx` — ya están
   en `.gitignore`).
2. Entrá a https://share.streamlit.io → **New app** → elegí el repo y
   `app.py`.
3. En **Advanced settings → Secrets**, pegá el contenido de tu
   `secrets.toml` (las tres líneas: URL, token, password).
4. Deploy. Te da una URL pública tipo `tu-app.streamlit.app`.
5. En el celu, abrí esa URL y agregala a la pantalla de inicio
   ("Añadir a inicio") para que se comporte como una app.

## Por qué Turso y no un archivo `.db` local

Streamlit Community Cloud corre la app en un **contenedor efímero**: su
disco se reconstruye desde el repo en cada reinicio o redeploy. Un
`.db` local ahí se **borraría** al reiniciar (la doc oficial de Streamlit
lo advierte). Turso mantiene la base en sus servidores; la app se conecta
por red y los datos persisten. El SQL que escribís sigue siendo SQLite.

## Agregar o cambiar categorías

Editás la tabla `categorias` directo en Turso:
```bash
turso db shell finanzas
> INSERT INTO categorias VALUES ('Nafta', 'Auto', 'Egreso');
> .quit
```
El dropdown de la app se actualiza solo (lee esa tabla en cada carga).

## Notas

- El "password gate" es una barrera simple (una contraseña compartida),
  no autenticación real. Suficiente para una app personal; si querés algo
  más serio, mirá `streamlit-authenticator`.
- Free tier de Turso: verificá límites actuales en https://turso.tech/pricing
  (sobran para un libro contable personal).
