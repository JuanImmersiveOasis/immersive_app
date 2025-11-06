# app.py - Logística Inmersive Oasis (final)
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
    st.error("❌ Falta NOTION_TOKEN en st.secrets o .env")
    st.stop()

NOTION_VERSION = "2022-06-28"
DEVICES_ID = "43e15b677c8c4bd599d7c602f281f1da"
LOCATIONS_ID = "28758a35e4118045abe6e37534c44974"

headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": NOTION_VERSION,
}

# ---------------- HELPERS NOTION ----------------
def q(db, payload=None):
    if payload is None:
        payload = {"page_size": 200}
    r = requests.post(f"https://api.notion.com/v1/databases/{db}/query", json=payload, headers=headers)
    try:
        return r.json().get("results", [])
    except:
        return []

def patch(page_id, data):
    return requests.patch(f"https://api.notion.com/v1/pages/{page_id}", json=data, headers=headers)

def create_page(data):
    return requests.post("https://api.notion.com/v1/pages", json=data, headers=headers)

# ---------------- PARSE DEVICES ----------------
def parse_device(p):
    props = p.get("properties", {})
    try:
        name = props["Name"]["title"][0]["text"]["content"]
    except:
        name = "Sin nombre"
    locs = []
    try:
        locs = [r["id"] for r in props.get("Location", {}).get("relation", [])]
    except:
        locs = []
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

# ---------------- UTIL ----------------
def iso_to_date(s):
    try:
        return datetime.fromisoformat(s).date()
    except:
        return None

def available(dev, start, end):
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

def office_id():
    r = q(LOCATIONS_ID, {"filter": {"property": "Name", "title": {"equals": "Office"}}})
    return r[0]["id"] if r else None

def in_house():
    r = q(LOCATIONS_ID, {"filter": {"property": "Type", "select": {"equals": "In House"}}})
    out = []
    for p in r:
        try:
            n = p["properties"]["Name"]["title"][0]["text"]["content"]
        except:
            n = "Sin nombre"
        out.append({"id": p["id"], "name": n})
    return out

def client_future():
    r = q(LOCATIONS_ID, {
        "filter": {
            "and": [
                {"property": "Type", "select": {"equals": "Client"}},
                {"property": "Start Date", "date": {"after": date.today().isoformat()}}
            ]
        }
    })
    out = []
    for p in r:
        try:
            n = p["properties"]["Name"]["title"][0]["text"]["content"]
        except:
            n = "Sin nombre"
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
        out.append({"id": p["id"], "name": n, "start": sd, "end": ed})
    return out

def assign_device(device_id, location_id):
    return patch(device_id, {"properties": {"Location": {"relation": [{"id": location_id}]}}})

# ---------------- SESSION (CACHE SUAVE) ----------------
if "devices" not in st.session_state:
    st.session_state.devices = load_devices()  # cache inicial

# selection lists - will be rebuilt deterministically later
if "sel_tab1" not in st.session_state:
    st.session_state.sel_tab1 = []  # names
if "sel_tab2" not in st.session_state:
    st.session_state.sel_tab2 = []  # ids
if "sel_tab3" not in st.session_state:
    st.session_state.sel_tab3 = []  # ids

# tab1 show flag (only after button)
if "tab1_show" not in st.session_state:
    st.session_state.tab1_show = False

# tab3 control: envio selected & search flags & available loaded
if "tab3_envio_selected" not in st.session_state:
    st.session_state.tab3_envio_selected = None
if "tab3_searched" not in st.session_state:
    st.session_state.tab3_searched = False
if "tab3_show_available" not in st.session_state:
    st.session_state.tab3_show_available = False

# last tab for reset
if "last_tab" not in st.session_state:
    st.session_state.last_tab = None

# ---------------- UI helpers ----------------
def card_html(name, selected):
    # original colors you requested
    bg = "#B3E5E6" if selected else "#e0e0e0"
    border = "#00859B" if selected else "#9e9e9e"
    return f"<div style='padding:8px 12px; background:{bg}; border-left:4px solid {border}; border-radius:6px; margin-bottom:6px;'><b>{name}</b></div>"

# ---------------- SIDEBAR ----------------
with st.sidebar:
    st.markdown("### Navegación")
    # keep the menu here
    menu = st.radio("", ["Disponibles para Alquilar", "Gafas para Equipo", "Próximos Envíos"])
    st.markdown("---")
    # Refresh button (opción A)
    if st.button("🔄 Consultar / Refrescar Devices", use_container_width=True):
        st.session_state.devices = load_devices()
        st.experimental_rerun()
    st.markdown("---")

# reset when tab changes (clean selections and flags)
if st.session_state.last_tab is None:
    st.session_state.last_tab = menu

if menu != st.session_state.last_tab:
    # clear checkboxes state keys to avoid stale keys
    # Reinitialize selection lists and flags
    st.session_state.sel_tab1 = []
    st.session_state.sel_tab2 = []
    st.session_state.sel_tab3 = []
    st.session_state.tab1_show = False
    st.session_state.tab3_envio_selected = None
    st.session_state.tab3_searched = False
    st.session_state.tab3_show_available = False
    st.session_state.last_tab = menu
    # keep devices cached (cache suave: not forced reload here)
    st.experimental_rerun()

devices = st.session_state.devices

# ---------------- TAB 1 ----------------
if menu == "Disponibles para Alquilar":
    st.title("Disponibles para Alquilar")

    c1, c2 = st.columns(2)
    with c1:
        start = st.date_input("Fecha inicio", date.today())
    with c2:
        end = st.date_input("Fecha fin", date.today())

    if st.button("Comprobar disponibilidad"):
        st.session_state.tab1_show = True
        # reload devices to get latest after action (cache suave: reload on explicit action)
        st.session_state.devices = load_devices()
        # clear any previous selection keys for tab1 items (they'll be created below)
        st.session_state.sel_tab1 = []
        st.experimental_rerun()

    if st.session_state.tab1_show:
        # compute available devices for the date range
        avail = [d for d in devices if available(d, start, end)]

        # filters only if tags exist
        tags = sorted({t for t in (x.get("Tags") for x in avail) if t})
        if tags:
            tag_opts = ["Todos"] + tags
            ftag = st.selectbox("Filtrar por tipo", options=tag_opts)
            if ftag != "Todos":
                avail = [d for d in avail if d.get("Tags") == ftag]

        # Render checkboxes and cards first
        for d in avail:
            key = f"tab1_{d['id']}"
            cols = st.columns([0.5, 9.5])
            with cols[0]:
                st.checkbox("", key=key)
            with cols[1]:
                checked = st.session_state.get(key, False)
                st.markdown(card_html(d["Name"], selected=checked), unsafe_allow_html=True)

        # Rebuild selection deterministically
        new_sel = []
        for d in avail:
            key = f"tab1_{d['id']}"
            if st.session_state.get(key, False):
                new_sel.append(d["Name"])
        st.session_state.sel_tab1 = new_sel

        total = len(avail)
        sel_count = len(st.session_state.sel_tab1)

        # Sidebar counter + assign form
        with st.sidebar:
            bg = "#e0e0e0" if sel_count == 0 else "#B3E5E6"
            st.markdown(f"<div style='padding:8px;background:{bg};border-radius:6px;font-weight:bold;text-align:center;'>{sel_count} / {total} dispositivos</div>", unsafe_allow_html=True)
            st.markdown("---")
            if sel_count > 0:
                st.markdown("#### Asignar a Cliente")
                client_name = st.text_input("Nombre Cliente", key="tab1_client_name")
                if st.button("Asignar Cliente"):
                    if not client_name or client_name.strip() == "":
                        st.error("El nombre del cliente no puede estar vacío")
                    else:
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
                            # assign all selected devices
                            name_to_id = {x["Name"]: x["id"] for x in devices}
                            assigned = 0
                            for nm in list(st.session_state.sel_tab1):
                                did = name_to_id.get(nm)
                                if did:
                                    assign_device(did, loc_id)
                                    assigned += 1
                            st.success(f"✅ {assigned} dispositivos asignados")
                            # refresh devices cache (cache suave: reload after changes)
                            st.session_state.devices = load_devices()
                            st.session_state.sel_tab1 = []
                            st.experimental_rerun()

# ---------------- TAB 2 ----------------
elif menu == "Gafas para Equipo":
    st.title("Gafas para Equipo")
    oid = office_id()
    if not oid:
        st.error("No existe Location con Name = 'Office'. Crea la Location Office en Notion.")
    else:
        office_devices = [d for d in devices if oid in d.get("location_ids", [])]

        # filter by tags only if exist
        tags = sorted({t for t in (x.get("Tags") for x in office_devices) if t})
        if tags:
            tag_opts = ["Todos"] + tags
            ftag = st.selectbox("Filtrar por tipo", options=tag_opts)
            if ftag != "Todos":
                office_devices = [d for d in office_devices if d.get("Tags") == ftag]

        # render list with checkboxes
        for d in office_devices:
            key = f"tab2_{d['id']}"
            cols = st.columns([0.5, 9.5])
            with cols[0]:
                st.checkbox("", key=key)
            with cols[1]:
                checked = st.session_state.get(key, False)
                st.markdown(card_html(d["Name"], selected=checked), unsafe_allow_html=True)

        # rebuild selection ids
        new_sel_ids = []
        for d in office_devices:
            key = f"tab2_{d['id']}"
            if st.session_state.get(key, False):
                new_sel_ids.append(d["id"])
        st.session_state.sel_tab2 = new_sel_ids

        total = len(office_devices)
        sel_count = len(st.session_state.sel_tab2)

        # sidebar counter + mover control
        with st.sidebar:
            bg = "#e0e0e0" if sel_count == 0 else "#B3E5E6"
            st.markdown(f"<div style='padding:8px;background:{bg};border-radius:6px;font-weight:bold;text-align:center;'>{sel_count} / {total} dispositivos</div>", unsafe_allow_html=True)
            st.markdown("---")
            if sel_count > 0:
                st.markdown("#### Mover a In House")
                inh = in_house()
                if not inh:
                    st.info("No hay In House definidas en Notion.")
                else:
                    dest_names = [x["name"] for x in inh]
                    dest_choice = st.selectbox("Destino:", dest_names, key="inhouse_choice_sidebar")
                    if st.button("Mover seleccionadas"):
                        dest_id = next(x["id"] for x in inh if x["name"] == dest_choice)
                        moved = 0
                        for did in list(st.session_state.sel_tab2):
                            assign_device(did, dest_id)
                            moved += 1
                        st.success(f"✅ {moved} dispositivos movidos")
                        st.session_state.devices = load_devices()
                        st.session_state.sel_tab2 = []
                        st.experimental_rerun()

# ---------------- TAB 3 ----------------
else:
    st.title("Próximos Envíos")

    # Selector with "Seleccionar..." default and Buscar to the right
    col_sel, col_btn = st.columns([8, 2])
    with col_sel:
        # options: placeholder + actual names
        locs = client_future()
        options = ["Seleccionar..."] + [x["name"] for x in locs]
        sel_name = st.selectbox("Selecciona envío:", options, index=0)
    with col_btn:
        # visual indicator plus action: button active only if selection != placeholder
        buscar_activo = sel_name != "Seleccionar..."
        if buscar_activo:
            # when clicked, set flags and load assigned
            if st.button("Buscar"):
                # find selected loc
                selected_loc = next((x for x in locs if x["name"] == sel_name), None)
                if selected_loc:
                    st.session_state.tab3_envio_selected = selected_loc["id"]
                    st.session_state.tab3_searched = True
                    st.session_state.tab3_show_available = False
                    # reload devices cache (cache suave)
                    st.session_state.devices = load_devices()
                    st.experimental_rerun()
        else:
            # show disabled button (visual only — clicking does nothing)
            st.markdown("<button disabled style='width:100%'>Buscar</button>", unsafe_allow_html=True)

    # Only after pressing Buscar we show Assigned accordion and sidebar counter
    if st.session_state.tab3_searched and st.session_state.tab3_envio_selected:
        # find the location object (from locs)
        selected_loc_obj = next((x for x in locs if x["id"] == st.session_state.tab3_envio_selected), None)
        loc_id = st.session_state.tab3_envio_selected

        # Assigned section inside expander (collapsed by default) - user chose Option B
        with st.expander(f"📦 Ver dispositivos asignados ({len([d for d in devices if loc_id in d.get('location_ids',[])])})", expanded=False):
            assigned = [d for d in devices if loc_id in d.get("location_ids", [])]
            if not assigned:
                st.info("No hay dispositivos asignados a esta Location.")
            else:
                for d in assigned:
                    cols = st.columns([9, 1])
                    with cols[0]:
                        st.markdown(card_html(d["Name"], selected=False), unsafe_allow_html=True)
                    with cols[1]:
                        # medium-size X button
                        if st.button("✕", key=f"tab3_rem_{d['id']}", help="Quitar dispositivo (vuelve a Office)"):
                            office = office_id()
                            if not office:
                                st.error("No existe Location 'Office' para reasignar.")
                            else:
                                assign_device(d["id"], office)
                                st.session_state.devices = load_devices()
                                st.experimental_rerun()

        # Sidebar counter present only after Buscar (counts selected to add / total available once loaded)
        # Show "Buscar disponibles" button below assigned accordion (in main area)
        if not st.session_state.tab3_show_available:
            if st.button("Buscar disponibles"):
                # compute available and show next render
                st.session_state.tab3_show_available = True
                st.experimental_rerun()

        # If we asked to show available, calculate and render them (deferred)
        if st.session_state.tab3_show_available:
            # compute can_add by dates in selected_loc_obj
            ls = iso_to_date(selected_loc_obj.get("start"))
            le = iso_to_date(selected_loc_obj.get("end"))
            if not ls or not le:
                st.warning("Esta Location no tiene fechas definidas correctamente.")
            else:
                can_add = [d for d in devices if available(d, ls, le) and (loc_id not in d.get("location_ids", []))]

                # show filters only if tags exist
                tags = sorted({t for t in (x.get("Tags") for x in can_add) if t})
                if tags:
                    tag_opts = ["Todos"] + tags
                    ftag = st.selectbox("Filtrar por tipo", options=tag_opts)
                    if ftag != "Todos":
                        can_add = [d for d in can_add if d.get("Tags") == ftag]

                # Render checkboxes and cards
                for d in can_add:
                    key = f"tab3_add_{d['id']}"
                    cols = st.columns([0.5, 9.5])
                    with cols[0]:
                        st.checkbox("", key=key)
                    with cols[1]:
                        checked = st.session_state.get(key, False)
                        st.markdown(card_html(d["Name"], selected=checked), unsafe_allow_html=True)

                # Rebuild sel_tab3 deterministically
                new_sel = []
                for d in can_add:
                    key = f"tab3_add_{d['id']}"
                    if st.session_state.get(key, False):
                        new_sel.append(d["id"])
                st.session_state.sel_tab3 = new_sel

                total = len(can_add)
                sel_count = len(st.session_state.sel_tab3)

                # Sidebar counter + Add button
                with st.sidebar:
                    bg = "#e0e0e0" if sel_count == 0 else "#B3E5E6"
                    st.markdown(f"<div style='padding:8px;background:{bg};border-radius:6px;font-weight:bold;text-align:center;'>{sel_count} / {total} dispositivos</div>", unsafe_allow_html=True)
                    st.markdown("---")
                    if sel_count > 0:
                        if st.button("Añadir seleccionadas"):
                            added = 0
                            for did in list(st.session_state.sel_tab3):
                                assign_device(did, loc_id)
                                added += 1
                            st.success(f"✅ {added} dispositivos añadidos")
                            # reload devices after change (cache suave)
                            st.session_state.devices = load_devices()
                            st.session_state.sel_tab3 = []
                            st.experimental_rerun()

# ---------------- FOOTER ----------------
st.markdown("---")
st.markdown("Notas: cache suave activado (se recargan dispositivos automáticamente tras operaciones de asignación). Usa 'Buscar' en 'Próximos Envíos' para cargar asignadas, y 'Buscar disponibles' para cargar las opciones de añadir (carga diferida).")
