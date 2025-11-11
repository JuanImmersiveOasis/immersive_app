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
    if payload is None:
        payload = {"page_size": 200}
    r = requests.post(f"https://api.notion.com/v1/databases/{db}/query", json=payload, headers=headers)
    return r.json().get("results", [])

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
    requests.patch(f"https://api.notion.com/v1/pages/{dev_id}", json={
        "properties": {"Location": {"relation": [{"id": loc_id}]}}
    }, headers=headers)

# ---------------- CACHED LOADERS ----------------
@st.cache_data(show_spinner=False)
def load_devices():
    results = q(DEVICES_ID)
    out = []
    for p in results:
        props = p["properties"]
        name = props["Name"]["title"][0]["text"]["content"] if props["Name"]["title"] else "Sin nombre"
        locs = [r["id"] for r in props["Location"]["relation"]]

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

        out.append({
            "id": p["id"],
            "Name": name,
            "location_ids": locs,
            "Start": roll("Start Date"),
            "End": roll("End Date")
        })

    return sorted(out, key=lambda x: x["Name"])

@st.cache_data(show_spinner=False)
def load_locations_map():
    results = q(LOCATIONS_ID)
    out = {}
    for p in results:
        props = p["properties"]
        loc_name = props["Name"]["title"][0]["text"]["content"]
        loc_type = props["Type"]["select"]["name"] if props["Type"]["select"] else "Sin Tipo"
        out[p["id"]] = {"name": loc_name, "type": loc_type}
    return out

@st.cache_data(show_spinner=False)
def load_future_client_locations():
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
    r = q(LOCATIONS_ID, {"filter": {"property": "Type", "select": {"equals": "In House"}}})
    return [{"id": p["id"], "name": p["properties"]["Name"]["title"][0]["text"]["content"]} for p in r]

def office_id():
    r = q(LOCATIONS_ID, {"filter": {"property": "Name", "title": {"equals": "Office"}}})
    return r[0]["id"] if r else None

def clear_all_cache():
    load_devices.clear()
    load_inhouse.clear()
    load_future_client_locations.clear()
    load_locations_map.clear()

# ---------------- UI HELP ----------------
def card(name, loc_type=None, selected=False):
    bg = "#B3E5E6" if selected else "#e0e0e0"
    border = "#00859B" if selected else "#9e9e9e"
    t = f"<span style='font-size:12px;color:#555;margin-left:8px;'>({loc_type})</span>" if loc_type else ""
    st.markdown(
        f"<div style='padding:7px;background:{bg};border-left:4px solid {border};border-radius:6px;margin-bottom:4px;'><b>{name}</b>{t}</div>",
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

# ---------------- STATE ----------------
for key, default in [("tab1_show", False), ("sel1", []), ("sel2", []), ("sel3", []), ("tab3_loc", None), ("show_avail_tab3", False)]:
    if key not in st.session_state:
        st.session_state[key] = default

# ---------------- SIDEBAR NAV ----------------
with st.sidebar:
    menu = st.radio("Navegación", ["Disponibles para Alquilar", "Gafas para Equipo", "Próximos Envíos"])
    st.markdown("----")

    st.markdown("""
        <style>
        .refresh-fixed-sidebar {
            position: fixed;
            left: 20px;
            bottom: 20px;
            z-index: 9999;
            width: 180px;
        }
        </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="refresh-fixed-sidebar">', unsafe_allow_html=True)
    if st.button("🔄 Refrescar", key="refresh_cache_fixed", use_container_width=True):
        clear_all_cache()
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# ---------------- TAB 1 ----------------
if menu == "Disponibles para Alquilar":
    st.title("Disponibles para Alquilar")
    d1, d2 = st.columns(2)
    with d1: start = st.date_input("Fecha inicio", date.today())
    with d2: end = st.date_input("Fecha fin", date.today())

    if st.button("Comprobar disponibilidad"):
        st.session_state.tab1_show = True
        st.session_state.sel1 = []

    if st.session_state.tab1_show:
        devices = load_devices()
        loc_map = load_locations_map()

        # ✅ Solo dispositivos con location asignada
        avail = [
            d for d in devices
            if d["location_ids"] and available(d, start, end)
        ]

        for d in avail:
            loc_type = loc_map[d["location_ids"][0]]["type"]
            key = f"a_{d['id']}"
            cols = st.columns([0.5, 9.5])
            with cols[0]: st.checkbox("", key=key)
            with cols[1]: card(d["Name"], loc_type, st.session_state.get(key, False))

        st.session_state.sel1 = [d["id"] for d in avail if st.session_state.get(f"a_{d['id']}", False)]
        sel_count = len(st.session_state.sel1)

        with st.sidebar:
            counter_badge(sel_count, len(avail))
            if sel_count > 0:
                client = st.text_input("Nombre Cliente")
                if st.button("Asignar Cliente"):
                    progress_bar = st.progress(0)
                    status_text = st.empty()
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

                    for idx, did in enumerate(st.session_state.sel1):
                        assign_device(did, new)
                        progress_bar.progress(0.2 + 0.8 * (idx + 1) / len(st.session_state.sel1))

                    status_text.empty()
                    st.success("✅ Proceso completado")
                    clear_all_cache()
                    st.rerun()

# ---------------- TAB 2 ----------------
elif menu == "Gafas para Equipo":
    st.title("Gafas para Equipo")
    devices = load_devices()
    oid = office_id()
    office_devices = [d for d in devices if oid in d["location_ids"]]

    loc_map = load_locations_map()

    for d in office_devices:
        loc_type = loc_map[d["location_ids"][0]]["type"]
        key = f"o_{d['id']}"
        cols = st.columns([0.5, 9.5])
        with cols[0]: st.checkbox("", key=key)
        with cols[1]: card(d["Name"], loc_type, st.session_state.get(key, False))

    st.session_state.sel2 = [d["id"] for d in office_devices if st.session_state.get(f"o_{d['id']}", False)]
    sel_count = len(st.session_state.sel2)

    with st.sidebar:
        counter_badge(sel_count, len(office_devices))
        if sel_count > 0:
            inh = load_inhouse()
            dest = st.selectbox("Asignar a:", [x["name"] for x in inh])
            dest_id = next(x["id"] for x in inh if x["name"] == dest)
            if st.button("Asignar seleccionadas"):
                progress_bar = st.progress(0)
                status_text = st.empty()
                for idx, did in enumerate(st.session_state.sel2):
                    assign_device(did, dest_id)
                    progress_bar.progress((idx + 1) / sel_count)
                status_text.empty()
                st.success("✅ Proceso completado")
                clear_all_cache()
                st.rerun()

# ---------------- TAB 3 ----------------
else:
    st.title("Próximos Envíos")
    locs = load_future_client_locations()
    options = ["Seleccionar..."] + [x["name"] for x in locs]
    sel = st.selectbox("Selecciona envío:", options)

    if sel != "Seleccionar...":
        loc = next(x for x in locs if x["name"] == sel)
        st.session_state.tab3_loc = loc["id"]

        st.write(f"📅 Inicio: **{loc['start']}** — Fin: **{loc['end']}**")

        devices = load_devices()
        assigned = [d for d in devices if loc["id"] in d["location_ids"]]

        with st.expander(f"📦 Gafas reservadas ({len(assigned)})", expanded=False):
            for d in assigned:
                cols = st.columns([9, 1])
                with cols[0]:
                    card(d["Name"], "Client")
                with cols[1]:
                    if st.button("✕", key=f"rm_{d['id']}"):
                        assign_device(d["id"], office_id())
                        clear_all_cache()
                        st.rerun()

            label = "Ocultar otras gafas disponibles" if st.session_state.get("show_avail_tab3") else "Mostrar otras gafas disponibles"
            if st.button(label, key="toggle_avail_tab3"):
                st.session_state.show_avail_tab3 = not st.session_state.get("show_avail_tab3", False)
                st.rerun()

            if st.session_state.show_avail_tab3:
                ls = iso_to_date(loc["start"])
                le = iso_to_date(loc["end"])
                can_add = [d for d in devices if available(d, ls, le) and loc["id"] not in d["location_ids"]]

                st.subheader("Reservar otras gafas")

                for d in can_add:
                    key = f"add_{d['id']}"
                    cols = st.columns([0.5, 9.5])
                    with cols[0]: st.checkbox("", key=key)
                    with cols[1]: card(d["Name"])

                st.session_state.sel3 = [d["id"] for d in can_add if st.session_state.get(f"add_{d['id']}", False)]

                if len(st.session_state.sel3) > 0:
                    if st.button("➕ Añadir seleccionadas", key="add_selected_tab3"):
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        for idx, did in enumerate(st.session_state.sel3):
                            assign_device(did, loc["id"])
                            progress_bar.progress((idx + 1) / len(st.session_state.sel3))
                        status_text.empty()
                        st.success("✅ Añadidas correctamente")
                        clear_all_cache()
                        st.rerun()
