import streamlit as st
import requests
from datetime import datetime, date
import os
from dotenv import load_dotenv
load_dotenv()

# ---------------- CONFIG ----------------
st.set_page_config(page_title="Diagnóstico - Gafas Office", page_icon="🔍", layout="wide")

# ---------------- NOTION / ENV ----------------
try:
    NOTION_TOKEN = st.secrets["NOTION_TOKEN"]
except:
    NOTION_TOKEN = os.getenv("NOTION_TOKEN")

if not NOTION_TOKEN:
    st.error("❌ Falta NOTION_TOKEN")
    st.stop()

NOTION_VERSION = "2022-06-28"
DEVICES_ID = "43e15b677c8c4bd599d7c602f281f1da"
LOCATIONS_ID = "28758a35e4118045abe6e37534c44974"

headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": NOTION_VERSION,
}

# ---------------- HELPERS ----------------
def q(db, payload=None):
    """Consulta una base de datos de Notion"""
    if payload is None:
        payload = {"page_size": 200}
    r = requests.post(f"https://api.notion.com/v1/databases/{db}/query", json=payload, headers=headers)
    return r.json().get("results", [])

# ---------------- MAIN ----------------
st.title("🔍 Diagnóstico: Gafas en Office")
st.markdown("---")

# 1. Buscar la ubicación "Office"
st.subheader("1️⃣ Verificando ubicación 'Office'")
office_search = q(LOCATIONS_ID, {"filter": {"property": "Name", "title": {"equals": "Office"}}})

if not office_search:
    st.error("❌ No se encontró una ubicación llamada exactamente 'Office'")
    st.info("💡 Verifica en Notion que la ubicación se llame 'Office' (sin espacios extras, mayúsculas exactas)")
    
    # Mostrar todas las ubicaciones disponibles
    st.markdown("### Ubicaciones disponibles en tu base de datos:")
    all_locations = q(LOCATIONS_ID)
    for loc in all_locations:
        name = loc["properties"]["Name"]["title"][0]["text"]["content"] if loc["properties"]["Name"]["title"] else "Sin nombre"
        loc_type = loc["properties"]["Type"]["select"]["name"] if loc["properties"]["Type"]["select"] else "Sin tipo"
        st.write(f"- **{name}** (Tipo: {loc_type})")
    
    st.stop()
else:
    office_id = office_search[0]["id"]
    st.success(f"✅ Ubicación 'Office' encontrada (ID: {office_id[:8]}...)")

st.markdown("---")

# 2. Cargar TODOS los dispositivos
st.subheader("2️⃣ Cargando todos los dispositivos")
all_devices = q(DEVICES_ID)
st.info(f"📊 Total de dispositivos en la base de datos: **{len(all_devices)}**")

st.markdown("---")

# 3. Analizar cada dispositivo
st.subheader("3️⃣ Análisis detallado de dispositivos")

devices_in_office = []
devices_without_location = []
devices_in_other_locations = []

for p in all_devices:
    props = p["properties"]
    
    # Extraer nombre
    name = props["Name"]["title"][0]["text"]["content"] if props["Name"]["title"] else "Sin nombre"
    
    # Extraer ubicaciones
    location_ids = [r["id"] for r in props["Location"]["relation"]]
    
    # Clasificar
    if office_id in location_ids:
        devices_in_office.append({
            "name": name,
            "location_count": len(location_ids),
            "id": p["id"]
        })
    elif len(location_ids) == 0:
        devices_without_location.append({
            "name": name,
            "id": p["id"]
        })
    else:
        devices_in_other_locations.append({
            "name": name,
            "location_ids": location_ids,
            "id": p["id"]
        })

# Mostrar resultados
col1, col2, col3 = st.columns(3)

with col1:
    st.metric("🟢 En Office", len(devices_in_office))
    
with col2:
    st.metric("⚪ Sin ubicación", len(devices_without_location))
    
with col3:
    st.metric("🔵 En otras ubicaciones", len(devices_in_other_locations))

st.markdown("---")

# Detalles de dispositivos EN OFFICE
st.subheader("🟢 Dispositivos en Office")
if devices_in_office:
    for idx, d in enumerate(devices_in_office, 1):
        st.write(f"{idx}. **{d['name']}**")
else:
    st.warning("No hay dispositivos en Office")

st.markdown("---")

# Detalles de dispositivos SIN UBICACIÓN
st.subheader("⚪ Dispositivos sin ubicación asignada")
if devices_without_location:
    st.warning(f"Estos {len(devices_without_location)} dispositivos NO tienen ninguna ubicación asignada:")
    for idx, d in enumerate(devices_without_location, 1):
        st.write(f"{idx}. **{d['name']}**")
    st.info("💡 Para que aparezcan en 'Gafas para Equipo', asígnales la ubicación 'Office' en Notion")
else:
    st.success("Todos los dispositivos tienen ubicación asignada")

st.markdown("---")

# Detalles de dispositivos EN OTRAS UBICACIONES
st.subheader("🔵 Dispositivos en otras ubicaciones")
if devices_in_other_locations:
    st.info(f"Estos {len(devices_in_other_locations)} dispositivos están en ubicaciones diferentes a Office:")
    
    # Cargar nombres de todas las ubicaciones
    all_locs = q(LOCATIONS_ID)
    location_names = {}
    for loc in all_locs:
        loc_id = loc["id"]
        loc_name = loc["properties"]["Name"]["title"][0]["text"]["content"] if loc["properties"]["Name"]["title"] else "Sin nombre"
        location_names[loc_id] = loc_name
    
    for idx, d in enumerate(devices_in_other_locations, 1):
        # Obtener nombres de las ubicaciones
        loc_list = [location_names.get(lid, "Ubicación desconocida") for lid in d["location_ids"]]
        locations_str = ", ".join(loc_list)
        st.write(f"{idx}. **{d['name']}** → Ubicación: {locations_str}")
else:
    st.success("No hay dispositivos en otras ubicaciones")

st.markdown("---")

# Resumen final
st.subheader("📋 Resumen")
st.write(f"""
**Dispositivos encontrados:**
- ✅ En Office: **{len(devices_in_office)}** (estos aparecen en "Gafas para Equipo")
- ⚠️ Sin ubicación: **{len(devices_without_location)}** (estos NO aparecen)
- ℹ️ En otras ubicaciones: **{len(devices_in_other_locations)}** (estos NO aparecen)

**Total:** {len(all_devices)} dispositivos
""")

if len(devices_in_office) < 8:
    st.warning(f"""
    ### ⚠️ Problema detectado
    
    Solo hay **{len(devices_in_office)} dispositivos** con la ubicación "Office" asignada.
    
    **Faltan {8 - len(devices_in_office)} dispositivos** para llegar a las 8 gafas que mencionas.
    
    **Solución:**
    1. Ve a Notion → Base de datos "Devices"
    2. Encuentra los dispositivos que aparecen arriba en "Sin ubicación" o "En otras ubicaciones"
    3. Asígnales la ubicación "Office" en la columna "Location"
    4. Vuelve a la app y haz clic en "🔄 Refrescar Datos"
    """)