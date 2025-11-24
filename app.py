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
HISTORIC_ID = "2a158a35e411806d9d11c6d77598d44d"
ACTIVE_INC_ID = "28c58a35e41180b8ae87fb11aec1f48e"
PAST_INC_ID   = "28e58a35e41180f29199c42d33500566"

headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": NOTION_VERSION,
}

# ---------------- HELPERS ----------------

def iso_to_date(s):
    try:
        return datetime.fromisoformat(s).date()
    except:
        return None

def fmt(date_str):
    """Formatea fechas a dd/mm/yyyy (si date_str es ISO)."""
    try:
        dt = iso_to_date(date_str)
        return dt.strftime("%d/%m/%Y")
    except:
        return date_str
    
def fmt_datetime(date_str):
    """Formatea fechas a dd/mm/yyyy HH:MM (si date_str es ISO con hora)."""
    try:
        dt = datetime.fromisoformat(date_str)
        return dt.strftime("%d/%m/%Y %H:%M")
    except:
        return date_str if date_str else "Sin fecha"    

def q(db, payload=None):
    """
    Query a Notion database and return ALL results (handles pagination).
    """
    if payload is None:
        payload = {"page_size": 200}

    url = f"https://api.notion.com/v1/databases/{db}/query"
    results = []
    next_cursor = None

    # Use an independent payload
    p = dict(payload)

    while True:
        if next_cursor:
            p["start_cursor"] = next_cursor

        r = requests.post(url, json=p, headers=headers)

        if r.status_code != 200:
            st.error(f"Error fetching database {db}: {r.status_code}")
            st.code(r.text)
            return []

        jr = r.json()
        results.extend(jr.get("results", []))

        if not jr.get("has_more", False):
            break

        next_cursor = jr.get("next_cursor", None)

        if not next_cursor:
            break

    return results

# ---------------- DEVICE AVAILABILITY ----------------

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

# ---------------- ASSIGN DEVICE ----------------

def assign_device(dev_id, loc_id):
    requests.patch(
        f"https://api.notion.com/v1/pages/{dev_id}",
        json={"properties": {"Location": {"relation": [{"id": loc_id}]}}},
        headers=headers
    )

# ---------------- LEGEND ----------------

def render_legend():
    st.markdown(
        """
        <div style='margin-bottom:10px;'>
            <span style='display:inline-block;width:20px;height:20px;line-height:20px;text-align:center;
                         font-weight:bold;color:#fff;background:#4CAF50;border-radius:4px;margin-right:6px'>O</span>
            Office: Las gafas se encuentran DISPONIBLES en oficina, libres de compromisos.<br>
            <span style='display:inline-block;width:20px;height:20px;line-height:20px;text-align:center;
                         font-weight:bold;color:#fff;background:#FF9800;border-radius:4px;margin-right:6px'>C</span>
            Client: Las gafas se encuentran ASIGNADAS a un proyecto en otras fechas.<br>
            <span style='display:inline-block;width:20px;height:20px;line-height:20px;text-align:center;
                         font-weight:bold;color:#fff;background:#1565C0;border-radius:4px;margin-right:6px'>H</span>
            At Home: Las gafas se encuentran en casa de algún miembro del equipo.
        </div>
        """,
        unsafe_allow_html=True
    )

# ---------------- LOAD MAP OF LOCATIONS ----------------
@st.cache_data(show_spinner=False)
def load_locations_map():
    """Devuelve diccionario id → {name, type}"""
    results = q(LOCATIONS_ID)
    out = {}
    for p in results:
        pid = p["id"]
        props = p["properties"]

        try:
            name = props["Name"]["title"][0]["text"]["content"]
        except:
            name = "Sin nombre"

        try:
            t = props["Type"]["select"]["name"]
        except:
            t = None

        out[pid] = {"name": name, "type": t}

    return out


# ---------------- DEVICES ----------------
@st.cache_data(show_spinner=False)
def load_devices():
    results = q(DEVICES_ID)
    out = []

    for p in results:
        props = p["properties"]

        name = props["Name"]["title"][0]["text"]["content"] if props["Name"]["title"] else "Sin nombre"
        tag = props["Tags"]["select"]["name"] if props.get("Tags") and props["Tags"]["select"] else None
        locs = [r["id"] for r in props["Location"]["relation"]] if props.get("Location") and props["Location"]["relation"] else []

        # Serial Number
        try:
            sn = props["SN"]["rich_text"][0]["text"]["content"]
        except:
            sn = ""

        # Rollups
        def roll(field):
            try:
                rr = props[field]["rollup"]
                if rr.get("array"):
                    return rr["array"][0]["date"]["start"]
                if rr.get("date"):
                    return rr["date"]["start"]
            except:
                return None

        out.append({
            "id": p["id"],
            "Name": name,
            "Tags": tag,
            "SN": sn,
            "location_ids": locs,
            "Start": roll("Start Date"),
            "End": roll("End Date")
        })

    return sorted(out, key=lambda x: x["Name"])


# ---------------- FUTURE CLIENT LOCATIONS ----------------
@st.cache_data(show_spinner=False)
def load_future_client_locations():
    today = date.today()
    results = q(LOCATIONS_ID)
    out = []

    for p in results:
        props = p["properties"]

        try:
            t = props["Type"]["select"]["name"]
        except:
            t = None

        if t != "Client":
            continue

        sd = props["Start Date"]["date"]["start"] if props.get("Start Date") and props["Start Date"]["date"] else None
        if not sd or iso_to_date(sd) < today:
            continue

        try:
            name = props["Name"]["title"][0]["text"]["content"]
        except:
            name = "Sin nombre"

        ed = props["End Date"]["date"]["start"] if props.get("End Date") and props["End Date"]["date"] else None

        out.append({
            "id": p["id"],
            "name": name,
            "start": sd,
            "end": ed
        })

    return out


# ---------------- IN HOUSE LOCATIONS ----------------
@st.cache_data(show_spinner=False)
def load_inhouse():
    results = q(LOCATIONS_ID, {"filter": {"property": "Type", "select": {"equals": "In House"}}})
    out = []

    for p in results:
        try:
            name = p["properties"]["Name"]["title"][0]["text"]["content"]
        except:
            name = "Sin nombre"

        out.append({"id": p["id"], "name": name})

    return out


# ---------------- OFFICE ID ----------------
def office_id():
    r = q(LOCATIONS_ID, {"filter": {"property": "Name", "title": {"equals": "Office"}}})
    return r[0]["id"] if r else None


# ---------------- CLEAR CACHE ----------------
def clear_all_cache():
    load_devices.clear()
    load_inhouse.clear()
    load_future_client_locations.clear()
    load_locations_map.clear()
    load_active_incidents.clear()
    load_past_incidents.clear()
    load_incidence_map.clear()


# ---------------- INCIDENTES ACTIVAS ----------------
@st.cache_data(show_spinner=False)
def load_active_incidents():
    r = q("28c58a35e41180b8ae87fb11aec1f48e")  # ACTIVE_INC_ID
    out = []

    for p in r:
        props = p["properties"]

        try:
            name = props["Name"]["title"][0]["text"]["content"]
        except:
            name = "Sin nombre"

        dev = None
        if "Device" in props and props["Device"]["relation"]:
            dev = props["Device"]["relation"][0]["id"]

        created = props.get("Created Date", {}).get("date", {}).get("start")

        notes = ""
        if props.get("Notes") and props["Notes"]["rich_text"]:
            notes = props["Notes"]["rich_text"][0]["text"]["content"]

        out.append({
            "id": p["id"],
            "Name": name,
            "Device": dev,
            "Created": created,
            "Notes": notes
        })

    return out


# ---------------- INCIDENTES PASADAS ----------------
@st.cache_data(show_spinner=False)
def load_past_incidents():
    r = q("28e58a35e41180f29199c42d33500566")  # PAST_INC_ID
    out = []

    for p in r:
        props = p["properties"]

        try:
            name = props["Name"]["title"][0]["text"]["content"]
        except:
            name = "Sin nombre"

        dev = None
        if "Device" in props and props["Device"]["relation"]:
            dev = props["Device"]["relation"][0]["id"]

        created = props.get("Created Date", {}).get("date", {}).get("start")
        resolved = props.get("Resolved Date", {}).get("date", {}).get("start")

        notes = ""
        if props.get("Notes") and props["Notes"]["rich_text"]:
            notes = props["Notes"]["rich_text"][0]["text"]["content"]

        rnotes = ""
        if props.get("Resolution Notes") and props["Resolution Notes"]["rich_text"]:
            rnotes = props["Resolution Notes"]["rich_text"][0]["text"]["content"]

        out.append({
            "id": p["id"],
            "Name": name,
            "Device": dev,
            "Created": created,
            "Notes": notes,
            "Resolved": resolved,
            "ResolutionNotes": rnotes
        })

    return out


# ---------------- INCIDENT MAP (NUEVO) ----------------
@st.cache_data(show_spinner=False)
def load_incidence_map():
    """
    Devuelve un diccionario:
    device_id → {active: N, total: M}
    """
    active = load_active_incidents()
    past = load_past_incidents()

    m = {}

    for inc in active:
        did = inc["Device"]
        if not did:
            continue
        if did not in m:
            m[did] = {"active": 0, "total": 0}
        m[did]["active"] += 1
        m[did]["total"] += 1

    for inc in past:
        did = inc["Device"]
        if not did:
            continue
        if did not in m:
            m[did] = {"active": 0, "total": 0}
        m[did]["total"] += 1

    return m

# ---------------- UI HELPERS ----------------

def card(name, location_types=None, selected=False, incident_counts=None):
    """
    Muestra una tarjeta (card) con el nombre del dispositivo.
    
    Parámetros:
    - name: Nombre del dispositivo (ej: "Quest 3 - Device 01")
    - location_types: Tipo de ubicación (ej: "Office", "Client", "In House")
    - selected: Si la card está seleccionada (cambia el color de fondo)
    - incident_counts: Tupla (incidencias_activas, total_incidencias) para mostrar badges
    """
    
    # Diccionario de colores de fondo según el tipo de ubicación
    color_map_bg = {
        "Office": "#D9E9DC",      # Verde claro
        "In House": "#E1EDF8",    # Azul claro
        "Client": "#F4ECDF"       # Naranja claro
    }
    
    # Diccionario de colores para los badges (etiquetas pequeñas)
    color_map_badge = {
        "Office": "#4CAF50",      # Verde
        "In House": "#1565C0",    # Azul
        "Client": "#FF9800"       # Naranja
    }
    
    # Diccionario de letras para los badges
    badge_letter_map = {
        "Office": "O",
        "In House": "H",
        "Client": "C"
    }

    # Color de fondo por defecto (gris)
    bg = "#e0e0e0"
    badge_html = ""

    # Si hay información de ubicación, crear el badge
    if location_types:
        first_type = location_types.split(" • ")[0]  # Tomar el primer tipo
        bg = color_map_bg.get(first_type, "#e0e0e0")
        badge_color = color_map_badge.get(first_type, "#B3E5E6")
        letter = badge_letter_map.get(first_type, "?")
        
        # HTML del badge de ubicación
        badge_html = (
            f"<span style='float:right;width:20px;height:20px;line-height:20px;"
            f"text-align:center;font-weight:bold;color:#fff;background:{badge_color};"
            f"border-radius:4px;margin-left:8px'>{letter}</span>"
        )

    # Si la card está seleccionada, cambiar el color de fondo
    if selected:
        bg = "#B3E5E6"

    # NUEVO: Badge de incidencias
    incident_badge_html = ""
    if incident_counts:
        active, total = incident_counts
        
        # Si hay incidencias activas, mostrar en rojo
        if active > 0:
            incident_badge_html = (
                f"<span style='float:right;width:auto;min-width:20px;height:20px;line-height:20px;"
                f"text-align:center;font-weight:bold;color:#fff;background:#E53935;"
                f"border-radius:4px;margin-left:8px;padding:0 6px;font-size:11px;'>"
                f"{active}/{total}</span>"
            )
        # Si solo hay incidencias pasadas, mostrar en gris
        elif total > 0:
            incident_badge_html = (
                f"<span style='float:right;width:auto;min-width:20px;height:20px;line-height:20px;"
                f"text-align:center;font-weight:bold;color:#fff;background:#9E9E9E;"
                f"border-radius:4px;margin-left:8px;padding:0 6px;font-size:11px;'>"
                f"0/{total}</span>"
            )

    # Renderizar la card con HTML
    st.markdown(
        f"""
        <div style='padding:7px;background:{bg};border-left:4px solid #9e9e9e;
                    border-radius:6px;margin-bottom:4px;overflow:auto;'>
            <b>{name}</b> {badge_html}{incident_badge_html} 
            <div style='clear:both;'></div>
        </div>
        """,
        unsafe_allow_html=True
    )


def counter_badge(selected, total):
    if selected > 0:
        bg = "#B3E5E6"
        tc = "#333"
    else:
        bg = "#e0e0e0"
        tc = "#666"

    st.markdown(
        f"""
        <div style='background:{bg};color:{tc};padding:12px 16px;border-radius:8px;
                    text-align:center;font-size:18px;font-weight:bold;margin-bottom:15px;
                    box-shadow:0 2px 4px rgba(0,0,0,0.1);'>
            {selected} / {total} seleccionadas
        </div>
        """,
        unsafe_allow_html=True
    )


def get_location_types_for_device(dev, loc_map):
    types = []
    for lid in dev.get("location_ids", []):
        entry = loc_map.get(lid)
        if entry and entry.get("type"):
            types.append(entry["type"])

    uniq = []
    seen = set()
    for t in types:
        if t not in seen:
            seen.add(t)
            uniq.append(t)

    return " • ".join(uniq) if uniq else None


# ---------------- TAG FILTERING ----------------
def segmented_tag_filter(devices, tag_field="Tags", groups=None, key_prefix="seg"):
    # Inferir etiquetas disponibles
    present_tags = sorted({(d.get(tag_field) or "") for d in devices if d.get(tag_field)})

    if groups is None:
        groups = present_tags

    # Construir contadores
    counts = {"Todas": len(devices)}
    for g in groups:
        counts[g] = sum(1 for d in devices if d.get(tag_field) == g)

    # Construcción de opciones
    opciones = {f"Todas ({counts['Todas']})": "Todas"}
    for g in groups:
        opciones[f"{g} ({counts[g]})"] = g

    # Control UI
    sel_label = st.segmented_control(
        label=None,
        options=list(opciones.keys()),
        default=list(opciones.keys())[0],
        key=f"{key_prefix}_seg"
    )

    # Protección
    if sel_label not in opciones:
        sel_label = list(opciones.keys())[0]
        st.session_state[f"{key_prefix}_seg"] = sel_label

    selected_group = opciones[sel_label]

    # Filtrado
    if selected_group == "Todas":
        filtered = devices
    else:
        filtered = [d for d in devices if d.get(tag_field) == selected_group]

    return filtered, selected_group, counts, opciones

# ---------------- STATE ----------------
for key, default in [
    ("tab1_show", False), ("sel1", []), ("sel2", []),
    ("sel3", []), ("tab3_loc", None), ("show_avail_tab3", False),
    ("show_avail_home", False)
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ---------------- SIDEBAR NAV ----------------
with st.sidebar:

    # ---------- CONTADOR: Próximos envíos ----------
    try:
        num_proximos = len(load_future_client_locations())
    except:
        num_proximos = 0

    # ---------- CONTADOR: Envíos finalizados (Check-In pendientes) ----------
    today = date.today()
    all_locs = q(LOCATIONS_ID)
    devices_tmp = load_devices()

    finished = []
    for p in all_locs:
        props = p["properties"]

        if props.get("Type", {}).get("select", {}).get("name") != "Client":
            continue

        end_prop = props.get("End Date")
        if isinstance(end_prop, dict):
            date_obj = end_prop.get("date")
            ed = date_obj.get("start") if isinstance(date_obj, dict) else None
        else:
            ed = None

        if not ed or iso_to_date(ed) >= today:
            continue

        loc_id = p["id"]
        assigned = [d for d in devices_tmp if loc_id in d["location_ids"]]
        if len(assigned) == 0:
            continue

        finished.append(p)

    num_finished = len(finished)

    # ---------- CONTADOR: Incidencias activas ----------
    try:
        actives_nav = load_active_incidents()
        num_incidencias = len(actives_nav)
    except:
        num_incidencias = 0

    # ---------- CREAR OPCIONES CON NÚMEROS ----------
    st.markdown("### 📋 Navegación")
    
    # Función para crear label con número en badge rojo
    def create_menu_label(text, count=0):
        if count > 0:
            # Con badge rojo mostrando el número
            return f"{text}   ({count})"
        else:
            # Sin badge
            return text
    
    # Opciones de navegación con números
    opciones_menu = [
        create_menu_label("Disponibles para Alquilar", 0),
        create_menu_label("Gafas en casa", 0),
        create_menu_label("Próximos Envíos", num_proximos),
        create_menu_label("Check-In", num_finished),
        create_menu_label("Incidencias", num_incidencias)
    ]
    
    # Mapeo de labels a valores internos
    menu_mapping = {
        opciones_menu[0]: "Disponibles para Alquilar",
        opciones_menu[1]: "Gafas en casa",
        opciones_menu[2]: "Próximos Envíos",
        opciones_menu[3]: "Check-In",
        opciones_menu[4]: "Incidencias"
    }
    
    # Radio buttons
    selected_label = st.radio(
        label="nav",
        options=opciones_menu,
        label_visibility="collapsed",
        key="nav_radio"
    )
    
    # Obtener el valor interno
    st.session_state.menu = menu_mapping[selected_label]

    st.markdown("----")

    # REFRESCAR
    if st.button("🔄 Refrescar", use_container_width=True):
        clear_all_cache()
        st.rerun()

# ---------- Cargar mapa de localizaciones DESPUÉS del sidebar ----------
locations_map = load_locations_map()

# ---------- Cargar mapa de incidencias para TODA la app (NUEVA LÍNEA) ----------
incidence_map = load_incidence_map()

# ---------------- TAB 1 ----------------
if st.session_state.menu == "Disponibles para Alquilar":
    st.title("Disponibles para Alquilar")

    with st.expander("📘 Leyenda de estados"):
        render_legend()

    # Filtros de fechas
    c1, c2 = st.columns(2)
    with c1:
        start = st.date_input("Fecha inicio", date.today())
    with c2:
        end = st.date_input("Fecha fin", date.today())

    # Botón comprobar
    if st.button("Comprobar disponibilidad"):
        st.session_state.tab1_show = True
        st.session_state.sel1 = []

    # Si ya mostramos disponibilidad
    if st.session_state.tab1_show:
        devices = load_devices()

        # Filtrar dispositivos disponibles
        avail = [
            d for d in devices
            if d.get("location_ids") and available(d, start, end)
        ]

        # Filtro por tipo (reuse)
        groups = ["Ultra", "Neo 4", "Quest 2", "Quest 3"]
        avail_filtered, _, _, _ = segmented_tag_filter(avail, groups=groups, key_prefix="tab1")

        # Render cards
        for d in avail_filtered:
            key = f"a_{d['id']}"
            subtitle = get_location_types_for_device(d, locations_map)

            cols = st.columns([0.5, 9.5])
            with cols[0]:
                st.checkbox("", key=key)

            with cols[1]:
                # INCIDENCIA DE ESTE DEVICE
                inc = incidence_map.get(d["id"], {"active": 0, "total": 0})

                card(
                    d["Name"],
                    location_types=subtitle,
                    selected=st.session_state.get(key, False),
                    incident_counts=(inc["active"], inc["total"])
                )

        # Actualizar selección
        st.session_state.sel1 = [
            d["id"] for d in avail_filtered if st.session_state.get(f"a_{d['id']}", False)
        ]
        sel_count = len(st.session_state.sel1)

        # Sidebar: contador + asignación
        with st.sidebar:
            counter_badge(sel_count, len(avail_filtered))

            if sel_count > 0:
                client = st.text_input("Nombre Cliente")

                if st.button("Asignar Cliente"):
                    # Crear la localización del cliente
                    new = requests.post(
                        "https://api.notion.com/v1/pages", headers=headers,
                        json={
                            "parent": {"database_id": LOCATIONS_ID},
                            "properties": {
                                "Name": {"title": [{"text": {"content": client}}]},
                                "Type": {"select": {"name": "Client"}},
                                "Start Date": {"date": {"start": start.isoformat()}},
                                "End Date": {"date": {"start": end.isoformat()}}
                            }
                        }
                    ).json()["id"]

                    # Asignar dispositivos
                    for did in st.session_state.sel1:
                        assign_device(did, new)

                    st.success("Asignado correctamente")
                    clear_all_cache()
                    st.rerun()

# ---------------- TAB 2 ----------------
elif st.session_state.menu == "Gafas en casa":

    st.title("Gafas en casa")

    # Cargar devices una sola vez en sesión
    if "devices_live" not in st.session_state:
        st.session_state.devices_live = load_devices()

    devices = st.session_state.devices_live
    inh = load_inhouse()
    oid = office_id()

    # Tipos de gafas para filtro
    groups = ["Ultra", "Neo 4", "Quest 2", "Quest 3"]

    with st.expander("📘 Leyenda de estados"):
        render_legend()

    # IDs de localizaciones de tipo "In House"
    inh_ids = [p["id"] for p in inh]

    # Dispositivos que están en casa
    inhouse_devices = [
        d for d in devices
        if any(l in inh_ids for l in d["location_ids"])
    ]

    # ------------------------------
    # PERSONAL CON DISPOSITIVOS EN CASA
    # ------------------------------
    with st.expander("Personal con dispositivos en casa", expanded=True):

        # Filtro por tipo
        inhouse_filtered, _, _, _ = segmented_tag_filter(
            inhouse_devices, groups=groups, key_prefix="inhouse"
        )

        # Mapear persona → dispositivos
        people_devices = {p["id"]: [] for p in inh}
        for d in inhouse_filtered:
            for lid in d["location_ids"]:
                if lid in people_devices:
                    people_devices[lid].append(d)

        # Personas que efectivamente tienen gafas filtradas
        people_with_devices = [
            p for p in inh if len(people_devices[p["id"]]) > 0
        ]

        # Render para cada persona
        for person in people_with_devices:
            pid = person["id"]
            pname = person["name"]
            devs = people_devices.get(pid, [])

            with st.expander(f"{pname} ({len(devs)})"):
                for d in devs:

                    cols = st.columns([9.2, 0.8])

                    with cols[0]:
                        # INCIDENCIA
                        inc = incidence_map.get(d["id"], {"active": 0, "total": 0})

                        card(
                            d["Name"],
                            location_types="In House",
                            incident_counts=(inc["active"], inc["total"])
                        )

                    # Botón para devolver a oficina
                    with cols[1]:
                        if st.button("✕", key=f"rm_{d['id']}"):
                            assign_device(d["id"], oid)
                            clear_all_cache()
                            st.session_state.devices_live = load_devices()
                            st.rerun()

    # ------------------------------
    # Otras gafas disponibles en oficina
    # ------------------------------

    office_devices = [
        d for d in devices
        if oid in d["location_ids"]
    ]

    with st.expander("Otras gafas disponibles en oficina", expanded=False):

        office_filtered, _, _, _ = segmented_tag_filter(
            office_devices, groups=groups, key_prefix="office"
        )

        for d in office_filtered:
            key = f"o_{d['id']}"
            subtitle = get_location_types_for_device(d, locations_map)

            cols = st.columns([0.5, 9.5])

            with cols[0]:
                st.checkbox("", key=key)

            with cols[1]:
                # INCIDENCIAS
                inc = incidence_map.get(d["id"], {"active": 0, "total": 0})

                card(
                    d["Name"],
                    location_types=subtitle,
                    selected=st.session_state.get(key, False),
                    incident_counts=(inc["active"], inc["total"])
                )

        # Selección
        st.session_state.sel2 = [
            d["id"] for d in office_filtered
            if st.session_state.get(f"o_{d['id']}", False)
        ]
        sel_count = len(st.session_state.sel2)

        # Sidebar: contador + asignar dispositivos
        with st.sidebar:
            counter_badge(sel_count, len(office_filtered))

            if sel_count > 0:
                dest = st.selectbox("Asignar a:", [x["name"] for x in inh])
                dest_id = next(x["id"] for x in inh if x["name"] == dest)

                if st.button("Asignar seleccionadas"):
                    for did in st.session_state.sel2:
                        assign_device(did, dest_id)

                    clear_all_cache()
                    st.session_state.devices_live = load_devices()
                    st.success("Asignación completada")
                    st.rerun()

# ---------------- TAB 3 ----------------
elif st.session_state.menu == "Próximos Envíos":
    st.title("Próximos Envíos")

    with st.expander("📘 Leyenda de estados"):
        render_legend()

    # Cargar envíos futuros
    future_locs = load_future_client_locations()

    with st.expander(f"📦 Envíos futuros ({len(future_locs)})", expanded=True):

        if len(future_locs) == 0:
            st.info("No hay envíos futuros.")
            st.stop()

        # Para cada envío futuro
        for loc in future_locs:

            lname = loc["name"]
            start = fmt(loc["start"])
            end = fmt(loc["end"])
            loc_id = loc["id"]

            devices = load_devices()
            groups = ["Ultra", "Neo 4", "Quest 2", "Quest 3"]

            # ------------------------------
            # EXPANDER POR ENVÍO
            # ------------------------------
            with st.expander(f"{lname} ({start} → {end})", expanded=False):

                # ===================================
                # A) Gafas asignadas a este envío
                # ===================================

                assigned = [
                    d for d in devices
                    if loc_id in d["location_ids"]
                ]

                st.subheader("Dispositivos asignados")

                assigned_filtered, _, _, _ = segmented_tag_filter(
                    assigned, groups=groups, key_prefix=f"assigned_{loc_id}"
                )

                for d in assigned_filtered:

                    cols = st.columns([9, 1])

                    with cols[0]:
                        subtitle = get_location_types_for_device(d, locations_map)

                        # INCIDENCIAS
                        inc = incidence_map.get(d["id"], {"active": 0, "total": 0})

                        card(
                            d["Name"],
                            location_types=subtitle,
                            incident_counts=(inc["active"], inc["total"])
                        )

                    with cols[1]:
                        if st.button("✕", key=f"rm_{loc_id}_{d['id']}"):
                            assign_device(d["id"], office_id())
                            clear_all_cache()
                            st.rerun()

                # ===================================
                # B) Añadir más gafas disponibles
                # ===================================

                with st.expander("Más gafas disponibles", expanded=False):

                    ls = iso_to_date(loc["start"])
                    le = iso_to_date(loc["end"])

                    can_add = [
                        d for d in devices
                        if d.get("location_ids")
                        and available(d, ls, le)
                        and loc_id not in d["location_ids"]
                    ]

                    can_add_filtered, _, _, _ = segmented_tag_filter(
                        can_add, groups=groups, key_prefix=f"canadd_{loc_id}"
                    )

                    # Lista de gafas disponibles para añadir
                    checkbox_keys = []

                    for d in can_add_filtered:
                        key = f"add_{loc_id}_{d['id']}"
                        checkbox_keys.append(key)

                        subtitle = get_location_types_for_device(d, locations_map)

                        cols = st.columns([0.5, 9.5])

                        with cols[0]:
                            st.checkbox("", key=key)

                        with cols[1]:
                            # INCIDENCIAS
                            inc = incidence_map.get(d["id"], {"active": 0, "total": 0})

                            card(
                                d["Name"],
                                location_types=subtitle,
                                selected=st.session_state.get(key, False),
                                incident_counts=(inc["active"], inc["total"])
                            )

                    # Obtener selección
                    selected_ids = [
                        key.split("_")[-1]
                        for key in checkbox_keys
                        if st.session_state.get(key, False)
                    ]

                    sel_count = len(selected_ids)

                    # Contador + Botón asignar
                    with st.sidebar:
                        counter_badge(sel_count, len(can_add_filtered))

                        if sel_count > 0:
                            if st.button(f"Añadir a {lname}", key=f"assign_{loc_id}"):

                                for did in selected_ids:
                                    assign_device(did, loc_id)

                                st.success("Añadidas correctamente")
                                clear_all_cache()
                                st.rerun()

# ---------------- TAB 4 — CHECK-IN ----------------
elif st.session_state.menu == "Check-In":
    st.title("Check-In de Gafas (de vuelta a oficina)")

    with st.expander("📘 Leyenda de estados"):
        render_legend()

    today = date.today()
    all_locs = q(LOCATIONS_ID)
    devices = load_devices()

    # -------------------------
    # Encontrar envíos finalizados
    # -------------------------
    finished = []

    for p in all_locs:
        props = p["properties"]

        # Debe ser tipo "Client"
        if not props.get("Type") or props["Type"]["select"]["name"] != "Client":
            continue

        # End Date
        ed = None
        if props.get("End Date") and props["End Date"].get("date"):
            ed = props["End Date"]["date"]["start"]

        if not ed:
            continue

        if iso_to_date(ed) >= today:
            continue

        loc_id = p["id"]
        assigned = [d for d in devices if loc_id in d["location_ids"]]

        # Si no hay dispositivos asignados, no hay check-in
        if len(assigned) == 0:
            continue

        finished.append({
            "id": loc_id,
            "name": props["Name"]["title"][0]["text"]["content"],
            "end": ed
        })

    if not finished:
        st.info("No hay envíos finalizados con dispositivos.")
        st.stop()

    # -------------------------
    # Selector de envío
    # -------------------------
    options = ["Seleccionar..."] + [
        f"{x['name']} (fin {fmt(x['end'])})" for x in finished
    ]

    sel = st.selectbox("Selecciona envío terminado:", options)

    if sel != "Seleccionar...":
        loc = finished[options.index(sel) - 1]

        st.write(f"📅 Finalizó el **{fmt(loc['end'])}**")

        assigned = [
            d for d in devices
            if loc["id"] in d["location_ids"]
        ]

        office = office_id()

        # -------------------------
        # Devices para Check-In
        # -------------------------
        with st.expander(f"📦 Gafas para recepcionar ({len(assigned)})", expanded=True):

            for d in assigned:

                cols = st.columns([9, 1])

                with cols[0]:

                    subtitle = get_location_types_for_device(d, locations_map)

                    # Obtener incidencias globales
                    inc = incidence_map.get(d["id"], {"active": 0, "total": 0})

                    card(
                        d["Name"],
                        location_types=subtitle,
                        incident_counts=(inc["active"], inc["total"])
                    )

                # -------------------------
                # Botón Check-In
                # -------------------------
                with cols[1]:
                    if st.button("📥", key=f"checkin_{d['id']}"):

                        # Crear entrada en histórico
                        payload = {
                            "parent": {"database_id": HISTORIC_ID},
                            "properties": {
                                "Name": {"title": [{"text": {"content": d['Name']}}]},
                                "Tags": {"select": {"name": d["Tags"]}} if d.get("Tags") else None,
                                "SN": {"rich_text": [{"text": {"content": d.get("SN", "")}}]},

                                "Location": {"relation": [{"id": loc["id"]}]},

                                "Start Date": {"date": {"start": d["Start"]}}
                                    if d.get("Start") else None,

                                "End Date": {"date": {"start": d["End"]}}
                                    if d.get("End") else None,

                                "Check In": {"date": {"start": date.today().isoformat()}}
                            }
                        }

                        # Eliminar None
                        payload["properties"] = {
                            k: v for k, v in payload["properties"].items() if v is not None
                        }

                        r = requests.post(
                            "https://api.notion.com/v1/pages",
                            headers=headers,
                            json=payload
                        )

                        if r.status_code != 200:
                            st.error(f"❌ Error al registrar en histórico ({r.status_code})")
                            st.code(r.text)
                        else:
                            # Mover a oficina
                            assign_device(d["id"], office)

                            st.success("Registro añadido correctamente")
                            clear_all_cache()
                            st.rerun()


# ---------------- TAB 5 – INCIDENCIAS ----------------
elif st.session_state.menu == "Incidencias":

    st.title("Incidencias de dispositivos")

    ACTIVE_INC_ID = "28c58a35e41180b8ae87fb11aec1f48e"
    PAST_INC_ID   = "28e58a35e41180f29199c42d33500566"

    # -------------------------
    # Cargar incidencias
    # -------------------------
    actives = load_active_incidents()
    pasts = load_past_incidents()
    devices = load_devices()

    # Crear mapa device → incidencias
    device_map = {d["id"]: {"dev": d, "active": [], "past": []} for d in devices}

    for a in actives:
        if a["Device"] in device_map:
            device_map[a["Device"]]["active"].append(a)

    for p in pasts:
        if p["Device"] in device_map:
            device_map[p["Device"]]["past"].append(p)

    # Filtrar dispositivos con incidencias
    devices_with_inc = [
        entry for entry in device_map.values()
        if len(entry["active"]) + len(entry["past"]) > 0
    ]

    # Contar total de incidencias activas
    total_active = sum(len(entry["active"]) for entry in devices_with_inc)

    # -------------------------
    # EXPANDER SUPERIOR con contador
    # -------------------------
    with st.expander(f"Gafas con incidencias ({total_active} activas)", expanded=True):

        if not devices_with_inc:
            st.info("No hay incidencias registradas.")
        else:
            for entry in devices_with_inc:

                dev = entry["dev"]
                active_list = entry["active"]
                past_list = entry["past"]

                active_count = len(active_list)
                total_count = active_count + len(past_list)

                subtitle = get_location_types_for_device(dev, locations_map)

                # --- Render card con badge de incidencias ---
                card(
                    dev["Name"],
                    location_types=subtitle,
                    incident_counts=(active_count, total_count)
                )

                # Ordenar activas y pasadas por separado
                # Ordenar activas (más recientes primero)
                active_sorted = sorted(
                    active_list,
                    key=lambda x: x.get("Created") or "",
                    reverse=True
                )

                # Ordenar pasadas (más recientes primero)
                past_sorted = sorted(
                    past_list,
                    key=lambda x: x.get("Created") or "",
                    reverse=True
                )

                # ===========================
                # INCIDENCIAS ACTIVAS
                # ===========================
                if active_sorted:

                    for inc in active_sorted:
                        notes = inc.get('Notes', '').replace('<', '&lt;').replace('>', '&gt;')
                        created = fmt_datetime(inc.get('Created'))

                        # Crear columnas para botón a la derecha
                        cols = st.columns([8, 2])

                        with cols[0]:
                            st.markdown(
                                f"""
                                <div style='margin-left:20px; margin-bottom:10px; padding:8px;
                                            background:#FFEBEE;
                                            border-radius:4px;'>
                                    <div style='display:flex; align-items:center; margin-bottom:4px;'>
                                        <div style='width:10px; height:10px; background:#E53935;
                                                    border-radius:50%; margin-right:8px;'></div>
                                        <strong style='font-size:14px; color:#333;'>{inc['Name']}</strong>
                                        <span style='margin-left:8px; color:#888; font-size:12px;'>
                                            {created}
                                        </span>
                                    </div>
                                    <div style='margin-left:18px; color:#666; font-size:13px;'>
                                        {notes if notes else '<em>Sin notas</em>'}
                                    </div>
                                </div>
                                """,
                                unsafe_allow_html=True
                            )

                        # Botón resolver a la derecha
                        with cols[1]:
                            if st.button("Resolver", key=f"resolve_{inc['id']}", help="Resolver incidencia"):
                                st.session_state.solve_inc = inc
                                st.rerun()

               # ===========================
                # INCIDENCIAS PASADAS
                # ===========================
                if past_sorted:

                    for inc in past_sorted:
                        notes = inc.get('Notes', '').replace('<', '&lt;').replace('>', '&gt;')
                        created = fmt_datetime(inc.get('Created'))
                        resolved = fmt_datetime(inc.get('Resolved'))
                        
                        # Obtener notas de resolución
                        resolution_notes = inc.get('ResolutionNotes', '')
                        
                        # ✅ CAMBIO: Solo mostrar si hay contenido real
                        if resolution_notes:
                            resolution_notes = resolution_notes.replace('<', '&lt;').replace('>', '&gt;')
                            resolution_html = f"<div style='margin-left:18px; color:#4CAF50; font-size:13px; margin-top:4px;'>{resolution_notes}</div>"
                        else:
                            resolution_html = ""

                        st.markdown(
                            f"""
                            <div style='margin-left:20px; margin-bottom:10px; padding:8px;
                                        background:#F5F5F5; 
                                        border-radius:4px;'>
                                <div style='display:flex; align-items:center; margin-bottom:4px;'>
                                    <div style='width:10px; height:10px; background:#9E9E9E;
                                                border-radius:50%; margin-right:8px;'></div>
                                    <strong style='font-size:14px; color:#555;'>{inc['Name']}</strong>
                                    <span style='margin-left:8px; color:#888; font-size:12px;'>
                                        Creada: {created} • Resuelta: {resolved}
                                    </span>
                                </div>
                                <div style='margin-left:18px; color:#666; font-size:13px;'>
                                    {notes if notes else '<em>Sin notas</em>'}
                                </div>
                                {resolution_html}
                            </div>
                            """,
                            unsafe_allow_html=True
                        )

                # Separación visual entre dispositivos
                st.markdown("<div style='height:15px;'></div>", unsafe_allow_html=True)


    # -------------------------
    # RESOLVER INCIDENCIA (sidebar)
    # -------------------------
    if "solve_inc" not in st.session_state:
        st.session_state.solve_inc = None

    if st.session_state.solve_inc:

        inc = st.session_state.solve_inc

        with st.sidebar:
            st.header("Resolver incidencia")
            st.write(f"**{inc['Name']}**")
            
            # Mostrar información de la incidencia original
            st.caption(f"Creada: {fmt_datetime(inc.get('Created'))}")
            if inc.get('Notes'):
                st.caption(f"Notas: {inc['Notes']}")

            # Usar date_input Y time_input para fecha y hora
            col_date, col_time = st.columns(2)
            
            with col_date:
                resolved_date = st.date_input(
                    "Fecha de resolución", 
                    value=date.today()
                )
            
            with col_time:
                resolved_time = st.time_input(
                    "Hora de resolución",
                    value=datetime.now().time()
                )
            
            rnotes = st.text_area("Notas de resolución")

            col1, col2 = st.columns(2)

            with col1:
                if st.button("✅ Confirmar", use_container_width=True):

                    # Combinar fecha y hora
                    resolved_datetime = datetime.combine(resolved_date, resolved_time)
                    resolved_iso = resolved_datetime.isoformat()

                    # Verificar que tenemos todos los datos necesarios
                    if not inc.get("Device"):
                        st.error("❌ Error: La incidencia no tiene dispositivo asociado")
                    else:
                        # Construir propiedades
                        properties = {
                            "Name": {"title": [{"text": {"content": inc["Name"]}}]},
                            "Device": {"relation": [{"id": inc["Device"]}]},
                            "Created Date": {"date": {"start": inc.get("Created", datetime.now().isoformat())}},
                            "Notes": {"rich_text": [{"text": {"content": inc.get("Notes", "")}}]},
                            "Resolved Date": {"date": {"start": resolved_iso}},
                        }
                        
                        # Añadir notas de resolución si existen
                        if rnotes:
                            properties["Resolution Notes"] = {"rich_text": [{"text": {"content": rnotes}}]}
                        
                        # Crear payload
                        payload = {
                            "parent": {"database_id": PAST_INC_ID},
                            "properties": properties
                        }

                        # Crear incidencia resuelta en PAST_INC_ID
                        response_create = requests.post(
                            "https://api.notion.com/v1/pages",
                            headers=headers,
                            json=payload
                        )

                        if response_create.status_code == 200:
                            # Archivar (borrar) la incidencia activa original
                            response_archive = requests.patch(
                                f"https://api.notion.com/v1/pages/{inc['id']}",
                                headers=headers,
                                json={"archived": True}
                            )

                            if response_archive.status_code == 200:
                                st.success("✅ Incidencia resuelta correctamente.")
                                st.session_state.solve_inc = None
                                clear_all_cache()
                                st.rerun()
                            else:
                                st.error(f"❌ Error al archivar incidencia activa: {response_archive.status_code}")
                                st.code(response_archive.text)
                        else:
                            st.error(f"❌ Error al crear incidencia resuelta: {response_create.status_code}")
                            st.code(response_create.text)

            with col2:
                if st.button("❌ Cancelar", use_container_width=True):
                    st.session_state.solve_inc = None
                    st.rerun()

   # -------------------------
    # AÑADIR NUEVA INCIDENCIA
    # -------------------------
    
    # ✅ NUEVO: Limpiar checkboxes si se creó una incidencia
    if "clear_new_inc_checkboxes" in st.session_state and st.session_state.clear_new_inc_checkboxes:
        # Limpiar todos los checkboxes que empiecen con "newinc_"
        keys_to_clear = [k for k in st.session_state.keys() if k.startswith("newinc_")]
        for key in keys_to_clear:
            st.session_state[key] = False
        
        # Limpiar la bandera
        st.session_state.clear_new_inc_checkboxes = False
    
    with st.expander("➕ Añadir nueva incidencia", expanded=False):

        groups = ["Ultra", "Neo 4", "Quest 2", "Quest 3"]
        
        # Filtrar solo dispositivos con location activa
        devices_with_location = [
            d for d in devices 
            if d.get("location_ids") and len(d["location_ids"]) > 0
        ]
        
        devices_filtered, _, _, _ = segmented_tag_filter(
            devices_with_location,
            groups=groups, 
            key_prefix="new_inc"
        )

        sel_keys = []

        for d in devices_filtered:
            key = f"newinc_{d['id']}"
            sel_keys.append(key)

            subtitle = get_location_types_for_device(d, locations_map)

            cols = st.columns([0.5, 9.5])

            with cols[0]:
                st.checkbox("", key=key)

            with cols[1]:
                # incidencias globales
                inc = incidence_map.get(d["id"], {"active": 0, "total": 0})

                card(
                    d["Name"],
                    location_types=subtitle,
                    incident_counts=(inc["active"], inc["total"])
                )

        selected = [
            k.split("_")[1] for k in sel_keys if st.session_state.get(k, False)
        ]

        # Mostrar contador de seleccionados
        if selected:
            with st.sidebar:
                counter_badge(len(selected), len(devices_filtered))

        # Sidebar: crear incidencia
        with st.sidebar:
            if selected:
                st.header("Nueva incidencia")
                name = st.text_input("Título incidencia", key="new_inc_name")
                notes = st.text_area("Notas", key="new_inc_notes")

                if st.button("Crear incidencia", type="primary", use_container_width=True):
                    
                    # Validación: verificar que hay título
                    if not name or name.strip() == "":
                        st.error("❌ Debes escribir un título para la incidencia")
                    else:
                        # Usar datetime.now() en lugar de date.today()
                        now = datetime.now().isoformat()
                        
                        success = True
                        for did in selected:

                            payload = {
                                "parent": {"database_id": ACTIVE_INC_ID},
                                "properties": {
                                    "Name": {"title": [{"text": {"content": name}}]},
                                    "Device": {"relation": [{"id": did}]},
                                    "Notes": {"rich_text": [{"text": {"content": notes}}]},
                                    "Created Date": {"date": {"start": now}}
                                }
                            }

                            response = requests.post(
                                "https://api.notion.com/v1/pages",
                                headers=headers,
                                json=payload
                            )
                            
                            if response.status_code != 200:
                                st.error(f"❌ Error al crear incidencia: {response.status_code}")
                                st.code(response.text)
                                success = False
                                break

                        if success:
                            # ✅ CAMBIO: Activar bandera para limpiar checkboxes
                            st.session_state.clear_new_inc_checkboxes = True

                            # ✅ Limpiar campos del formulario
                            if "new_inc_name" in st.session_state:
                                del st.session_state["new_inc_name"]
                            if "new_inc_notes" in st.session_state:
                                del st.session_state["new_inc_notes"]

                            # ✅ Limpiar caché
                            clear_all_cache()
                            
                            # ✅ Recargar página
                            st.rerun()