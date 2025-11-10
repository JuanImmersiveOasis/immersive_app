import streamlit as st
import requests
from datetime import datetime, date
import os
from dotenv import load_dotenv
load_dotenv()

# ---------------- CONFIG ----------------
st.set_page_config(page_title="Logistica", page_icon=None, layout="wide")

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


def iso_to_date(s):
    """Convierte una fecha ISO a objeto date"""
    try:
        return datetime.fromisoformat(s).date()
    except:
        return None


def available(dev, start, end):
    """Verifica si un dispositivo está disponible en un rango de fechas"""
    ds = iso_to_date(dev.get("Start"))
    de = iso_to_date(dev.get("End"))
    if not ds and not de:
        return True
    if ds and de:
        return not (start <= de and end >= ds)
    if ds and not de:
        return end < ds
    if de and not ds:
        return start > de
    return True


def assign_device(dev_id, loc_id):
    """Asigna un dispositivo a una ubicación en Notion"""
    requests.patch(f"https://api.notion.com/v1/pages/{dev_id}", json={
        "properties": {"Location": {"relation": [{"id": loc_id}]}}
    }, headers=headers)


# ---------------- CACHED LOADERS ----------------
@st.cache_data(show_spinner=False)
def load_devices():
    """Carga todos los dispositivos desde Notion"""
    results = q(DEVICES_ID)
    out = []
    for p in results:
        props = p["properties"]
        name = props["Name"]["title"][0]["text"]["content"] if props["Name"]["title"] else "Sin nombre"
        locs = [r["id"] for r in props["Location"]["relation"]]
        tag = props["Tags"]["select"]["name"] if props["Tags"]["select"] else None

        def roll(field):
            """Extrae fechas de campos rollup"""
            try:
                rr = props[field]["rollup"]
                if rr.get("array"):
                    return rr["array"][0]["date"]["start"]
                if rr.get("date"):
                    return rr["date"]["start"]
            except:
                return None
            return None

        out.append({
            "id": p["id"],
            "Name": name,
            "Tags": tag,
            "location_ids": locs,
            "Start": roll("Start Date"),
            "End": roll("End Date")
        })

    return sorted(out, key=lambda x: x["Name"])


@st.cache_data(show_spinner=False)
def load_future_client_locations():
    """Carga ubicaciones de tipo Client futuras"""
    today = date.today()
    results = q(LOCATIONS_ID)
    out = []
    for p in results:
        props = p["properties"]
        t = props["Type"]["select"]["name"]
        if t != "Client":
            continue
        sd = props["Start Date"]["date"]["start"] if props["Start Date"]["date"] else None
        if not sd or iso_to_date(sd) < today:
            continue
        name = props["Name"]["title"][0]["text"]["content"]
        ed = props["End Date"]["date"]["start"] if props["End Date"]["date"] else None
        out.append({"id": p["id"], "name": name, "start": sd, "end": ed})
    return out


@st.cache_data(show_spinner=False)
def load_inhouse():
    """Carga ubicaciones de tipo In House"""
    r = q(LOCATIONS_ID, {"filter": {"property": "Type", "select": {"equals": "In House"}}})
    return [{"id": p["id"], "name": p["properties"]["Name"]["title"][0]["text"]["content"]} for p in r]


def office_id():
    """Obtiene el ID de la ubicación Office"""
    r = q(LOCATIONS_ID, {"filter": {"property": "Name", "title": {"equals": "Office"}}})
    return r[0]["id"] if r else None


def clear_all_cache():
    """Limpia toda la caché de datos"""
    load_devices.clear()
    load_inhouse.clear()
    load_future_client_locations.clear()


# ---------------- UI HELP ----------------
def card(name, selected=False):
    """Muestra una tarjeta de dispositivo con estilo visual"""
    bg = "#B3E5E6" if selected else "#e0e0e0"
    border = "#00859B" if selected else "#9e9e9e"
    st.markdown(
        f"<div style='padding:7px;background:{bg};border-left:4px solid {border};border-radius:6px;margin-bottom:4px;'><b>{name}</b></div>",
        unsafe_allow_html=True
    )


def counter_badge(selected, total):
    """
    Muestra un contador de elementos seleccionados con fondo verde si hay selección.
    - Si selected > 0: fondo verde
    - Si selected = 0: fondo gris
    """
    if selected > 0:
        bg_color = "#B3E5E6"  # Turquesa
        text_color = "666"
    else:
        bg_color = "#e0e0e0"  # Gris claro
        text_color = "#666"
    
    # Crear el HTML del badge con estilos
    st.markdown(
        f"""
        <div style='
            background: {bg_color};
            color: {text_color};
            padding: 12px 16px;
            border-radius: 8px;
            text-align: center;
            font-size: 18px;
            font-weight: bold;
            margin-bottom: 15px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        '>
            {selected} / {total} seleccionadas
        </div>
        """,
        unsafe_allow_html=True
    )


# ---------------- STATE ----------------
if "tab1_show" not in st.session_state:
    st.session_state.tab1_show = False
if "sel1" not in st.session_state:
    st.session_state.sel1 = []
if "sel2" not in st.session_state:
    st.session_state.sel2 = []
if "sel3" not in st.session_state:
    st.session_state.sel3 = []
if "tab3_loc" not in st.session_state:
    st.session_state.tab3_loc = None
if "show_avail_tab3" not in st.session_state:
    st.session_state.show_avail_tab3 = False


# ---------------- SIDEBAR NAV ----------------
with st.sidebar:
    menu = st.radio("Navegación", ["Disponibles para Alquilar", "Gafas para Equipo", "Próximos Envíos"])
    st.markdown("----")


# ---------------- TAB 1: Disponibles para Alquilar ----------------
if menu == "Disponibles para Alquilar":
    st.title("Disponibles para Alquilar")
    
    # Selector de fechas
    d1, d2 = st.columns(2)
    with d1:
        start = st.date_input("Fecha inicio", date.today())
    with d2:
        end = st.date_input("Fecha fin", date.today())

    # Botón de búsqueda
    if st.button("Comprobar disponibilidad"):
        st.session_state.tab1_show = True
        st.session_state.sel1 = []

    # Mostrar resultados si se ha hecho la búsqueda
    if st.session_state.tab1_show:
        devices = load_devices()
        avail = [d for d in devices if available(d, start, end)]

        # Mostrar dispositivos disponibles con checkboxes
        for d in avail:
            key = f"a_{d['id']}"
            cols = st.columns([0.5, 9.5])
            with cols[0]:
                st.checkbox("", key=key)
            with cols[1]:
                card(d["Name"], st.session_state.get(key, False))

        # Actualizar lista de seleccionados
        st.session_state.sel1 = [d["id"] for d in avail if st.session_state.get(f"a_{d['id']}", False)]
        sel_count = len(st.session_state.sel1)

        # Sidebar con contador y opciones
        with st.sidebar:
            # MEJORA 1: Usar el nuevo contador con fondo verde
            counter_badge(sel_count, len(avail))

            # Si hay dispositivos seleccionados, mostrar formulario
            if sel_count > 0:
                client = st.text_input("Nombre Cliente")
                
                if st.button("Asignar Cliente"):
                    # MEJORA 2: Mostrar barra de progreso
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    # Paso 1: Crear la ubicación Cliente
                    status_text.text("📝 Creando ubicación de cliente...")
                    new = requests.post("https://api.notion.com/v1/pages", headers=headers, json={
                        "parent": {"database_id": LOCATIONS_ID},
                        "properties": {
                            "Name": {"title": [{"text": {"content": client}}]},
                            "Type": {"select": {"name": "Client"}},
                            "Start Date": {"date": {"start": start.isoformat()}},
                            "End Date": {"date": {"start": end.isoformat()}}
                        }
                    }).json()["id"]
                    
                    progress_bar.progress(0.2)
                    
                    # Paso 2: Asignar cada dispositivo
                    total_devices = len(st.session_state.sel1)
                    for idx, did in enumerate(st.session_state.sel1):
                        # Encontrar el nombre del dispositivo para mostrarlo
                        device_name = next((d["Name"] for d in avail if d["id"] == did), "Dispositivo")
                        status_text.text(f"⚙️ Asignando {idx + 1}/{total_devices}: {device_name}")
                        
                        assign_device(did, new)
                        
                        # Actualizar barra de progreso (de 0.2 a 1.0)
                        progress = 0.2 + (0.8 * (idx + 1) / total_devices)
                        progress_bar.progress(progress)
                    
                    # Paso 3: Finalizado
                    progress_bar.progress(1.0)
                    status_text.empty()
                    st.success(f"✅ ¡Proceso completado! {total_devices} gafas asignadas a '{client}'")
                    
                    # Limpiar caché y reiniciar
                    clear_all_cache()
                    st.rerun()


# ---------------- TAB 2: Gafas para Equipo ----------------
elif menu == "Gafas para Equipo":
    st.title("Gafas para Equipo")
    
    # Cargar dispositivos y filtrar los que están en Office
    devices = load_devices()
    oid = office_id()
    office_devices = [d for d in devices if oid in d["location_ids"]]

    # Mostrar dispositivos de Office con checkboxes
    for d in office_devices:
        key = f"o_{d['id']}"
        cols = st.columns([0.5, 9.5])
        with cols[0]:
            st.checkbox("", key=key)
        with cols[1]:
            card(d["Name"], st.session_state.get(key, False))

    # Actualizar lista de seleccionados
    st.session_state.sel2 = [d["id"] for d in office_devices if st.session_state.get(f"o_{d['id']}", False)]
    sel_count = len(st.session_state.sel2)

    # Sidebar con contador y opciones
    with st.sidebar:
        # MEJORA 1: Usar el nuevo contador con fondo verde
        counter_badge(sel_count, len(office_devices))
        
        # Si hay dispositivos seleccionados, mostrar opciones
        if sel_count > 0:
            inh = load_inhouse()
            dest = st.selectbox("Asignar a:", [x["name"] for x in inh])
            dest_id = next(x["id"] for x in inh if x["name"] == dest)
            
            if st.button("Asignar seleccionadas"):
                # MEJORA 2: Mostrar barra de progreso
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                total_devices = len(st.session_state.sel2)
                
                # Asignar cada dispositivo
                for idx, did in enumerate(st.session_state.sel2):
                    # Encontrar el nombre del dispositivo
                    device_name = next((d["Name"] for d in office_devices if d["id"] == did), "Dispositivo")
                    status_text.text(f"📦 Moviendo {idx + 1}/{total_devices}: {device_name}")
                    
                    assign_device(did, dest_id)
                    
                    # Actualizar progreso
                    progress = (idx + 1) / total_devices
                    progress_bar.progress(progress)
                
                # Finalizado
                progress_bar.progress(1.0)
                status_text.empty()
                st.success(f"✅ ¡Proceso completado! {total_devices} dispositivos movidos a '{dest}'")
                
                # Limpiar caché y reiniciar
                clear_all_cache()
                st.rerun()


# ---------------- TAB 3: Próximos Envíos ----------------
else:
    st.title("Próximos Envíos")

    # Cargar ubicaciones futuras de clientes
    locs = load_future_client_locations()
    options = ["Seleccionar..."] + [x["name"] for x in locs]
    sel = st.selectbox("Selecciona envío:", options)

    if sel != "Seleccionar...":
        loc = next(x for x in locs if x["name"] == sel)
        st.session_state.tab3_loc = loc["id"]

        st.write(f"📅 Inicio: **{loc['start']}** — Fin: **{loc['end']}**")
        st.markdown("---")

        devices = load_devices()
        assigned = [d for d in devices if loc["id"] in d["location_ids"]]

        # Expander con dispositivos ya asignados
        with st.expander(f"📦 Gafas reservadas ({len(assigned)})", expanded=False):
            for d in assigned:
                cols = st.columns([9, 1])
                with cols[0]:
                    card(d["Name"])
                with cols[1]:
                    if st.button("✕", key=f"rm_{d['id']}"):
                        assign_device(d["id"], office_id())
                        clear_all_cache()
                        st.rerun()

        # Botón para buscar disponibles
        if st.button(" Mostrar otras disponibles"):
            st.session_state.show_avail_tab3 = True
            st.rerun()

        # Mostrar dispositivos disponibles para añadir
        if st.session_state.show_avail_tab3:
            ls = iso_to_date(loc["start"])
            le = iso_to_date(loc["end"])
            can_add = [d for d in devices if available(d, ls, le) and loc["id"] not in d["location_ids"]]

            # Mostrar dispositivos disponibles con checkboxes
            for d in can_add:
                key = f"add_{d['id']}"
                cols = st.columns([0.5, 9.5])
                with cols[0]:
                    st.checkbox("", key=key)
                with cols[1]:
                    card(d["Name"], st.session_state.get(key, False))

            # Actualizar lista de seleccionados
            st.session_state.sel3 = [d["id"] for d in can_add if st.session_state.get(f"add_{d['id']}", False)]

            # Sidebar con contador y opciones
            with st.sidebar:
                # MEJORA 1: Usar el nuevo contador con fondo verde
                counter_badge(len(st.session_state.sel3), len(can_add))
                
                # Si hay dispositivos seleccionados, mostrar botón
                if len(st.session_state.sel3) > 0:
                    if st.button("Añadir seleccionadas"):
                        # MEJORA 2: Mostrar barra de progreso
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        total_devices = len(st.session_state.sel3)
                        
                        # Asignar cada dispositivo
                        for idx, did in enumerate(st.session_state.sel3):
                            # Encontrar el nombre del dispositivo
                            device_name = next((d["Name"] for d in can_add if d["id"] == did), "Dispositivo")
                            status_text.text(f"➕ Añadiendo {idx + 1}/{total_devices}: {device_name}")
                            
                            assign_device(did, loc["id"])
                            
                            # Actualizar progreso
                            progress = (idx + 1) / total_devices
                            progress_bar.progress(progress)
                        
                        # Finalizado
                        progress_bar.progress(1.0)
                        status_text.empty()
                        st.success(f"✅ ¡Proceso completado! {total_devices} dispositivos añadidos a '{sel}'")
                        
                        # Limpiar caché y reiniciar
                        clear_all_cache()
                        st.rerun()


# ---------------- GLOBAL FIXED REFRESH BUTTON ----------------
# Estilos CSS para posicionar los botones en la esquina inferior izquierda
st.markdown(
    """
    <style>
    .fixed-buttons {
        position: fixed;
        bottom: 12px;
        left: 12px;
        display: flex;
        gap: 8px;
        z-index: 999;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# Crear dos columnas para los botones
col_btn1, col_btn2 = st.columns([1, 1])

with col_btn1:
    # Botón para refrescar la página
    if st.button("🔄 Refrescar", key="refresh_page", help="Recarga la página completa"):
        st.rerun()

with col_btn2:
    # Botón para limpiar caché y recargar datos de Notion
    if st.button("🗑️ Limpiar Caché", key="clear_cache", help="Borra datos guardados y recarga desde Notion"):
        clear_all_cache()
        st.success("✅ Caché limpiado - Recargando datos de Notion...")
        st.rerun()