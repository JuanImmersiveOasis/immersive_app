# app.py - Logística Inmersive Oasis (versión con contador y mejoras)
import streamlit as st
import requests
from datetime import datetime, date
import os
from dotenv import load_dotenv
load_dotenv()

# ---------------- CONFIG ----------------
st.set_page_config(page_title="Logistica", page_icon=None, layout="wide")

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
    if payload is None:
        payload = {"page_size": 200}
    resp = requests.post(f"https://api.notion.com/v1/databases/{db}/query", json=payload, headers=headers)
    try:
        return resp.json().get("results", [])
    except:
        return []

def patch(page_id, data):
    try:
        return requests.patch(f"https://api.notion.com/v1/pages/{page_id}", json=data, headers=headers)
    except Exception as e:
        st.error(f"Error patch: {e}")
        return None

def create_page(data):
    try:
        return requests.post("https://api.notion.com/v1/pages", json=data, headers=headers)
    except Exception as e:
        st.error(f"Error create page: {e}")
        return None


def parse_device(p):
    props = p.get("properties", {})
    # Name
    try:
        name = props["Name"]["title"][0]["text"]["content"]
    except:
        name = "Sin nombre"
    # Locations relation ids
    try:
        locs = [r["id"] for r in props.get("Location", {}).get("relation", [])]
    except:
        locs = []
    # Tags
    try:
        tag = props.get("Tags", {}).get("select", {}).get("name")
    except:
        tag = None

    def roll(field):
        try:
            rr = props[field]["rollup"]
            if rr.get("array"):
                return rr["array"][0]["date"]["start"]
            if rr.get("date"):
                return rr["date"]["start"]
        except:
            return None
        return None

    return {
        "id": p.get("id"),
        "Name": name,
        "Tags": tag,
        "location_ids": locs,
        "Start": roll("Start Date"),
        "End": roll("End Date")
    }

def load_devices():
    pages = q(DEVICES_ID)
    return sorted([parse_device(p) for p in pages], key=lambda x: (x.get("Name") or "").lower())

def iso_to_date(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s).date()
    except:
        return None

def available(dev, start, end):
    ds = iso_to_date(dev.get("Start"))
    de = iso_to_date(dev.get("End"))
    # If no rollup dates, consider available
    if not ds and not de:
        return True
    if ds and de:
        # overlap -> not available
        if (start <= de and end >= ds):
            return False
        return True
    if ds and not de:
        if end >= ds:
            return False
        return True
    if de and not ds:
        if start <= de:
            return False
        return True
    return True

# Locations helpers
def get_office_id():
    res = q(LOCATIONS_ID, {"filter": {"property": "Name", "title": {"equals": "Office"}}})
    if not res:
        return None
    return res[0].get("id")

def get_in_house_list():
    res = q(LOCATIONS_ID, {"filter": {"property": "Type", "select": {"equals": "In House"}}})
    out = []
    for p in res:
        try:
            nm = p["properties"]["Name"]["title"][0]["text"]["content"]
        except:
            nm = "Sin nombre"
        out.append({"id": p["id"], "name": nm})
    return out

def get_client_future_locations():
    today_iso = date.today().isoformat()
    res = q(LOCATIONS_ID, {
        "filter": {
            "and": [
                {"property": "Type", "select": {"equals": "Client"}},
                {"property": "Start Date", "date": {"after": today_iso}}
            ]
        },
        "page_size": 200
    })
    out = []
    for p in res:
        try:
            nm = p["properties"]["Name"]["title"][0]["text"]["content"]
        except:
            nm = "Sin nombre"
        sd = None
        ed = None
        try:
            sd = p["properties"]["Start Date"]["date"]["start"]
        except:
            sd = None
        try:
            ed = p["properties"]["End Date"]["date"]["start"]
        except:
            ed = None
        out.append({"id": p["id"], "name": nm, "start": sd, "end": ed})
    return out

def assign_device_to_location(device_id, location_id):
    payload = {"properties": {"Location": {"relation": [{"id": location_id}]}}}
    return patch(device_id, payload)

# ---------------- STATE ----------------
# selections per tab
if "sel_tab1" not in st.session_state:
    st.session_state.sel_tab1 = []   # names
if "sel_tab2" not in st.session_state:
    st.session_state.sel_tab2 = []   # ids
if "sel_tab3_add" not in st.session_state:
    st.session_state.sel_tab3_add = []  # ids to add
# global devices cache
if "devices" not in st.session_state:
    st.session_state.devices = load_devices()
# for tab1: show results only after button
if "tab1_shown" not in st.session_state:
    st.session_state.tab1_shown = False
# last selected envio id to detect change
if "last_envio_id" not in st.session_state:
    st.session_state.last_envio_id = None

# ---------------- SIDEBAR NAV & controls ----------------
with st.sidebar:
    menu = st.radio("Navegación", ["Disponibles para Alquilar", "Gafas para Equipo", "Próximos Envíos"])
    st.markdown("---")
    # Placeholders for counters and actions will be rendered conditionally below per tab

# When change tab: clear selections and ensure devices refreshed
if "last_menu" not in st.session_state:
    st.session_state.last_menu = menu

if menu != st.session_state.last_menu:
    st.session_state.sel_tab1 = []
    st.session_state.sel_tab2 = []
    st.session_state.sel_tab3_add = []
    st.session_state.tab1_shown = False
    # refresh devices each tab change (as requested)
    st.session_state.devices = load_devices()
    st.session_state.last_envio_id = None
    st.session_state.last_menu = menu
    st.rerun()

devices = st.session_state.devices  # current cache

# ---------------- UI helpers (cards + pill) ----------------
def device_card(name, selected=False, show_close=False, close_key=None):
    """Renders a card/pill. If show_close True, caller should render a separate small button alongside."""
    bg = "#B3E5E6" if selected else "#e0e0e0"
    border = "#00859B" if selected else "#9e9e9e"
    return f"<div style='padding:8px 12px; background:{bg}; border-left:4px solid {border}; border-radius:6px; display:flex; align-items:center; justify-content:space-between;'> <span style=\"font-weight:600\">{name}</span></div>"

def render_card_row(name, device_id, checkbox_key, selected):
    cols = st.columns([0.5, 9.0, 0.5])
    with cols[0]:
        checked = st.checkbox("", key=checkbox_key)
    with cols[1]:
        st.markdown(device_card(name, selected=checked), unsafe_allow_html=True)
    return checked

# ---------------- TAB 1 ----------------
if menu == "Disponibles para Alquilar":
    st.title("Disponibles para Alquilar")
    col1, col2 = st.columns(2)
    with col1:
        start = st.date_input("Fecha inicio", date.today())
    with col2:
        end = st.date_input("Fecha fin", date.today())

    # Comprobar disponibilidad button (only here)
    if st.button("Comprobar disponibilidad"):
        st.session_state.tab1_shown = True
        st.session_state.devices = load_devices()
        st.session_state.sel_tab1 = []
        st.rerun()

    # Only show results after pressing button
    if st.session_state.tab1_shown:
        # compute available
        avail = [d for d in devices if available(d, start, end)]
        # filter by Tags
        types = sorted({t for t in (d.get("Tags") for d in avail) if t})
        types_opts = ["Todos"] + types
        ftype = st.selectbox("Filtrar por tipo", options=types_opts)
        if ftype != "Todos":
            avail = [d for d in avail if d.get("Tags") == ftype]

        # LEFT: sidebar counter + assign form
        with st.sidebar:
            # counter: selected / total
            total = len(avail)
            selected_count = len(st.session_state.sel_tab1)
            st.markdown(f"### {selected_count} / {total}")
            st.markdown("---")
            # show assign form only if there are selections
            if st.session_state.sel_tab1:
                st.markdown("#### Asignar a Cliente")
                client_name = st.text_input("Nombre Cliente", key="client_name_sidebar")
                if st.button("Asignar Cliente"):
                    if not client_name or client_name.strip() == "":
                        st.error("El nombre del cliente no puede estar vacío")
                    else:
                        # create client location
                        payload = {
                            "parent": {"database_id": LOCATIONS_ID},
                            "properties": {
                                "Name": {"title": [{"text": {"content": client_name.strip()}}]},
                                "Type": {"select": {"name": "Client"}},
                                "Start Date": {"date": {"start": start.isoformat()}},
                                "End Date": {"date": {"start": end.isoformat()}}
                            }
                        }
                        resp = create_page(payload)
                        if resp is None or resp.status_code not in (200, 201):
                            st.error("Error creando Location Client")
                        else:
                            loc_id = resp.json().get("id")
                            # assign each selected device name to this loc
                            name_to_id = {x["Name"]: x["id"] for x in devices}
                            assigned = 0
                            for nm in list(st.session_state.sel_tab1):
                                did = name_to_id.get(nm)
                                if did:
                                    ok = assign_device_to_location(did, loc_id)
                                    if ok is not None:
                                        assigned += 1
                            st.success(f"✅ {assigned} dispositivos asignados a {client_name.strip()}")
                            st.session_state.sel_tab1 = []
                            st.session_state.devices = load_devices()
                            st.rerun()

        # Show total available as green pill above list (in main area)
        st.markdown("", unsafe_allow_html=True)
        st.markdown(f"<div style='padding:6px;background:#C6F6C6;border-radius:6px;display:inline-block;font-weight:bold;'> {len(avail)} disponibles </div>", unsafe_allow_html=True)
        st.markdown("")

        # list devices: show only name, checkbox, card colored when selected
        for d in avail:
            chk_key = f"tab1_{d['id']}"
            # ensure checkbox initial state consistent with st.session_state.sel_tab1
            if chk_key not in st.session_state:
                st.session_state[chk_key] = False
            cols = st.columns([0.5, 9.5])
            with cols[0]:
                checked = st.checkbox("", key=chk_key)
            with cols[1]:
                # If checked, card should be colored; use checked variable
                st.markdown(device_card(d["Name"], selected=checked), unsafe_allow_html=True)
            # keep sel_tab1 synced with checkboxes (store names)
            if checked and d["Name"] not in st.session_state.sel_tab1:
                st.session_state.sel_tab1.append(d["Name"])
            if not checked and d["Name"] in st.session_state.sel_tab1:
                st.session_state.sel_tab1.remove(d["Name"])

# ---------------- TAB 2 ----------------
elif menu == "Gafas para Equipo":
    st.title("Gafas para Equipo")
    oid = get_office_id()
    if not oid:
        st.error("No existe Location con Name = 'Office'. Crea la Location Office en Notion.")
    else:
        office_devices = [d for d in devices if oid in d.get("location_ids", [])]
        # Filter by type
        types = sorted({t for t in (x.get("Tags") for x in office_devices) if t})
        types_opts = ["Todos"] + types
        ftype = st.selectbox("Filtrar por tipo", options=types_opts)
        if ftype != "Todos":
            office_devices = [d for d in office_devices if d.get("Tags") == ftype]

        # Sidebar: counter and mover controls (only if any selected)
        with st.sidebar:
            total_office = len(office_devices)
            selected_count2 = len(st.session_state.sel_tab2)
            st.markdown(f"### {selected_count2} / {total_office}")
            st.markdown("---")
            # Only show selector and move button if there are selections
            if st.session_state.sel_tab2:
                st.markdown("#### Mover a In House")
                inhouses = get_in_house_list()
                if not inhouses:
                    st.info("No hay In House definidas en Notion.")
                else:
                    dest_names = [x["name"] for x in inhouses]
                    dest_choice = st.selectbox("Destino:", dest_names, key="sidebar_inhouse_select")
                    if st.button("Mover seleccionadas"):
                        dest_id = next(x["id"] for x in inhouses if x["name"] == dest_choice)
                        moved = 0
                        for did in list(st.session_state.sel_tab2):
                            res = assign_device_to_location(did, dest_id)
                            if res is not None:
                                moved += 1
                        st.success(f"✅ {moved} dispositivos movidos a {dest_choice}")
                        st.session_state.sel_tab2 = []
                        st.session_state.devices = load_devices()
                        st.rerun()

        # Main area: list office devices with checkboxes; cards should be gray by default and colored only when checkbox checked
        st.markdown(f"<div style='padding:6px;background:#C6F6C6;border-radius:6px;display:inline-block;font-weight:bold;'> {len(office_devices)} en Office </div>", unsafe_allow_html=True)
        st.markdown("")
        for d in office_devices:
            chk_key = f"tab2_{d['id']}"
            if chk_key not in st.session_state:
                st.session_state[chk_key] = False
            cols = st.columns([0.5, 9.5])
            with cols[0]:
                c = st.checkbox("", key=chk_key)
            with cols[1]:
                st.markdown(device_card(d["Name"], selected=c), unsafe_allow_html=True)
            # maintain sel_tab2 as list of ids
            if c and d["id"] not in st.session_state.sel_tab2:
                st.session_state.sel_tab2.append(d["id"])
            if not c and d["id"] in st.session_state.sel_tab2:
                st.session_state.sel_tab2.remove(d["id"])

# ---------------- TAB 3 ----------------
else:
    st.title("Próximos Envíos")
    locs = get_client_future_locations()
    if not locs:
        st.info("No hay envíos futuros")
    else:
        loc_names = [x["name"] for x in locs]
        sel = st.selectbox("Selecciona envío:", loc_names)
        # find selected loc safely
        loc = next((x for x in locs if x["name"] == sel), None)
        if not loc:
            st.warning("Envío no encontrado. Refresca.")
            st.stop()

        loc_id = loc["id"]
        # If selected envio changed since last, refresh devices and reset add selection
        if st.session_state.last_envio_id != loc_id:
            st.session_state.last_envio_id = loc_id
            st.session_state.devices = load_devices()
            st.session_state.sel_tab3_add = []

        st.write(f"Inicio: {loc.get('start') or '-'} — Fin: {loc.get('end') or '-'}")
        st.markdown("---")

        # Assigned devices: show in a pill with an X button on the right
        assigned = [d for d in devices if loc_id in d.get("location_ids", [])]
        st.subheader("Asignadas:")
        if not assigned:
            st.info("No hay dispositivos asignados a esta Location.")
        else:
            for d in assigned:
                # render a row: card + small X button on right (in same visual row)
                cols = st.columns([9.0, 0.6])
                with cols[0]:
                    st.markdown(device_card(d["Name"], selected=False), unsafe_allow_html=True)
                with cols[1]:
                    # small X button; key unique
                    if st.button("✕", key=f"rem_x_{d['id']}", help="Quitar dispositivo de este envío"):
                        office = get_office_id()
                        if not office:
                            st.error("No existe Location 'Office' para reasignar. Crea la Location 'Office' en Notion.")
                        else:
                            assign_device_to_location(d["id"], office)
                            st.session_state.devices = load_devices()
                            st.rerun()

        st.markdown("---")
        st.subheader("Añadir disponibles (cargadas automáticamente por fechas del envío)")

        # compute can_add automatically for selected envio
        loc_start = iso_to_date(loc.get("start"))
        loc_end = iso_to_date(loc.get("end"))
        if not loc_start or not loc_end:
            st.warning("Esta Location no tiene fechas definidas correctamente.")
        else:
            can_add = [d for d in devices if available(d, loc_start, loc_end) and (loc_id not in d.get("location_ids", []))]
            # filter by type
            tags = sorted({t for t in (dd.get("Tags") for dd in can_add) if t})
            tags_opts = ["Todos"] + tags
            ftag = st.selectbox("Filtrar por tipo", options=tags_opts, key="tab3_filter")
            if ftag != "Todos":
                can_add = [d for d in can_add if d.get("Tags") == ftag]

            st.markdown(f"<div style='padding:6px;background:#C6F6C6;border-radius:6px;display:inline-block;font-weight:bold;'> {len(can_add)} disponibles para añadir </div>", unsafe_allow_html=True)
            st.markdown("")

            # checkboxes for can_add and accumulate selection in session
            add_ids = []
            for d in can_add:
                k = f"tab3_add_{d['id']}"
                if k not in st.session_state:
                    st.session_state[k] = False
                cols = st.columns([0.5, 9.5])
                with cols[0]:
                    sel_flag = st.checkbox("", key=k)
                with cols[1]:
                    st.markdown(device_card(d["Name"], selected=sel_flag), unsafe_allow_html=True)
                if sel_flag:
                    add_ids.append(d["id"])

            if add_ids:
                if st.button("Añadir seleccionadas"):
                    added = 0
                    for did in add_ids:
                        res = assign_device_to_location(did, loc_id)
                        if res is not None:
                            added += 1
                    st.success(f"✅ {added} dispositivos añadidos")
                    st.session_state.devices = load_devices()
                    # clear the add checkboxes
                    for did in add_ids:
                        key = f"tab3_add_{did}"
                        if key in st.session_state:
                            st.session_state[key] = False
                    st.rerun()

# ---------------- FOOTER ----------------
st.markdown("---")
st.markdown("Notas: usa 'Comprobar disponibilidad' para activar la búsqueda en la primera pestaña. Las listas se recargan automáticamente al cambiar de envío o pestaña.")
