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

def q(db, payload=None):
    """
    Query a Notion database and return ALL results (handles pagination).
    """
    if payload is None:
        payload = {"page_size": 200}

    url = f"https://api.notion.com/v1/databases/{db}/query"
    results = []
    has_more = True
    next_cursor = None

    # Make a shallow copy to avoid mutating caller's payload
    p = dict(payload)

    while True:
        if next_cursor:
            p["start_cursor"] = next_cursor
        r = requests.post(url, json=p, headers=headers)
        if r.status_code != 200:
            # Bubble up error in a helpful way
            try:
                st.error(f"Error fetching database {db}: {r.status_code}")
                st.code(r.text)
            except:
                pass
            return []
        jr = r.json()
        results.extend(jr.get("results", []))
        if not jr.get("has_more", False):
            break
        next_cursor = jr.get("next_cursor", None)
        if not next_cursor:
            break
    return results

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

def assign_device(dev_id, loc_id):
    requests.patch(
        f"https://api.notion.com/v1/pages/{dev_id}",
        json={"properties": {"Location": {"relation": [{"id": loc_id}]}}},
        headers=headers
    )

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

# ---------------- CACHED LOADERS ----------------
@st.cache_data(show_spinner=False)
def load_devices():
    results = q(DEVICES_ID)
    out = []
    for p in results:
        props = p["properties"]

        name = props["Name"]["title"][0]["text"]["content"] if props["Name"]["title"] else "Sin nombre"
        tag = props["Tags"]["select"]["name"] if props.get("Tags") and props["Tags"]["select"] else None
        locs = [r["id"] for r in props["Location"]["relation"]] if props.get("Location") and props["Location"]["relation"] else []

        # SN — CAMBIO: leer SN si existe
        try:
            sn = props["SN"]["rich_text"][0]["text"]["content"] if props.get("SN") and props["SN"]["rich_text"] else ""
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
        name = props["Name"]["title"][0]["text"]["content"]
        ed = props["End Date"]["date"]["start"] if props.get("End Date") and props["End Date"]["date"] else None
        out.append({"id": p["id"], "name": name, "start": sd, "end": ed})
    return out

@st.cache_data(show_spinner=False)
def load_inhouse():
    r = q(LOCATIONS_ID, {"filter": {"property": "Type", "select": {"equals": "In House"}}})
    out = []
    for p in r:
        try:
            nm = p["properties"]["Name"]["title"][0]["text"]["content"]
        except:
            nm = "Sin nombre"
        out.append({"id": p["id"], "name": nm})
    return out

def office_id():
    r = q(LOCATIONS_ID, {"filter": {"property": "Name", "title": {"equals": "Office"}}})
    return r[0]["id"] if r else None

def clear_all_cache():
    load_devices.clear()
    load_inhouse.clear()
    load_future_client_locations.clear()
    load_locations_map.clear()

# ---------------- UI HELP ----------------
def card(name, location_types=None, selected=False):
    color_map_bg = {"Office": "#D9E9DC", "In House": "#E1EDF8", "Client": "#F4ECDF"}
    color_map_badge = {"Office": "#4CAF50", "In House": "#1565C0", "Client": "#FF9800"}
    badge_letter_map = {"Office": "O", "In House": "H", "Client": "C"}

    bg = "#e0e0e0"
    badge_html = ""

    if location_types:
        first_type = location_types.split(" • ")[0]
        bg = color_map_bg.get(first_type, "#e0e0e0")
        badge_color = color_map_badge.get(first_type, "#B3E5E6")
        letter = badge_letter_map.get(first_type, "?")
        badge_html = f"<span style='float:right;width:20px;height:20px;line-height:20px;text-align:center;font-weight:bold;color:#fff;background:{badge_color};border-radius:4px;margin-left:8px'>{letter}</span>"

    if selected:
        bg = "#B3E5E6"

    st.markdown(
        f"""
        <div style='padding:7px;background:{bg};border-left:4px solid #9e9e9e;border-radius:6px;margin-bottom:4px;overflow:auto;'>
            <b>{name}</b> {badge_html}
            <div style='clear:both;'></div>
        </div>
        """,
        unsafe_allow_html=True
    )

def counter_badge(selected, total):
    if selected > 0:
        bg = "#B3E5E6"
        tc = "666"
    else:
        bg = "#e0e0e0"
        tc = "#666"
    st.markdown(
        f"<div style='background:{bg};color:{tc};padding:12px 16px;border-radius:8px;text-align:center;font-size:18px;font-weight:bold;margin-bottom:15px;box-shadow:0 2px 4px rgba(0,0,0,0.1);'>{selected} / {total} seleccionadas</div>",
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

# ---------------- SEGMENTED FILTER HELPER ----------------
def segmented_tag_filter(devices, tag_field="Tags", groups=None, key_prefix="seg"):
    # Infer tags present
    present_tags = sorted({(d.get(tag_field) or "") for d in devices if d.get(tag_field)})

    if groups is None:
        groups = present_tags

    # Build counts
    counts = {"Todas": len(devices)}
    for g in groups:
        counts[g] = sum(1 for d in devices if d.get(tag_field) == g)

    # Build display options
    opciones = {f"Todas ({counts['Todas']})": "Todas"}
    for g in groups:
        opciones[f"{g} ({counts[g]})"] = g

    # --- SEGMENTED CONTROL ---
    sel_label = st.segmented_control(
        label=None,
        options=list(opciones.keys()),
        default=list(opciones.keys())[0],
        key=f"{key_prefix}_seg"
    )

    # --- FIX 1: If stored key is invalid, reset to default ---
    if sel_label not in opciones:
        sel_label = list(opciones.keys())[0]  # fallback
        st.session_state[f"{key_prefix}_seg"] = sel_label

    selected_group = opciones[sel_label]

    # Filter devices
    if selected_group == "Todas":
        filtered = devices
    else:
        filtered = [d for d in devices if d.get(tag_field) == selected_group]

    return filtered, selected_group, counts, opciones


# ---------------- STATE ----------------
for key, default in [
    ("tab1_show", False), ("sel1", []), ("sel2", []),
    ("sel3", []), ("tab3_loc", None), ("show_avail_tab3", False), ("show_avail_home", False)
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ---------------- SIDEBAR NAV ----------------
# ===========================
# SIDEBAR NATIVO SEGMENTED CONTROL
# ===========================
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

    # =========================================================
    # Construcción NATIVA de etiquetas para segmented_control
    # =========================================================

    label_disponibles = "Disponibles para Alquilar"
    label_casa = "Gafas en casa"

    # 🟠 Se muestran solo si > 0
    label_proximos = (
        "Próximos Envíos"
        + ("  🟠" if num_proximos > 0 else "")     # ← Mostrar SOLO icono
        # + (f"  🟠{num_proximos}" if num_proximos > 0 else "")   # ← Mostrar icono + número
    )

    # 🟠 Check-In (solo icono)
    label_checkin = (
        "Check-In"
        + ("  🟠" if num_finished > 0 else "")    # ← Mostrar SOLO icono
        # + (f"  🟠{num_finished}" if num_finished > 0 else "")   # ← Mostrar icono + número
    )


    opciones_segmented = {
        label_disponibles: "Disponibles para Alquilar",
        label_casa: "Gafas en casa",
        label_proximos: "Próximos Envíos",
        label_checkin: "Check-In",
        "Incidencias": "Incidencias"
    }


    # ---------- CONTROL DE NAVEGACIÓN ----------
    menu_label = st.segmented_control(
        "Navegación",
        list(opciones_segmented.keys()),
        default=list(opciones_segmented.keys())[0]
    )

    # Guarda la opción REAL en session_state
    st.session_state.menu = opciones_segmented[menu_label]

    st.markdown("----")

    # ---------- REFRESCAR ----------
    if st.button("🔄 Refrescar"):
        clear_all_cache()
        st.rerun()


# ---------- Cargar mapa de localizaciones DESPUÉS del sidebar ----------
locations_map = load_locations_map()


# ---------------- TAB 1 ----------------
if st.session_state.menu == "Disponibles para Alquilar":
    st.title("Disponibles para Alquilar")

    with st.expander("📘 Leyenda de estados"):
        render_legend()

    c1, c2 = st.columns(2)
    with c1:
        start = st.date_input("Fecha inicio", date.today())
    with c2:
        end = st.date_input("Fecha fin", date.today())

    if st.button("Comprobar disponibilidad"):
        st.session_state.tab1_show = True
        st.session_state.sel1 = []

    if st.session_state.tab1_show:
        devices = load_devices()
        avail = [d for d in devices if d.get("location_ids") and available(d, start, end)]

        # FILTRO POR TIPO (reutilizable)
        groups = ["Ultra", "Neo 4", "Quest 2", "Quest 3"]
        avail_filtered, _, _, _ = segmented_tag_filter(avail, groups=groups, key_prefix="tab1")

        for d in avail_filtered:
            key = f"a_{d['id']}"
            subtitle = get_location_types_for_device(d, locations_map)
            cols = st.columns([0.5, 9.5])
            with cols[0]:
                st.checkbox("", key=key)
            with cols[1]:
                card(d["Name"], location_types=subtitle, selected=st.session_state.get(key, False))

        st.session_state.sel1 = [
            d["id"] for d in avail_filtered if st.session_state.get(f"a_{d['id']}", False)
        ]

        sel_count = len(st.session_state.sel1)

        with st.sidebar:
            counter_badge(sel_count, len(avail_filtered))
            if sel_count > 0:
                client = st.text_input("Nombre Cliente")
                if st.button("Asignar Cliente"):
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

                    for did in st.session_state.sel1:
                        assign_device(did, new)

                    st.success("Asignado correctamente")
                    clear_all_cache()
                    st.rerun()

# ---------------- TAB 2 ----------------
elif st.session_state.menu == "Gafas en casa":

    # Título principal de la página
    st.title("Gafas en casa")

    # Cargar dispositivos (solo una vez)
    if "devices_live" not in st.session_state:
        st.session_state.devices_live = load_devices()

    devices = st.session_state.devices_live
    inh = load_inhouse()
    oid = office_id()
    groups = ["Ultra", "Neo 4", "Quest 2", "Quest 3"]

    with st.expander("📘 Leyenda de estados"):
        render_legend()

    # ==========================================================
    # FILTRO GLOBAL: gafas en casa
    # ==========================================================
    inh_ids = [p["id"] for p in inh]
    inhouse_devices = [d for d in devices if any(l in inh_ids for l in d["location_ids"])]

    # Aplicar filtro por tipo (directo dentro del expander)
    # ==========================================================
    # Expander principal: PERSONAL CON DISPOSITIVOS EN CASA
    # ==========================================================
    with st.expander("Personal con dispositivos en casa", expanded=True):

        inhouse_filtered, _, _, _ = segmented_tag_filter(
            inhouse_devices, groups=groups, key_prefix="inhouse"
        )

        # Reconstruir personas → dispositivos filtrados
        people_devices = {p["id"]: [] for p in inh}
        for d in inhouse_filtered:
            for lid in d["location_ids"]:
                if lid in people_devices:
                    people_devices[lid].append(d)

        # Lista de personas con gafas filtradas
        people_with_devices = [p for p in inh if len(people_devices[p["id"]]) > 0]

        # Expanders por persona
        for person in people_with_devices:
            pid = person["id"]
            pname = person["name"]
            devs = people_devices.get(pid, [])

            with st.expander(f"{pname} ({len(devs)})"):
                for d in devs:
                    cols = st.columns([9.2, 0.8])
                    with cols[0]:
                        card(d["Name"], location_types="In House")
                    with cols[1]:
                        if st.button("✕", key=f"rm_{d['id']}"):
                            assign_device(d["id"], oid)

                            # REFRESCO COMPLETO
                            clear_all_cache()
                            st.session_state.devices_live = load_devices()
                            st.rerun()

    # ==========================================================
    # EXPANDER: Otras gafas disponibles en oficina
    # ==========================================================

    office_devices = [d for d in devices if oid in d["location_ids"]]

    with st.expander("Otras gafas disponibles en oficina", expanded=False):

        office_filtered, _, _, _ = segmented_tag_filter(
            office_devices, groups=groups, key_prefix="office"
        )

        # Render de lista filtrada
        for d in office_filtered:
            key = f"o_{d['id']}"
            subtitle = get_location_types_for_device(d, locations_map)
            cols = st.columns([0.5, 9.5])
            with cols[0]:
                st.checkbox("", key=key)
            with cols[1]:
                card(d["Name"], location_types=subtitle, selected=st.session_state.get(key, False))

        # Selección para asignar
        st.session_state.sel2 = [
            d["id"] for d in office_filtered if st.session_state.get(f"o_{d['id']}", False)
        ]
        sel_count = len(st.session_state.sel2)

        # Contador en sidebar
        with st.sidebar:
            counter_badge(sel_count, len(office_filtered))

            if sel_count > 0:
                dest = st.selectbox("Asignar a:", [x["name"] for x in inh])
                dest_id = next(x["id"] for x in inh if x["name"] == dest)

                if st.button("Asignar seleccionadas"):
                    for did in st.session_state.sel2:
                        assign_device(did, dest_id)

                    # REFRESCO COMPLETO
                    clear_all_cache()
                    st.session_state.devices_live = load_devices()

                    st.success("Asignación completada")
                    st.rerun()

# ---------------- TAB 3 ----------------
elif st.session_state.menu == "Próximos Envíos":
    st.title("Próximos Envíos")

    with st.expander("📘 Leyenda de estados"):
        render_legend()

    # =============================
    # NIVEL 1 — Expanders de Envíos
    # =============================
    future_locs = load_future_client_locations()

    with st.expander(f"📦 Envíos futuros ({len(future_locs)})", expanded=True):

        if len(future_locs) == 0:
            st.info("No hay envíos futuros.")
            st.stop()

        # Procesar cada envío futuro
        for loc in future_locs:

            lname = loc["name"]
            start = fmt(loc["start"])
            end = fmt(loc["end"])
            loc_id = loc["id"]

            devices = load_devices()
            groups = ["Ultra", "Neo 4", "Quest 2", "Quest 3"]

            # =============================
            # NIVEL 2 — Expander por envío
            # =============================
            with st.expander(f"{lname} ({start} → {end})", expanded=False):

                # ===================================
                # A) Gafas asignadas a este envío
                # ===================================
                assigned = [d for d in devices if loc_id in d["location_ids"]]

                st.subheader(f"📦 Gafas asignadas ")

                assigned_filtered, _, _, _ = segmented_tag_filter(
                    assigned, groups=groups, key_prefix=f"assigned_{loc_id}"
                )

                

                for d in assigned_filtered:
                    cols = st.columns([9, 1])
                    with cols[0]:
                        subtitle = get_location_types_for_device(d, locations_map)
                        card(d["Name"], location_types=subtitle)
                    with cols[1]:
                        if st.button("✕", key=f"rm_{loc_id}_{d['id']}"):
                            assign_device(d["id"], office_id())
                            clear_all_cache()
                            st.rerun()

                # ===================================
                # B) Expander de gafas disponibles
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

                    

                    # Render checkboxes
                    checkbox_keys = []
                    for d in can_add_filtered:
                        key = f"add_{loc_id}_{d['id']}"
                        checkbox_keys.append(key)
                        cols = st.columns([0.5, 9.5])
                        with cols[0]:
                            st.checkbox("", key=key)
                        with cols[1]:
                            subtitle = get_location_types_for_device(d, locations_map)
                            card(d["Name"], location_types=subtitle, selected=st.session_state.get(key, False))

                    # Obtener selección real
                    selected_ids = [
                        key.split("_")[-1]
                        for key in checkbox_keys
                        if st.session_state.get(key, False)
                    ]

                    sel_count = len(selected_ids)

                    # ===================================
                    # Sidebar — contador + botón
                    # ===================================
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

    finished = []
    for p in all_locs:
        props = p["properties"]

        if not props.get("Type") or not props["Type"].get("select") or props["Type"]["select"]["name"] != "Client":
            continue

        ed = props.get("End Date")["date"]["start"] if props.get("End Date") and props["End Date"].get("date") else None
        if not ed or iso_to_date(ed) >= today:
            continue

        loc_id = p["id"]
        assigned = [d for d in devices if loc_id in d["location_ids"]]
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

    options = ["Seleccionar..."] + [f"{x['name']} (fin {fmt(x['end'])})" for x in finished]
    sel = st.selectbox("Selecciona envío terminado:", options)

    if sel != "Seleccionar...":
        loc = finished[options.index(sel) - 1]

        st.write(f"📅 Finalizó el **{fmt(loc['end'])}**")

        assigned = [d for d in devices if loc["id"] in d["location_ids"]]
        office = office_id()

        with st.expander(f"📦 Gafas para recepcionar ({len(assigned)})", expanded=True):

            for d in assigned:
                cols = st.columns([9, 1])
                with cols[0]:
                    subtitle = get_location_types_for_device(d, locations_map)
                    card(d["Name"], location_types=subtitle)

                with cols[1]:
                    if st.button("📥", key=f"checkin_{d['id']}"):

                        payload = {
                            "parent": {"database_id": HISTORIC_ID},
                            "properties": {
                                "Name": {"title": [{"text": {"content": d['Name']}}]},
                                # Only include if not None
                                "Tags": {"select": {"name": d["Tags"]}} if d.get("Tags") else None,
                                "SN": {"rich_text": [{"text": {"content": d.get("SN", "")}}]},
                                "Location": {"relation": [{"id": loc["id"]}]},
                                "Start Date": {"date": {"start": d["Start"]}} if d.get("Start") else None,
                                "End Date": {"date": {"start": d["End"]}} if d.get("End") else None,
                                "Check In": {"date": {"start": date.today().isoformat()}}
                            }
                        }

                        # Remove None props
                        payload["properties"] = {k: v for k, v in payload["properties"].items() if v is not None}

                        r = requests.post("https://api.notion.com/v1/pages", headers=headers, json=payload)

                        if r.status_code != 200:
                            st.error(f"❌ Error al registrar en histórico ({r.status_code})")
                            st.code(r.text)
                            # Do not continue to move device if historic failed
                        else:
                            st.success("Registro añadido correctamente")
                            # Now move device to office
                            assign_device(d["id"], office)
                            # refresh caches and UI
                            clear_all_cache()
                            st.rerun()

# ---------------- TAB 5 — INCIDENCIAS ----------------
elif st.session_state.menu == "Incidencias":

    st.title("Incidencias de dispositivos")

    ACTIVE_INC_ID = "28c58a35e41180b8ae87fb11aec1f48e"
    PAST_INC_ID   = "28e58a35e41180f29199c42d33500566"

    # ---- Loaders ----

    @st.cache_data(show_spinner=False)
    def load_active_incidents():
        r = q(ACTIVE_INC_ID)
        out = []
        for p in r:
            props = p["properties"]

            try:
                name = props["Name"]["title"][0]["text"]["content"]
            except:
                name = "Sin nombre"

            # CAMPO REAL = "👓 Device"
            dev = None
            if "👓 Device" in props:
                rel = props["👓 Device"].get("relation", [])
                if rel:
                    dev = rel[0]["id"]

            created = props["Created Date"]["date"]["start"] if props.get("Created Date") else None

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

    @st.cache_data(show_spinner=False)
    def load_past_incidents():
        r = q(PAST_INC_ID)
        out = []
        for p in r:
            props = p["properties"]

            try:
                name = props["Name"]["title"][0]["text"]["content"]
            except:
                name = "Sin nombre"

            # CAMPO REAL = "👓 Device"
            dev = None
            if "👓 Device" in props:
                rel = props["👓 Device"].get("relation", [])
                if rel:
                    dev = rel[0]["id"]

            created = props["Created Date"]["date"]["start"] if props.get("Created Date") else None
            resolved = props["Resolved Date"]["date"]["start"] if props.get("Resolved Date") else None

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

    devices = load_devices()
    actives = load_active_incidents()
    pasts = load_past_incidents()

    # Build device → incidents
    device_map = {d["id"]: {"dev": d, "active": [], "past": []} for d in devices}

    for a in actives:
        if a["Device"] in device_map:
            device_map[a["Device"]]["active"].append(a)

    for p in pasts:
        if p["Device"] in device_map:
            device_map[p["Device"]]["past"].append(p)

    # Devices with at least 1 incident
    devices_with_inc = [
        v for v in device_map.values()
        if len(v["active"]) + len(v["past"]) > 0
    ]

    # ---------------- EXPANDER SUPERIOR ----------------
    with st.expander("🔧 Gafas con incidencias", expanded=True):

        for entry in devices_with_inc:

            dev = entry["dev"]
            active_list = entry["active"]
            past_list = entry["past"]

            active_count = len(active_list)
            past_count   = len(past_list)
            total = active_count + past_count

            # ----- Badge incidencias -----
            inc_html = ""
            if total > 0:
                bg = "#E53935" if active_count > 0 else "#9E9E9E"
                inc_html = (
                    f"<span style='display:inline-block;padding:2px 8px;"
                    f"background:{bg};color:white;border-radius:6px;font-size:12px;"
                    f"font-weight:bold;margin-left:8px;'>{active_count}/{past_count}</span>"
                )

            title_html = f"{dev['Name']} {inc_html}"

            with st.expander(title_html, expanded=False):

                # Ordenar
                active_sorted = sorted(active_list, key=lambda x: x["Created"] or "", reverse=True)
                past_sorted   = sorted(past_list,   key=lambda x: x["Created"] or "", reverse=True)

                # ---- ACTIVAS ----
                st.subheader(" Incidencias activas")

                if len(active_sorted) == 0:
                    st.info("No hay incidencias activas")
                else:
                    for inc in active_sorted:
                        cols = st.columns([8, 2])
                        with cols[0]:
                            st.write(f"**{inc['🟥 Name']}** — {fmt(inc['Created'])}")
                            if inc["Notes"]:
                                st.caption(inc["Notes"])
                        with cols[1]:
                            if st.button("Resolver", key=f"solve_{inc['id']}"):
                                st.session_state.solve_inc = inc

                if len(past_sorted) == 0:
                    st.info("No hay incidencias pasadas")
                else:
                    for inc in past_sorted:
                        st.write(
                            f"**{inc['⚪ Name']}** — {fmt(inc['Created'])} → {fmt(inc['Resolved'])}"
                        )
                        if inc["Notes"]:
                            st.caption(inc["Notes"])

    # ---------------- SIDEBAR: Resolver incidencia ----------------
    if "solve_inc" in st.session_state and st.session_state.solve_inc:
        inc = st.session_state.solve_inc

        with st.sidebar:
            st.markdown("### Resolver incidencia")

            resolved_date = st.date_input("Fecha de resolución", value=date.today())
            rnotes = st.text_area("Comentarios de resolución")

            if st.button("Confirmar resolución"):

                payload = {
                    "parent": {"database_id": PAST_INC_ID},
                    "properties": {
                        "Name": {"title": [{"text": {"content": inc["Name"]}}]},
                        "👓 Device": {"relation": [{"id": inc["Device"]}]},
                        "Created Date": {"date": {"start": inc["Created"]}},
                        "Notes": {"rich_text": [{"text": {"content": inc["Notes"]}}]},
                        "Resolved Date": {"date": {"start": resolved_date.isoformat()}},
                        "Resolution Notes": {"rich_text": [{"text": {"content": rnotes}}]},
                    }
                }

                requests.post("https://api.notion.com/v1/pages", headers=headers, json=payload)

                # Borrar la incidencia activa
                requests.delete(f"https://api.notion.com/v1/blocks/{inc['id']}", headers=headers)

                st.success("Incidencia resuelta")
                st.session_state.solve_inc = None
                clear_all_cache()
                st.rerun()

    # ---------------- EXPANDER: Añadir nueva incidencia ----------------
    with st.expander("➕ Añadir nueva incidencia", expanded=False):

        groups = ["Ultra", "Neo 4", "Quest 2", "Quest 3"]
        devices_filtered, _, _, _ = segmented_tag_filter(devices, groups=groups, key_prefix="new_inc")

        sel_keys = []
        for d in devices_filtered:
            key = f"newinc_{d['id']}"
            sel_keys.append(key)

            cols = st.columns([0.5, 9.5])
            with cols[0]:
                st.checkbox("", key=key)
            with cols[1]:
                subtitle = get_location_types_for_device(d, locations_map)
                card(d["Name"], location_types=subtitle)

        selected = [dk.split("_")[1] for dk in sel_keys if st.session_state.get(dk, False)]

        with st.sidebar:
            if selected:
                st.markdown("### Nueva incidencia")
                name = st.text_input("Nombre incidencia")
                notes = st.text_area("Notas")

                if st.button("Crear incidencia"):
                    for did in selected:
                        payload = {
                            "parent": {"database_id": ACTIVE_INC_ID},
                            "properties": {
                                "Name": {"title": [{"text": {"content": name}}]},
                                "👓 Device": {"relation": [{"id": did}]},
                                "Notes": {"rich_text": [{"text": {"content": notes}}]},
                                "Created Date": {"date": {"start": date.today().isoformat()}}
                            }
                        }

                        requests.post("https://api.notion.com/v1/pages", headers=headers, json=payload)

                    st.success("Incidencia creada")
                    clear_all_cache()
                    st.rerun()
