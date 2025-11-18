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

def fmt(date_str):
    """Formatea fechas a dd/mm/yyyy"""
    try:
        dt = iso_to_date(date_str)
        return dt.strftime("%d/%m/%Y")
    except:
        return date_str

def q(db, payload=None):
    if payload is None:
        payload = {"page_size": 200}

    url = f"https://api.notion.com/v1/databases/{db}/query"
    results = []
    has_more = True
    next_cursor = None

    while has_more:
        if next_cursor:
            payload["start_cursor"] = next_cursor

        r = requests.post(url, json=payload, headers=headers).json()

        results.extend(r.get("results", []))

        has_more = r.get("has_more", False)
        next_cursor = r.get("next_cursor", None)

    return results


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
        tag = props["Tags"]["select"]["name"] if props["Tags"]["select"] else None
        locs = [r["id"] for r in props["Location"]["relation"]] if props["Location"]["relation"] else []

        # SN — CAMBIO NUEVO
        sn = props["SN"]["rich_text"][0]["text"]["content"] if props["SN"]["rich_text"] else ""

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
            "SN": sn,         # ← NUEVO
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
        sd = props["Start Date"]["date"]["start"] if props["Start Date"]["date"] else None
        if not sd or iso_to_date(sd) < today:
            continue
        name = props["Name"]["title"][0]["text"]["content"]
        ed = props["End Date"]["date"]["start"] if props["End Date"]["date"] else None
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

# ---------------- STATE ----------------
for key, default in [
    ("tab1_show", False), ("sel1", []), ("sel2", []),
    ("sel3", []), ("tab3_loc", None), ("show_avail_tab3", False)
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ---------------- SIDEBAR NAV ----------------
with st.sidebar:
    menu = st.radio("Navegación", [
        "Disponibles para Alquilar",
        "Gafas en casa",
        "Próximos Envíos",
        "Check-In"
    ])
    st.markdown("----")

    if st.button("🔄 Refrescar", key="refresh_cache"):
        clear_all_cache()
        st.rerun()

locations_map = load_locations_map()

# ---------------- TAB 1 ----------------
if menu == "Disponibles para Alquilar":
    st.title("Disponibles para Alquilar")

    with st.expander("📘 Leyenda de estados"):
        render_legend()

    c1, c2 = st.columns(2)
    with c1: start = st.date_input("Fecha inicio", date.today())
    with c2: end = st.date_input("Fecha fin", date.today())

    if st.button("Comprobar disponibilidad"):
        st.session_state.tab1_show = True
        st.session_state.sel1 = []

    if st.session_state.tab1_show:
        devices = load_devices()
        avail = [d for d in devices if d.get("location_ids") and available(d, start, end)]

        for d in avail:
            key = f"a_{d['id']}"
            subtitle = get_location_types_for_device(d, locations_map)
            cols = st.columns([0.5, 9.5])
            with cols[0]: st.checkbox("", key=key)
            with cols[1]: card(d["Name"], location_types=subtitle, selected=st.session_state.get(key, False))

        st.session_state.sel1 = [
            d["id"] for d in avail if st.session_state.get(f"a_{d['id']}", False)
        ]

        sel_count = len(st.session_state.sel1)

        with st.sidebar:
            counter_badge(sel_count, len(avail))
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
elif menu == "Gafas en casa":

    if "devices_live" not in st.session_state:
        st.session_state.devices_live = load_devices()

    devices = st.session_state.devices_live
    inh = load_inhouse()

    # ---- SUMATORIO TOTAL DE GAFAS EN CASA ----
    people_devices = {p["id"]: [] for p in inh}
    for dev in devices:
        for lid in dev["location_ids"]:
            if lid in people_devices:
                people_devices[lid].append(dev)

    total_equipo = sum(len(people_devices[p["id"]]) for p in inh)

    # Título con sumatorio
    st.title(f"Total de dispositivos en casa ({total_equipo})")

    with st.expander("📘 Leyenda de estados"):
        render_legend()

    oid = office_id()

    # Agrupar por persona
    people_devices = {p["id"]: [] for p in inh}
    for dev in devices:
        for lid in dev["location_ids"]:
            if lid in people_devices:
                people_devices[lid].append(dev)

    people_with_devices = [p for p in inh if len(people_devices[p["id"]]) > 0]

    st.markdown("## Personal con dispositivos en casa")

    for person in people_with_devices:
        pid = person["id"]
        pname = person["name"]
        devs = people_devices[pid]

        with st.expander(f"{pname} ({len(devs)})"):

            for d in devs:
                cols = st.columns([9.2, 0.8])
                with cols[0]:
                    card(d["Name"], location_types="In House")
                with cols[1]:
                    if st.button("✕", key=f"rm_{d['id']}"):
                        assign_device(d["id"], oid)
                        d["location_ids"] = [oid]
                        st.rerun()


    if st.button(
        "Ocultar otras gafas disponibles" if st.session_state.get("show_avail_home") else "Mostrar otras gafas disponibles",
        key="toggle_avail_home"
    ):
        st.session_state.show_avail_home = not st.session_state.get("show_avail_home")
        st.rerun()

    if st.session_state.get("show_avail_home", False):

        st.subheader("Otras gafas disponibles (en oficina)")

        # Dispositivos que realmente están en OFFICE
        office_devices = [d for d in devices if oid in d["location_ids"]]

        # ---- FILTRO POR TIPO (SEGMENTED CONTROL) ----

        # Contar por tipo
        count_total  = len(office_devices)
        count_ultra  = sum(1 for d in office_devices if d["Tags"] == "Ultra")
        count_neo4   = sum(1 for d in office_devices if d["Tags"] == "Neo 4")
        count_quest2 = sum(1 for d in office_devices if d["Tags"] == "Quest 2")
        count_quest3 = sum(1 for d in office_devices if d["Tags"] == "Quest 3")

        # Opciones mostradas en el segmented control
        opciones = {
            f"Todas ({count_total})":  "Todas",
            f"Ultra ({count_ultra})":  "Ultra",
            f"Neo 4 ({count_neo4})":   "Neo 4",
            f"Quest 2 ({count_quest2})": "Quest 2",
            f"Quest 3 ({count_quest3})": "Quest 3"
        }

        tipo_sel = st.segmented_control(
            label=None,
            options=list(opciones.keys()),
            default=list(opciones.keys())[0]
        )

        # ---- APLICAR FILTRO ----
        filtro = opciones[tipo_sel]

        if filtro == "Ultra":
            office_filtered = [d for d in office_devices if d["Tags"] == "Ultra"]
        elif filtro == "Neo 4":
            office_filtered = [d for d in office_devices if d["Tags"] == "Neo 4"]
        elif filtro == "Quest 2":
            office_filtered = [d for d in office_devices if d["Tags"] == "Quest 2"]
        elif filtro == "Quest 3":
            office_filtered = [d for d in office_devices if d["Tags"] == "Quest 3"]
        else:
            office_filtered = office_devices

        # ---- RENDER DEL LISTADO (YA FILTRADO) ----
        for d in office_filtered:
            key = f"o_{d['id']}"
            subtitle = get_location_types_for_device(d, locations_map)
            cols = st.columns([0.5, 9.5])
            with cols[0]:
                st.checkbox("", key=key)
            with cols[1]:
                card(d["Name"], location_types=subtitle, selected=st.session_state.get(key, False))

        # ---- ACTUALIZAR SELECCIÓN ----
        st.session_state.sel2 = [
            d["id"] for d in office_filtered if st.session_state.get(f"o_{d['id']}", False)
        ]
        sel_count = len(st.session_state.sel2)

        # ---- CONTADOR EN EL SIDEBAR ----
        with st.sidebar:
            counter_badge(sel_count, len(office_filtered))

            if sel_count > 0:
                dest = st.selectbox("Asignar a:", [x["name"] for x in inh])
                dest_id = next(x["id"] for x in inh if x["name"] == dest)

                if st.button("Asignar seleccionadas"):
                    for did in st.session_state.sel2:
                        assign_device(did, dest_id)
                        for d in devices:
                            if d["id"] == did:
                                d["location_ids"] = [dest_id]

                    st.success("Asignación completada")
                    st.session_state.sel2 = []
                    st.rerun()


# ---------------- TAB 4 — CHECK-IN ----------------
else:
    st.title("Check-In de Gafas (de vuelta a oficina)")

    today = date.today()
    all_locs = q(LOCATIONS_ID)
    devices = load_devices()

    finished = []
    for p in all_locs:
        props = p["properties"]

        if not props["Type"]["select"] or props["Type"]["select"]["name"] != "Client":
            continue

        ed = props["End Date"]["date"]["start"] if props["End Date"]["date"] else None
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

    options = ["Seleccionar..."] + [
        f"{x['name']} (fin {fmt(x['end'])})" for x in finished
    ]

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
                                "Tags": {"select": {"name": d["Tags"]}} if d["Tags"] else None,
                                "SN": {"rich_text": [{"text": {"content": d.get("SN", "")}}]},
                                "Location": {"relation": [{"id": loc["id"]}]},
                                "Start Date": {"date": {"start": d["Start"]}} if d["Start"] else None,
                                "End Date": {"date": {"start": d["End"]}} if d["End"] else None,
                                "Check In": {"date": {"start": date.today().isoformat()}}
                            }
                        }

                        payload["properties"] = {k:v for k,v in payload["properties"].items() if v}

                        r = requests.post(
                            "https://api.notion.com/v1/pages",
                            headers=headers,
                            json=payload
                        )

                        if r.status_code != 200:
                            st.error("❌ Error al registrar en histórico")
                            st.code(r.text)
                            st.stop()
                        else:
                            st.success("Registro añadido correctamente")

                        assign_device(d["id"], office)

                        clear_all_cache()
                        st.rerun()
