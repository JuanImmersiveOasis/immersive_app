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
    return requests.post(f"https://api.notion.com/v1/databases/{db}/query", json=payload, headers=headers).json().get("results", [])

def patch(page_id, data):
    return requests.patch(f"https://api.notion.com/v1/pages/{page_id}", json=data, headers=headers)

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

def iso_to_date(x):
    try: return datetime.fromisoformat(x).date()
    except: return None

def available(dev, start, end):
    ds, de = iso_to_date(dev["Start"]), iso_to_date(dev["End"])
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
    out=[]
    for p in r:
        try: n=p["properties"]["Name"]["title"][0]["text"]["content"]
        except: n="Sin nombre"
        out.append({"id":p["id"],"name":n})
    return out

def client_future():
    r = q(LOCATIONS_ID,{
        "filter":{"and":[
            {"property":"Type","select":{"equals":"Client"}},
            {"property":"Start Date","date":{"after":date.today().isoformat()}}
        ]}
    })
    out=[]
    for p in r:
        try:n=p["properties"]["Name"]["title"][0]["text"]["content"]
        except:n="Sin nombre"
        sd = p["properties"]["Start Date"]["date"]["start"]
        try: ed = p["properties"]["End Date"]["date"]["start"]
        except: ed=None
        out.append({"id":p["id"],"name":n,"start":sd,"end":ed})
    return out

def assign(dev, loc):
    patch(dev, {"properties":{"Location":{"relation":[{"id":loc}]}}})

# ---------------- STATE ----------------
if "devices" not in st.session_state: st.session_state.devices=load_devices()
if "sel_tab1" not in st.session_state: st.session_state.sel_tab1=[]
if "sel_tab2" not in st.session_state: st.session_state.sel_tab2=[]
if "sel_tab3" not in st.session_state: st.session_state.sel_tab3=[]
if "tab1_show" not in st.session_state: st.session_state.tab1_show=False
if "last_envio" not in st.session_state: st.session_state.last_envio=None

# ---------------- SIDEBAR ----------------
with st.sidebar:
    menu = st.radio("Navegación",["Disponibles para Alquilar","Gafas para Equipo","Próximos Envíos"])
    st.markdown("---")

# Reset on tab change
if "last" not in st.session_state: st.session_state.last=menu
if menu!=st.session_state.last:
    st.session_state.sel_tab1=[]
    st.session_state.sel_tab2=[]
    st.session_state.sel_tab3=[]
    st.session_state.tab1_show=False
    st.session_state.last_envio=None
    st.session_state.devices=load_devices()
    st.session_state.last=menu
    st.rerun()

devices = st.session_state.devices

# ---------------- CARD RENDER ----------------
def card(name, selected):
    bg = "#B3E5E6" if selected else "#e0e0e0"
    border = "#00859B" if selected else "#9e9e9e"
    return f"<div style='padding:8px;background:{bg};border-left:4px solid {border};border-radius:6px;margin-bottom:6px;'><b>{name}</b></div>"

# ---------------- TAB 1 ----------------
if menu=="Disponibles para Alquilar":
    st.title("Disponibles para Alquilar")
    col1,col2=st.columns(2)
    with col1: start=st.date_input("Fecha inicio",date.today())
    with col2: end=st.date_input("Fecha fin",date.today())

    if st.button("Comprobar disponibilidad"):
        st.session_state.tab1_show=True
        st.session_state.sel_tab1=[]
        st.session_state.devices=load_devices()
        st.rerun()

    if st.session_state.tab1_show:
        avail=[d for d in devices if available(d,start,end)]
        tags=["Todos"]+sorted({d["Tags"] for d in avail if d["Tags"]})
        f=st.selectbox("Filtrar por tipo",tags)
        if f!="Todos": avail=[d for d in avail if d["Tags"]==f]

        total=len(avail)
        sel=len(st.session_state.sel_tab1)

        with st.sidebar:
            bg="#e0e0e0" if sel==0 else "#B3E5E6"
            st.markdown(f"<div style='padding:8px;background:{bg};border-radius:6px;font-weight:bold;text-align:center;'>{sel} / {total} dispositivos</div>",unsafe_allow_html=True)
            st.markdown("---")
            if sel>0:
                st.markdown("#### Asignar a Cliente")
                name=st.text_input("Nombre Cliente")
                if st.button("Asignar Cliente"):
                    new=create_page({
                        "parent":{"database_id":LOCATIONS_ID},
                        "properties":{
                            "Name":{"title":[{"text":{"content":name}}]},
                            "Type":{"select":{"name":"Client"}},
                            "Start Date":{"date":{"start":start.isoformat()}},
                            "End Date":{"date":{"start":end.isoformat()}}
                        }
                    }).json()["id"]
                    for nm in st.session_state.sel_tab1:
                        assign(next(x["id"] for x in devices if x["Name"]==nm),new)
                    st.session_state.sel_tab1=[]
                    st.session_state.devices=load_devices()
                    st.rerun()

        for d in avail:
            k=f"a_{d['id']}"
            cols=st.columns([0.5,9.5])
            with cols[0]:
                c=st.checkbox("",key=k)
            with cols[1]:
                st.markdown(card(d["Name"],c),unsafe_allow_html=True)
            if c and d["Name"] not in st.session_state.sel_tab1: st.session_state.sel_tab1.append(d["Name"])
            if not c and d["Name"] in st.session_state.sel_tab1: st.session_state.sel_tab1.remove(d["Name"])

# ---------------- TAB 2 ----------------
elif menu=="Gafas para Equipo":
    st.title("Gafas para Equipo")
    oid=office_id()
    office=[d for d in devices if oid in d["location_ids"]]

    tags=["Todos"]+sorted({d["Tags"] for d in office if d["Tags"]})
    f=st.selectbox("Filtrar por tipo",tags)
    if f!="Todos": office=[d for d in office if d["Tags"]==f]

    total=len(office)
    sel=len(st.session_state.sel_tab2)

    with st.sidebar:
        bg="#e0e0e0" if sel==0 else "#B3E5E6"
        st.markdown(f"<div style='padding:8px;background:{bg};border-radius:6px;font-weight:bold;text-align:center;'>{sel} / {total} dispositivos</div>",unsafe_allow_html=True)
        st.markdown("---")
        if sel>0:
            st.markdown("#### Mover a In House")
            inh=in_house()
            dest=st.selectbox("Destino:",[x["name"] for x in inh])
            if st.button("Mover"):
                did=next(x["id"] for x in inh if x["name"]==dest)
                for i in st.session_state.sel_tab2: assign(i,did)
                st.session_state.sel_tab2=[]
                st.session_state.devices=load_devices()
                st.rerun()

    for d in office:
        k=f"o_{d['id']}"
        cols=st.columns([0.5,9.5])
        with cols[0]: c=st.checkbox("",key=k)
        with cols[1]: st.markdown(card(d["Name"],c),unsafe_allow_html=True)
        if c and d["id"] not in st.session_state.sel_tab2: st.session_state.sel_tab2.append(d["id"])
        if not c and d["id"] in st.session_state.sel_tab2: st.session_state.sel_tab2.remove(d["id"])

# ---------------- TAB 3 ----------------
else:
    st.title("Próximos Envíos")
    locs=client_future()
    if not locs: st.info("No hay envíos futuros")
    else:
        sel_loc=st.selectbox("Selecciona envío:",[x["name"] for x in locs])
        loc=next(x for x in locs if x["name"]==sel_loc)
        loc_id=loc["id"]

        if st.session_state.last_envio!=loc_id:
            st.session_state.last_envio=loc_id
            st.session_state.sel_tab3=[]
            st.session_state.devices=load_devices()

        st.write(f"Inicio: {loc['start']} — Fin: {loc['end']}")
        st.markdown("---")

        assigned=[d for d in devices if loc_id in d["location_ids"]]
        st.subheader("Asignadas:")
        for d in assigned:
            cols=st.columns([9,1])
            with cols[0]: st.markdown(card(d["Name"],False),unsafe_allow_html=True)
            with cols[1]:
                if st.button("✕",key=f"x_{d['id']}",help="Quitar",use_container_width=True):
                    assign(d["id"],office_id())
                    st.session_state.devices=load_devices()
                    st.rerun()

        st.markdown("---")
        st.subheader("Añadir disponibles:")
        ls,le=iso_to_date(loc["start"]),iso_to_date(loc["end"])
        can=[d for d in devices if available(d,ls,le) and loc_id not in d["location_ids"]]

        tags=["Todos"]+sorted({d["Tags"] for d in can if d["Tags"]})
        f=st.selectbox("Filtrar por tipo",tags)
        if f!="Todos": can=[d for d in can if d["Tags"]==f]

        total=len(can)
        sel=len(st.session_state.sel_tab3)

        with st.sidebar:
            bg="#e0e0e0" if sel==0 else "#B3E5E6"
            st.markdown(f"<div style='padding:8px;background:{bg};border-radius:6px;font-weight:bold;text-align:center;'>{sel} / {total} dispositivos</div>",unsafe_allow_html=True)
            st.markdown("---")
            if sel>0:
                if st.button("Añadir seleccionadas"):
                    for did in st.session_state.sel_tab3: assign(did,loc_id)
                    st.session_state.sel_tab3=[]
                    st.session_state.devices=load_devices()
                    st.rerun()

        for d in can:
            k=f"c_{d['id']}"
            cols=st.columns([0.5,9.5])
            with cols[0]: c=st.checkbox("",key=k)
            with cols[1]: st.markdown(card(d["Name"],c),unsafe_allow_html=True)
            if c and d["id"] not in st.session_state.sel_tab3: st.session_state.sel_tab3.append(d["id"])
            if not c and d["id"] in st.session_state.sel_tab3: st.session_state.sel_tab3.remove(d["id"])
