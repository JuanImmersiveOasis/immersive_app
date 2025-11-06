import streamlit as st
import requests
from datetime import datetime, date
import os
from dotenv import load_dotenv
load_dotenv()

# ---------------- CONFIG ----------------
st.set_page_config(page_title="Logistica", page_icon="img/icono.png", layout="wide")

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
    return requests.post(
        f"https://api.notion.com/v1/databases/{db}/query",
        json=payload, headers=headers
    ).json().get("results", [])

def patch(page_id, data):
    requests.patch(f"https://api.notion.com/v1/pages/{page_id}", json=data, headers=headers)

def create_page(data):
    return requests.post("https://api.notion.com/v1/pages", json=data, headers=headers)


def parse_device(p):
    props = p["properties"]
    name = props["Name"]["title"][0]["text"]["content"] if props["Name"]["title"] else "Sin nombre"
    locs = [r["id"] for r in props["Location"]["relation"]]
    try:
        tag = props["Tags"]["select"]["name"]
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
        "id": p["id"],
        "Name": name,
        "Tags": tag,
        "location_ids": locs,
        "Start": roll("Start Date"),
        "End": roll("End Date")
    }

def load_devices():
    return sorted([parse_device(p) for p in q(DEVICES_ID)], key=lambda x: x["Name"])

def d(x):
    try: return datetime.fromisoformat(x).date()
    except: return None

def available(dev, start, end):
    ds, de = d(dev["Start"]), d(dev["End"])
    if not ds and not de: return True
    if ds and de: return not (start <= de and end >= ds)
    if ds and not de: return end < ds
    if de and not ds: return start > de
    return True


def office_id():
    r = q(LOCATIONS_ID, {"filter": {"property": "Name", "title": {"equals": "Office"}}})
    return r[0]["id"] if r else None

def in_house():
    r = q(LOCATIONS_ID, {"filter": {"property": "Type", "select": {"equals": "In House"}}})
    return [{"id": p["id"], "name": p["properties"]["Name"]["title"][0]["text"]["content"]} for p in r]

def client_future():
    r = q(LOCATIONS_ID, {
        "filter": {
            "and": [
                {"property": "Type", "select": {"equals": "Client"}},
                {"property": "Start Date", "date": {"after": date.today().isoformat()}}
            ]
        }
    })
    return [{
        "id": p["id"],
        "name": p["properties"]["Name"]["title"][0]["text"]["content"],
        "start": p["properties"]["Start Date"]["date"]["start"],
        "end": p["properties"]["End Date"]["date"]["start"] if p["properties"]["End Date"]["date"] else None
    } for p in r]


def assign(dev, loc):
    patch(dev, {"properties": {"Location": {"relation": [{"id": loc}]}}})

# ---------------- STATE ----------------
if "sel" not in st.session_state: st.session_state.sel = []
if "devices" not in st.session_state: st.session_state.devices = load_devices()
if "show_results" not in st.session_state: st.session_state.show_results = False

# ---------------- SIDEBAR ----------------
with st.sidebar:
    menu = st.radio("Navegación", ["Disponibles para Alquilar", "Gafas para Equipo", "Próximos Envíos"])

    st.markdown("---")

# Refresh list on tab change
if "last" not in st.session_state: st.session_state.last = menu
if menu != st.session_state.last:
    st.session_state.sel = []
    st.session_state.show_results = False
    st.session_state.last = menu
    st.rerun()

devices = st.session_state.devices

def card(name, selected):
    bg = "#B3E5E6" if selected else "#e0e0e0"
    border = "#00859B" if selected else "#9e9e9e"
    st.markdown(f"<div style='padding:8px;background:{bg};border-left:4px solid {border};border-radius:6px;margin-bottom:6px;'><b>{name}</b></div>", unsafe_allow_html=True)

# ---------------- TAB 1 ----------------
if menu == "Disponibles para Alquilar":
    st.subheader("🔍 Disponibles para Alquilar")

    col1, col2 = st.columns(2)
    with col1: start = st.date_input("Fecha inicio", date.today())
    with col2: end = st.date_input("Fecha fin", date.today())

    if st.button("Comprobar disponibilidad"):
        st.session_state.show_results = True
        st.session_state.devices = load_devices()
        st.session_state.sel = []
        st.rerun()

    if st.session_state.show_results:

        avail = [d for d in devices if available(d, start, end)]

        tags = ["Todos"] + sorted({d["Tags"] for d in avail if d["Tags"]})
        ftag = st.selectbox("Filtrar por tipo", tags)
        if ftag != "Todos":
            avail = [d for d in avail if d["Tags"] == ftag]

        st.markdown(f"<div style='padding:6px;background:#C6F6C6;border-radius:6px;display:inline-block;font-weight:bold;'> {len(avail)} disponibles </div>", unsafe_allow_html=True)

        for d in avail:
            cols = st.columns([0.5, 9.5])
            with cols[0]:
                c = st.checkbox("", key=f"a_{d['id']}")
                if c and d["Name"] not in st.session_state.sel: st.session_state.sel.append(d["Name"])
                if not c and d["Name"] in st.session_state.sel: st.session_state.sel.remove(d["Name"])
            with cols[1]:
                card(d["Name"], c)

        # Sidebar form
        with st.sidebar:
            if st.session_state.sel:
                st.markdown("### Asignar a Cliente")
                name = st.text_input("Nombre Cliente")
                if st.button("Asignar Cliente"):
                    new = create_page({
                        "parent": {"database_id": LOCATIONS_ID},
                        "properties": {
                            "Name": {"title": [{"text": {"content": name}}]},
                            "Type": {"select": {"name": "Client"}},
                            "Start Date": {"date": {"start": start.isoformat()}},
                            "End Date": {"date": {"start": end.isoformat()}}
                        }
                    }).json()["id"]
                    for nm in st.session_state.sel:
                        assign(next(x["id"] for x in devices if x["Name"] == nm), new)
                    st.session_state.sel = []
                    st.session_state.devices = load_devices()
                    st.rerun()

# ---------------- TAB 2 ----------------
elif menu == "Gafas para Equipo":
    st.subheader("🏢 Gafas para Equipo")

    oid = office_id()
    office_devices = [d for d in devices if oid in d["location_ids"]]

    tags = ["Todos"] + sorted({d["Tags"] for d in office_devices if d["Tags"]})
    ftag = st.selectbox("Filtrar por tipo", tags)
    if ftag != "Todos":
        office_devices = [d for d in office_devices if d["Tags"] == ftag]

    st.markdown(f"<div style='padding:6px;background:#C6F6C6;border-radius:6px;display:inline-block;font-weight:bold;'> {len(office_devices)} en Office </div>", unsafe_allow_html=True)

    selected_ids = []
    for d in office_devices:
        cols = st.columns([0.5, 9.5])
        with cols[0]:
            c = st.checkbox("", key=f"o_{d['id']}")
            if c: selected_ids.append(d["id"])
        with cols[1]:
            card(d["Name"], c)

    with st.sidebar:
        if selected_ids:
            st.markdown("### Mover a In House")
            dests = in_house()
            dest_name = st.selectbox("Destino:", [x["name"] for x in dests])
            dest_id = next(x["id"] for x in dests if x["name"] == dest_name)
            if st.button("Mover"):
                for did in selected_ids:
                    assign(did, dest_id)
                st.session_state.devices = load_devices()
                st.rerun()

# ---------------- TAB 3 ----------------
else:
    st.subheader("📦 Próximos Envíos")
    locs = client_future()
    if not locs:
        st.info("No hay envíos futuros")
    else:
        sel = st.selectbox("Selecciona envío:", [x["name"] for x in locs])
        loc = next(x for x in locs if x["name"] == sel)
        loc_id = loc["id"]

        st.write(f"Inicio: {loc['start']} — Fin: {loc['end']}")
        st.markdown("---")

        assigned = [d for d in devices if loc_id in d["location_ids"]]
        st.write("Asignadas:")
        for d in assigned:
            if st.button(f"Quitar {d['Name']}", key=f"r_{d['id']}"):
                assign(d["id"], office_id())
                st.session_state.devices = load_devices()
                st.rerun()
            card(d["Name"], False)

        st.markdown("---")
        st.write("Añadir:")

        ls, le = d(loc["start"]), d(loc["end"])
        can_add = [d for d in devices if available(d, ls, le) and loc_id not in d["location_ids"]]

        tags = ["Todos"] + sorted({d["Tags"] for d in can_add if d["Tags"]})
        ftag = st.selectbox("Filtrar por tipo", tags)
        if ftag != "Todos":
            can_add = [d for d in can_add if d["Tags"] == ftag]

        add_sel = []
        for d in can_add:
            cols = st.columns([0.5, 9.5])
            with cols[0]:
                if st.checkbox("", key=f"add_{d['id']}"): add_sel.append(d)
            with cols[1]:
                card(d["Name"], False)

        if add_sel and st.button("Añadir seleccionadas"):
            for d in add_sel:
                assign(d["id"], loc_id)
            st.session_state.devices = load_devices()
            st.rerun()
