# app.py
import streamlit as st
import requests
from datetime import datetime, date
import os
from dotenv import load_dotenv
load_dotenv()

# ---------------------------
# Configuración de la página
# ---------------------------
st.set_page_config(
    page_title="Disponibilidad de dispositivos",
    page_icon="img/icono.png",
    layout="centered"
)

logo_col, title_col = st.columns([1, 9])
with logo_col:
    st.markdown("<div style='margin-top: 30px;'></div>", unsafe_allow_html=True)
    st.image("img/icono.png", width=80)
with title_col:
    st.markdown("<h1 style='margin-top: 20px;'>Disponibilidad de dispositivos</h1>", unsafe_allow_html=True)

st.markdown("Consulta qué dispositivos están disponibles para alquilar en un rango de fechas")
st.markdown("---")

# ---------------------------
# Configuración de Notion
# ---------------------------
try:
    NOTION_TOKEN = st.secrets["NOTION_TOKEN"]
except:
    NOTION_TOKEN = os.getenv("NOTION_TOKEN")

if not NOTION_TOKEN:
    st.error("❌ No se encontró NOTION_TOKEN. Configura st.secrets o el archivo .env")
    st.stop()

NOTION_VERSION = "2022-06-28"
DEVICES_ID = "43e15b677c8c4bd599d7c602f281f1da"
LOCATIONS_ID = "28758a35e4118045abe6e37534c44974"

headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": NOTION_VERSION,
}

# ---------------------------
# Utilidades Notion
# ---------------------------
def get_pages(database_id, payload=None):
    """Obtiene páginas de una base de datos (query). payload opcional para filtros."""
    url = f"https://api.notion.com/v1/databases/{database_id}/query"
    if payload is None:
        payload = {"page_size": 100}
    response = requests.post(url, json=payload, headers=headers)
    data = response.json()
    return data.get("results", [])

def get_page(page_id):
    """Obtiene una página por id (GET /pages/{id})"""
    url = f"https://api.notion.com/v1/pages/{page_id}"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    return None

def extract_device_data(page):
    """Extrae campos de una página device: id, Name, Tags, location_ids, Start Date, End Date, Locations_demo_count"""
    props = page.get("properties", {})
    device_data = {"id": page.get("id")}

    # Name
    try:
        if props.get("Name") and props["Name"]["title"]:
            device_data["Name"] = props["Name"]["title"][0]["text"]["content"]
        else:
            device_data["Name"] = "Sin nombre"
    except:
        device_data["Name"] = "Sin nombre"

    # Tags
    try:
        if props.get("Tags") and props["Tags"]["select"]:
            device_data["Tags"] = props["Tags"]["select"]["name"]
        else:
            device_data["Tags"] = "Sin tag"
    except:
        device_data["Tags"] = "Sin tag"

    # Location relation ids (lista) y contador
    try:
        if props.get("Location") and props["Location"]["relation"]:
            location_ids = [rel["id"] for rel in props["Location"]["relation"]]
            device_data["location_ids"] = location_ids
            device_data["Locations_demo_count"] = len(location_ids)
        else:
            device_data["location_ids"] = []
            device_data["Locations_demo_count"] = 0
    except:
        device_data["location_ids"] = []
        device_data["Locations_demo_count"] = 0

    # Start Date (rollup) - similar a tu lógica previa
    try:
        if props.get("Start Date") and props["Start Date"]["rollup"]:
            rollup = props["Start Date"]["rollup"]
            if rollup["type"] == "date" and rollup.get("date"):
                device_data["Start Date"] = rollup["date"]["start"]
            elif rollup["type"] == "array" and rollup["array"]:
                first_item = rollup["array"][0]
                if first_item["type"] == "date" and first_item.get("date"):
                    device_data["Start Date"] = first_item["date"]["start"]
                else:
                    device_data["Start Date"] = None
            else:
                device_data["Start Date"] = None
        else:
            device_data["Start Date"] = None
    except:
        device_data["Start Date"] = None

    # End Date (rollup)
    try:
        if props.get("End Date") and props["End Date"]["rollup"]:
            rollup = props["End Date"]["rollup"]
            if rollup["type"] == "date" and rollup.get("date"):
                device_data["End Date"] = rollup["date"]["start"]
            elif rollup["type"] == "array" and rollup["array"]:
                first_item = rollup["array"][0]
                if first_item["type"] == "date" and first_item.get("date"):
                    device_data["End Date"] = first_item["date"]["start"]
                else:
                    device_data["End Date"] = None
            else:
                device_data["End Date"] = None
        else:
            device_data["End Date"] = None
    except:
        device_data["End Date"] = None

    return device_data

def check_availability(device, start_date, end_date):
    """Comprueba si device está disponible entre start_date y end_date.
       Nota: no toca el criterio 'Location vacía' aquí; eso se filtra en la UI según tab."""
    # Si no tiene ubicación = disponible según lógica previa
    if device["Locations_demo_count"] == 0:
        return True

    device_start = device.get("Start Date")
    device_end = device.get("End Date")

    # Si tiene ubicación pero sin fechas = ocupado indefinidamente
    if device_start is None and device_end is None:
        return False

    # Convertir a date
    try:
        device_start_date = datetime.fromisoformat(device_start).date() if device_start else None
        device_end_date = datetime.fromisoformat(device_end).date() if device_end else None
    except:
        return False

    # Comparaciones de solapamiento
    if device_start_date and device_end_date:
        if (start_date <= device_end_date and end_date >= device_start_date):
            return False
        else:
            return True
    elif device_start_date and not device_end_date:
        if end_date >= device_start_date:
            return False
        else:
            return True
    elif device_end_date and not device_start_date:
        if start_date <= device_end_date:
            return False
        else:
            return True
    return True

# ---------------------------
# Funciones Locations
# ---------------------------
def get_in_house_locations():
    """Obtiene locations de tipo In House (id, name, device_count)"""
    payload = {
        "filter": {
            "property": "Type",
            "select": {"equals": "In House"}
        },
        "page_size": 100
    }
    pages = get_pages(LOCATIONS_ID, payload)
    locations = []
    for page in pages:
        props = page.get("properties", {})
        # Name
        try:
            if props.get("Name") and props["Name"]["title"]:
                name = props["Name"]["title"][0]["text"]["content"]
            else:
                name = "Sin nombre"
        except:
            name = "Sin nombre"
        # Units device count (opcional)
        try:
            device_count = props.get("Units", {}).get("number", 0) or 0
        except:
            device_count = 0
        locations.append({"id": page["id"], "name": name, "device_count": device_count})
    return locations

def get_office_location_by_name(office_name="Office"):
    """Busca la Location cuyo Name = office_name y devuelve su id y data (asume única)"""
    payload = {
        "filter": {
            "property": "Name",
            "title": {"equals": office_name}
        },
        "page_size": 1
    }
    pages = get_pages(LOCATIONS_ID, payload)
    if not pages:
        return None
    page = pages[0]
    props = page.get("properties", {})
    try:
        name = props.get("Name", {}).get("title", [])[0]["text"]["content"]
    except:
        name = "Office"
    return {"id": page["id"], "name": name}

def get_client_locations_future_start():
    """Obtiene Locations Type=Client y Start Date > hoy"""
    today_iso = date.today().isoformat()
    payload = {
        "filter": {
            "and": [
                {"property": "Type", "select": {"equals": "Client"}},
                {"property": "Start Date", "date": {"after": today_iso}}
            ]
        },
        "page_size": 100
    }
    pages = get_pages(LOCATIONS_ID, payload)
    locations = []
    for page in pages:
        props = page.get("properties", {})
        try:
            name = props.get("Name", {}).get("title", [])[0]["text"]["content"]
        except:
            name = "Sin nombre"
        # Opcional: extraer Start Date string
        try:
            sd = props.get("Start Date", {}).get("date", {}).get("start")
        except:
            sd = None
        # Extraer relación con dispositivos (si hay rollup/relación) -> no asumimos
        locations.append({"id": page["id"], "name": name, "start_date": sd, "raw": page})
    return locations

def get_location_devices(location_page):
    """Dado el JSON de location page (o su id), intenta recoger dispositivos relacionados
       Si la Location tiene una rollup/relación hacia Devices, podemos leerla;
       Para simplicidad, hacemos una query de Devices y filtramos por relación a location id.
    """
    location_id = location_page["id"] if isinstance(location_page, dict) and "id" in location_page else location_page
    # Obtener todos los devices (paginación no implementada, asumimos <100)
    device_pages = get_pages(DEVICES_ID)
    devices = [extract_device_data(p) for p in device_pages]
    linked = [d for d in devices if location_id in d.get("location_ids", [])]
    return linked

# ---------------------------
# Creación y asignación
# ---------------------------
def create_in_house_location(name, start_date):
    url = "https://api.notion.com/v1/pages"
    payload = {
        "parent": {"database_id": LOCATIONS_ID},
        "properties": {
            "Name": {"title": [{"text": {"content": name}}]},
            "Type": {"select": {"name": "In House"}},
            "Start Date": {"date": {"start": start_date.isoformat()}}
        }
    }
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code == 200:
        data = response.json()
        st.success(f"✅ Ubicación '{name}' creada correctamente")
        return data["id"]
    else:
        st.error(f"❌ Error al crear ubicación: {response.text}")
        return None

def assign_devices_client(device_names, client_name, start_date, end_date, available_devices):
    """Crea Location Client nueva y asigna devices (igual que tu implementación)"""
    if not client_name or client_name.strip() == "":
        st.error("⚠️ El nombre del destino no puede estar vacío")
        return False
    # Crear location Client
    url_location = "https://api.notion.com/v1/pages"
    payload_location = {
        "parent": {"database_id": LOCATIONS_ID},
        "properties": {
            "Name": {"title": [{"text": {"content": client_name}}]},
            "Type": {"select": {"name": "Client"}},
            "Start Date": {"date": {"start": start_date.isoformat()}},
            "End Date": {"date": {"start": end_date.isoformat()}}
        }
    }
    with st.spinner(f"Creando destino '{client_name}'..."):
        response_location = requests.post(url_location, json=payload_location, headers=headers)
    if response_location.status_code != 200:
        st.error(f"❌ Error al crear el destino: {response_location.text}")
        return False
    location_data = response_location.json()
    location_id = location_data["id"]
    st.success(f"✅ Destino '{client_name}' creado")

    # Asignar devices (patch)
    success_count = 0
    url_patch = "https://api.notion.com/v1/pages/"
    progress_bar = st.progress(0)
    total = len(device_names)
    for idx, device_name in enumerate(device_names):
        device_id = next((d["id"] for d in available_devices if d["Name"] == device_name), None)
        if not device_id:
            st.warning(f"⚠️ No se encontró el ID para '{device_name}'")
            progress_bar.progress((idx + 1) / total)
            continue

        payload_device = {"properties": {"Location": {"relation": [{"id": location_id}]}}}
        response_device = requests.patch(f"{url_patch}{device_id}", json=payload_device, headers=headers)
        if response_device.status_code == 200:
            success_count += 1
        else:
            st.warning(f"⚠️ Error al asignar '{device_name}': {response_device.text}")
        progress_bar.progress((idx + 1) / total)
    progress_bar.empty()
    if success_count > 0:
        st.success(f"🎉 {success_count} dispositivos asignados a '{client_name}'")
        return True
    else:
        st.error("❌ No se pudo asignar ningún dispositivo")
        return False

def assign_devices_to_existing_client(device_names, location_id, location_name, available_devices):
    """Asigna devices a una location Client existente (patch)"""
    success_count = 0
    url_patch = "https://api.notion.com/v1/pages/"
    progress_bar = st.progress(0)
    total = len(device_names)
    for idx, device_name in enumerate(device_names):
        device_id = next((d["id"] for d in available_devices if d["Name"] == device_name), None)
        if not device_id:
            st.warning(f"⚠️ No se encontró el ID para '{device_name}'")
            progress_bar.progress((idx + 1) / total)
            continue
        payload_device = {"properties": {"Location": {"relation": [{"id": location_id}]}}}
        response_device = requests.patch(f"{url_patch}{device_id}", json=payload_device, headers=headers)
        if response_device.status_code == 200:
            success_count += 1
        else:
            st.warning(f"⚠️ Error al asignar '{device_name}': {response_device.text}")
        progress_bar.progress((idx + 1) / total)
    progress_bar.empty()
    if success_count > 0:
        st.success(f"🎉 {success_count} dispositivos asignados a '{location_name}'")
        return True
    else:
        st.error("❌ No se pudo asignar ningún dispositivo")
        return False

def assign_devices_in_house(device_names, location_id, location_name, start_date, available_devices):
    """Asigna devices a In House (igual que tu implementación)"""
    success_count = 0
    url_patch = "https://api.notion.com/v1/pages/"
    progress_bar = st.progress(0)
    total = len(device_names)
    for idx, device_name in enumerate(device_names):
        device_id = next((d["id"] for d in available_devices if d["Name"] == device_name), None)
        if not device_id:
            st.warning(f"⚠️ No se encontró el ID para '{device_name}'")
            progress_bar.progress((idx + 1) / total)
            continue
        payload_device = {"properties": {"Location": {"relation": [{"id": location_id}]}}}
        response_device = requests.patch(f"{url_patch}{device_id}", json=payload_device, headers=headers)
        if response_device.status_code == 200:
            success_count += 1
        else:
            st.warning(f"⚠️ Error al asignar '{device_name}': {response_device.text}")
        progress_bar.progress((idx + 1) / total)
    progress_bar.empty()
    if success_count > 0:
        st.success(f"🎉 {success_count} dispositivos asignados a '{location_name}'")
        return True
    else:
        st.error("❌ No se pudo asignar ningún dispositivo")
        return False

def reassign_device_to_office(device_id, office_location_id):
    """Asigna la relación Location del device a la Office (sobrescribe relaciones)"""
    url_patch = f"https://api.notion.com/v1/pages/{device_id}"
    payload = {"properties": {"Location": {"relation": [{"id": office_location_id}]}}}
    response = requests.patch(url_patch, json=payload, headers=headers)
    return response.status_code == 200

# ---------------------------
# Estado de sesión
# ---------------------------
if 'selected_devices' not in st.session_state:
    st.session_state.selected_devices = []

if 'search_completed' not in st.session_state:
    st.session_state.search_completed = False

if 'available_devices' not in st.session_state:
    st.session_state.available_devices = []

if 'query_start_date' not in st.session_state:
    st.session_state.query_start_date = date.today()

if 'query_end_date' not in st.session_state:
    st.session_state.query_end_date = date.today()

# ---------------------------
# UI: Selección de fechas (global)
# ---------------------------
col1, col2 = st.columns(2)
with col1:
    start_date = st.date_input("Fecha de inicio", value=date.today(), format="DD/MM/YYYY")
with col2:
    end_date = st.date_input("Fecha de fin", value=date.today(), format="DD/MM/YYYY")

if start_date > end_date:
    st.error("⚠️ La fecha de inicio no puede ser posterior a la fecha de fin")
    st.stop()

# ---------------------------
# Pestañas principales
# ---------------------------
tab1, tab2, tab3 = st.tabs([
    "🔍 Disponibles para Alquilar",
    "🏢 Office → In House",
    "📦 Planificaciones Pendientes"
])

# --- BOTÓN GENERAL DE BUSQUEDA (actualiza devices en sesión) ---
with st.sidebar:
    if st.button("🔍 Consultar Disponibilidad (Actualizar Devices)", type="primary", use_container_width=True):
        with st.spinner("Consultando dispositivos..."):
            pages = get_pages(DEVICES_ID)
            all_devices = [extract_device_data(page) for page in pages]
            # Guardar todos los devices en session_state para reutilizar en los tabs
            st.session_state.all_devices = all_devices
            st.session_state.query_start_date = start_date
            st.session_state.query_end_date = end_date
            st.session_state.search_completed = True
            st.session_state.selected_devices = []
            st.success("✅ Devices actualizados")

# Si no se han cargado devices aún, cargarlos automáticamente
if 'all_devices' not in st.session_state or not st.session_state.get('search_completed', False):
    try:
        pages = get_pages(DEVICES_ID)
        st.session_state.all_devices = [extract_device_data(p) for p in pages]
        st.session_state.search_completed = True
    except Exception as e:
        st.error(f"Error al obtener devices: {e}")
        st.stop()

all_devices = st.session_state.get('all_devices', [])

# ---------------------------
# TAB 1 - Disponibles para Alquilar (excluye Devices sin Location)
# ---------------------------
with tab1:
    st.header("🔍 Disponibles para Alquilar")
    st.write("Se muestran dispositivos disponibles en las fechas indicadas. **Se excluyen dispositivos que no tienen Location asignada nunca.**")
    st.markdown("---")

    # Filtrar por disponibilidad y que tengan al menos una Location previa
    available_devices = [d for d in all_devices if d["Locations_demo_count"] > 0 and check_availability(d, start_date, end_date)]

    if available_devices:
        st.success(f"✅ Hay {len(available_devices)} dispositivos disponibles (con Location previa).")
        # Filtro por Tags
        unique_tags = sorted({d["Tags"] for d in available_devices if d["Tags"] and d["Tags"] != "Sin tag"})
        filter_options = ["Todos"] + unique_tags
        selected_tag = st.selectbox("🔎 Filtrar por etiqueta", options=filter_options, index=0)
        if selected_tag != "Todos":
            available_devices = [d for d in available_devices if d["Tags"] == selected_tag]

        # Mostrar dispositivos con checkbox (guardar por name)
        st.subheader("Selecciona los dispositivos que quieres asignar")
        for device in sorted(available_devices, key=lambda x: x["Name"]):
            device_name = device["Name"]
            cols = st.columns([0.5, 9.5])
            with cols[0]:
                checked = st.checkbox("", key=f"tab1_check_{device_name}", value=(device_name in st.session_state.selected_devices))
                if checked and device_name not in st.session_state.selected_devices:
                    st.session_state.selected_devices.append(device_name)
                elif not checked and device_name in st.session_state.selected_devices:
                    st.session_state.selected_devices.remove(device_name)
            with cols[1]:
                st.markdown(f"<div style='padding:8px 12px; background-color: #e0e0e0; border-radius:6px; margin-top:-6px;'>"
                            f"<strong>{device_name}</strong> — {device.get('Tags','')}</div>", unsafe_allow_html=True)

        # Si hay seleccionados, permitir asignar a Client (crear) o asignar a Client existente (si quieres)
        if st.session_state.selected_devices:
            st.markdown("---")
            st.subheader(f"🎯 Asignar ubicación ({len(st.session_state.selected_devices)} dispositivos)")
            location_type = st.selectbox("Tipo de Ubicación", ["Client", "In House"], index=0)
            selected_list = ", ".join(st.session_state.selected_devices)
            st.info(f"**Seleccionados:** {selected_list}")
            if location_type == "Client":
                st.write("**📋 Nuevo Destino Cliente**")
                client_name = st.text_input("Nombre del Destino", placeholder="Ej: Destino Barcelona 2025", key="tab1_client_name")
                if st.button("Crear y Asignar (Client)", type="primary", key="tab1_create_client"):
                    qs = st.session_state.query_start_date or start_date
                    qe = st.session_state.query_end_date or end_date
                    success = assign_devices_client(st.session_state.selected_devices, client_name, qs, qe, available_devices)
                    if success:
                        st.session_state.selected_devices = []
                        # refrescar devices
                        st.experimental_rerun()
            else:
                st.write("**🏠 Asignar a In House**")
                with st.spinner("Cargando ubicaciones In House..."):
                    in_house_locations = get_in_house_locations()
                if not in_house_locations:
                    st.warning("⚠️ No hay ubicaciones In House disponibles")
                    new_in_house_name = st.text_input("Nombre de la ubicación", placeholder="Ej: Casa Juan", key="tab1_new_in_house")
                    if st.button("Crear y Asignar (In House)", key="tab1_create_inhouse"):
                        if not new_in_house_name or new_in_house_name.strip() == "":
                            st.error("⚠️ El nombre no puede estar vacío")
                        else:
                            today = date.today()
                            location_id = create_in_house_location(new_in_house_name, today)
                            if location_id:
                                success = assign_devices_in_house(st.session_state.selected_devices, location_id, new_in_house_name, today, available_devices)
                                if success:
                                    st.session_state.selected_devices = []
                                    st.experimental_rerun()
                else:
                    location_options = {f"📍 {loc['name']}": loc['id'] for loc in in_house_locations}
                    selected_location_display = st.selectbox("Seleccionar ubicación existente", options=list(location_options.keys()), key="tab1_inhouse_select")
                    selected_location_id = location_options[selected_location_display]
                    selected_location_name = selected_location_display.replace("📍 ", "")
                    if st.button("Asignar (In House)", type="primary", key="tab1_assign_inhouse"):
                        today = date.today()
                        success = assign_devices_in_house(st.session_state.selected_devices, selected_location_id, selected_location_name, today, available_devices)
                        if success:
                            st.session_state.selected_devices = []
                            st.experimental_rerun()
    else:
        st.warning("⚠️ No hay dispositivos disponibles en estas fechas (o no tienen Location asignada)")

# ---------------------------
# TAB 2 - Devices en Office → mover a In House
# ---------------------------
with tab2:
    st.header("🏢 Office → In House")
    st.write("Se muestran dispositivos que actualmente están asignados a la Location con Name = 'Office'. Puedes moverlos a una ubicación In House.")
    st.markdown("---")

    # Primero conseguir la office location
    office = get_office_location_by_name("Office")
    if not office:
        st.error("❌ No se encontró la Location con Name = 'Office'. Crearla en Notion antes de usar este flujo.")
    else:
        office_id = office["id"]
        # Obtener todos los devices y filtrar los que tienen office_id en sus location_ids
        office_devices = [d for d in all_devices if office_id in d.get("location_ids", [])]
        if not office_devices:
            st.info("ℹ️ No hay dispositivos actualmente en Office.")
        else:
            st.success(f"✅ {len(office_devices)} dispositivos en Office.")
            # Mostrar con checkboxes para selección
            st.subheader("Selecciona dispositivos para mover a In House")
            for device in sorted(office_devices, key=lambda x: x["Name"]):
                name = device["Name"]
                cols = st.columns([0.5, 9.5])
                with cols[0]:
                    checked = st.checkbox("", key=f"tab2_check_{name}", value=(name in st.session_state.selected_devices))
                    if checked and name not in st.session_state.selected_devices:
                        st.session_state.selected_devices.append(name)
                    elif not checked and name in st.session_state.selected_devices:
                        st.session_state.selected_devices.remove(name)
                with cols[1]:
                    st.markdown(f"<div style='padding:8px 12px; background-color:#e0e0e0; border-radius:6px; margin-top:-6px;'>"
                                f"<strong>{name}</strong> — {device.get('Tags','')}</div>", unsafe_allow_html=True)
            # Si hay seleccionados, indicar In House destino
            if st.session_state.selected_devices:
                st.markdown("---")
                st.subheader("Elegir In House destino")
                in_house_locations = get_in_house_locations()
                if not in_house_locations:
                    st.warning("⚠️ No hay In House creadas. Crea una nueva.")
                    new_name = st.text_input("Nombre de la nueva In House", key="tab2_new_inhouse")
                    if st.button("Crear y mover", key="tab2_create_move"):
                        if not new_name or new_name.strip() == "":
                            st.error("⚠️ El nombre no puede estar vacío")
                        else:
                            today = date.today()
                            loc_id = create_in_house_location(new_name, today)
                            if loc_id:
                                success = assign_devices_in_house(st.session_state.selected_devices, loc_id, new_name, today, office_devices)
                                if success:
                                    st.session_state.selected_devices = []
                                    st.experimental_rerun()
                else:
                    options = {f"📍 {loc['name']}": loc['id'] for loc in in_house_locations}
                    selected_display = st.selectbox("Seleccionar ubicación In House", options=list(options.keys()), key="tab2_inhouse_select")
                    selected_id = options[selected_display]
                    selected_name = selected_display.replace("📍 ", "")
                    if st.button("Mover a In House", key="tab2_move_button"):
                        success = assign_devices_in_house(st.session_state.selected_devices, selected_id, selected_name, date.today(), office_devices)
                        if success:
                            st.session_state.selected_devices = []
                            st.experimental_rerun()

# ---------------------------
# TAB 3 - Planificaciones Pendientes (Start Date futura)
# ---------------------------
with tab3:
    st.header("📦 Planificaciones Pendientes")
    st.write("Locations de tipo Client con Start Date en el futuro. Puedes elegir una, ver sus dispositivos, añadir o quitar dispositivos.")
    st.markdown("---")

    client_locations = get_client_locations_future_start()
    if not client_locations:
        st.info("ℹ️ No hay Locations Client con Start Date futura.")
    else:
        # Mostrar dropdown de locations futuras
        display_map = {f"📅 {loc['start_date'] or '—'} — {loc['name']}": loc for loc in client_locations}
        selected_display = st.selectbox("Seleccionar Location pendiente", options=list(display_map.keys()))
        selected_loc = display_map[selected_display]
        st.markdown(f"### {selected_loc['name']} — Start: {selected_loc.get('start_date')}")
        # Obtener dispositivos actualmente asignados a esa location
        assigned_devices = get_location_devices(selected_loc)
        if assigned_devices:
            st.subheader("Dispositivos asignados actualmente")
            for d in sorted(assigned_devices, key=lambda x: x["Name"]):
                cols = st.columns([0.5, 6, 3])
                with cols[0]:
                    # Checkbox para seleccionar para eliminación
                    rem = st.checkbox("", key=f"tab3_rem_{d['id']}", value=False)
                with cols[1]:
                    st.markdown(f"**{d['Name']}** — {d.get('Tags','')}", unsafe_allow_html=True)
                with cols[2]:
                    # Botón para quitar individualmente
                    if st.button(f"Quitar {d['Name']}", key=f"tab3_btn_rem_{d['id']}"):
                        # Reasignar a Office
                        office = get_office_location_by_name("Office")
                        if not office:
                            st.error("❌ No existe la Location 'Office' para reasignar.")
                        else:
                            ok = reassign_device_to_office(d["id"], office["id"])
                            if ok:
                                st.success(f"✅ {d['Name']} reasignado a Office")
                                st.experimental_rerun()
                            else:
                                st.error("❌ Error al reasignar dispositivo")
        else:
            st.info("ℹ️ No hay dispositivos asignados a esta Location todavía.")

        st.markdown("---")
        # Si se seleccionaron checkboxes (o usamos botones), también permitimos quitar en lote
        # Recolectar seleccionados marcados para quitar
        to_remove = []
        for d in assigned_devices:
            key = f"tab3_rem_{d['id']}"
            if st.session_state.get(key):
                to_remove.append(d)
        if to_remove:
            if st.button(f"Quitar {len(to_remove)} seleccionados y reasignar a Office", key="tab3_bulk_remove"):
                office = get_office_location_by_name("Office")
                if not office:
                    st.error("❌ No existe la Location 'Office' para reasignar.")
                else:
                    success_count = 0
                    for d in to_remove:
                        if reassign_device_to_office(d["id"], office["id"]):
                            success_count += 1
                    st.success(f"✅ {success_count} dispositivos reasignados a Office")
                    st.experimental_rerun()

        st.markdown("---")
        # Añadir dispositivos a esta Location: mostramos disponibles según fechas de la location
        st.subheader("➕ Añadir dispositivos a esta Location")
        # Tomamos las fechas del Start Date y End Date de la Location seleccionada (si las tiene)
        # Extraer rollup/props desde raw (guardamos raw page en selected_loc['raw'])
        raw = selected_loc.get("raw", {})
        props = raw.get("properties", {})
        try:
            loc_start = props.get("Start Date", {}).get("date", {}).get("start")
            loc_end = props.get("End Date", {}).get("date", {}).get("start")
            loc_start_date = datetime.fromisoformat(loc_start).date() if loc_start else None
            loc_end_date = datetime.fromisoformat(loc_end).date() if loc_end else None
        except:
            loc_start_date = None
            loc_end_date = None

        if not loc_start_date or not loc_end_date:
            st.warning("⚠️ Esta Location no tiene Start Date o End Date definidos correctamente. No se puede buscar disponibilidad.")
        else:
            # Filtrar dispositivos disponibles en ese rango (y que tengan Location previa > 0)
            possible_devices = [d for d in all_devices if d["Locations_demo_count"] > 0 and check_availability(d, loc_start_date, loc_end_date)]
            if not possible_devices:
                st.info("ℹ️ No hay dispositivos disponibles para esas fechas.")
            else:
                st.info(f"📦 {len(possible_devices)} dispositivos disponibles para añadir")
                # Mostrar con checkboxes para seleccionar
                for d in sorted(possible_devices, key=lambda x: x["Name"]):
                    name = d["Name"]
                    cols = st.columns([0.5, 9.5])
                    with cols[0]:
                        chk = st.checkbox("", key=f"tab3_add_{d['id']}", value=False)
                    with cols[1]:
                        st.markdown(f"<div style='padding:8px 12px; background:#e0e0e0; border-radius:6px; margin-top:-6px;'>"
                                    f"<strong>{name}</strong> — {d.get('Tags','')}</div>", unsafe_allow_html=True)

                # Recoger seleccionados
                to_add = []
                for d in possible_devices:
                    key = f"tab3_add_{d['id']}"
                    if st.session_state.get(key):
                        to_add.append(d["Name"])

                if to_add:
                    st.markdown("---")
                    st.info(f"Seleccionados para añadir: {', '.join(to_add)}")
                    # Opción: añadir a esta Location existente (selected_loc['id'])
                    if st.button("Añadir seleccionados a esta Location", key="tab3_add_btn"):
                        success = assign_devices_to_existing_client(to_add, selected_loc["id"], selected_loc["name"], possible_devices)
                        if success:
                            st.success("✅ Dispositivos añadidos a la Location")
                            st.experimental_rerun()

# Fin del script
