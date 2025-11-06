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
        tag = props["Tags"]["select"]["name"] if props["Tags"]["select"] else None

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
            "Tags": tag,
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


# ---------------- UI HELP ----------------
def card(name, selected=False):
    bg = "#B3E5E6" if selected else "#e0e0e0"
    border = "#00859B" if selected else "#9e9e9e"
    st.markdown(
        f"<div style='padding:7px;background:{bg};border-left:4px solid {border};border-radius:6px;margin-bottom:4px;'><b>{name}</b></div>",
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


# ---------------- TAB 1 ----------------
if menu == "Disponibles para Alquilar":
    st.title("Disponibles para Alquilar")
    d1, d2 = st.columns(2)
    with d1:
        start = st.date_input("Fecha inicio", date.today())
    with d2:
        end = st.date_input("Fecha fin", date.today())

    if st.button("Comprobar disponibilidad"):
        st.session_state.tab1_show = True
        st.session_state.sel1 = []

    if st.session_state.tab1_show:
        devices = load_devices()
        avail = [d for d in devices if available(d, start, end)]

        for d in avail:
            key = f"a_{d['id']}"
            cols = st.columns([0.5, 9.5])
            with cols[0]:
                st.checkbox("", key=key)
            with cols[1]:
                card(d["Name"], st.session_state.get(key, False))

        st.session_state.sel1 = [d["id"] for d in avail if st.session_state.get(f"a_{d['id']}", False)]
        sel_count = len(st.session_state.sel1)

        with st.sidebar:
            st.markdown(f"### {sel_count} / {len(avail)} seleccionados")

            if sel_count > 0:
                client = st.text_input("Nombre Cliente")
                if st.button("Asignar Cliente"):
                    new = requests.post("https://api.notion.com/v1/pages", headers=headers, json={
                        "parent": {"database_id": LOCATIONS_ID},
                        "properties": {
                            "Name": {"title": [{"text": {"content": client}}]},
                            "Type": {"select": {"name": "Client"}},
                            "Start Date": {"date": {"start": start.isoformat()}},
                            "End Date": {"date": {"start": end.isoformat()}}
                        }
                    }).json()["id"]

                    for did in st.session_state.sel1:
                        assign_device(did, new)

                    clear_all_cache()
                    st.rerun()


# ---------------- TAB 2 ----------------
elif menu == "Gafas para Equipo":
    st.title("Gafas para Equipo")
    devices = load_devices()
    oid = office_id()
    office_devices = [d for d in devices if oid in d["location_ids"]]

    for d in office_devices:
        key = f"o_{d['id']}"
        cols = st.columns([0.5, 9.5])
        with cols[0]:
            st.checkbox("", key=key)
        with cols[1]:
            card(d["Name"], st.session_state.get(key, False))

    st.session_state.sel2 = [d["id"] for d in office_devices if st.session_state.get(f"o_{d['id']}", False)]
    sel_count = len(st.session_state.sel2)

    with st.sidebar:
        st.markdown(f"### {sel_count} / {len(office_devices)} seleccionados")
        if sel_count > 0:
            inh = load_inhouse()
            dest = st.selectbox("Mover a:", [x["name"] for x in inh])
            dest_id = next(x["id"] for x in inh if x["name"] == dest)
            if st.button("Mover seleccionadas"):
                for did in st.session_state.sel2:
                    assign_device(did, dest_id)
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
        st.markdown("---")

        devices = load_devices()
        assigned = [d for d in devices if loc["id"] in d["location_ids"]]

        with st.expander(f"📦 Dispositivos asignados ({len(assigned)})", expanded=False):
            for d in assigned:
                cols = st.columns([9, 1])
                with cols[0]:
                    card(d["Name"])
                with cols[1]:
                    if st.button("✕", key=f"rm_{d['id']}"):
                        assign_device(d["id"], office_id())
                        clear_all_cache()
                        st.rerun()

        if st.button("Buscar disponibles"):
            st.session_state.show_avail_tab3 = True
            st.rerun()

        if st.session_state.show_avail_tab3:
            ls = iso_to_date(loc["start"])
            le = iso_to_date(loc["end"])
            can_add = [d for d in devices if available(d, ls, le) and loc["id"] not in d["location_ids"]]

            for d in can_add:
                key = f"add_{d['id']}"
                cols = st.columns([0.5, 9.5])
                with cols[0]:
                    st.checkbox("", key=key)
                with cols[1]:
                    card(d["Name"], st.session_state.get(key, False))

            st.session_state.sel3 = [d["id"] for d in can_add if st.session_state.get(f"add_{d['id']}", False)]

            with st.sidebar:
                st.markdown(f"### {len(st.session_state.sel3)} / {len(can_add)} seleccionados")
                if len(st.session_state.sel3) > 0:
                    if st.button("Añadir seleccionadas"):
                        for did in st.session_state.sel3:
                            assign_device(did, loc["id"])
                        clear_all_cache()
                        st.rerun()


# ---------------- GLOBAL FIXED REFRESH BUTTON ----------------
st.markdown(
    """
    <div style="position:fixed; bottom:12px; left:12px;">
        <form action="#" method="post">
            <button style="padding:8px 14px;background:#444;color:white;border:none;border-radius:6px;"
             onclick="window.location.reload();">🔄 Refrescar</button>
        </form>
    </div>
    """,
    unsafe_allow_html=True
)
