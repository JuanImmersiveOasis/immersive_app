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

def render_legend():
    st.markdown(
        """
        <div style='margin-bottom:10px;'>
            <span style='display:inline-block;width:20px;height:20px;line-height:20px;text-align:center;
                         font-weight:bold;color:#fff;background:#4CAF50;border-radius:4px;margin-right:6px'>O</span>
            Office: Las gafas se encuentran DISPONIBLES en oficina<br>
            <span style='display:inline-block;width:20px;height:20px;line-height:20px;text-align:center;
                         font-weight:bold;color:#fff;background:#FF9800;border-radius:4px;margin-right:6px'>C</span>
            Client: Las gafas se encuentran RESERVADAS en oficina, asignadas a un proyecto en otras fechas.<br>
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
    """
    Devuelve un diccionario id -> {"name": ..., "type": ...}
    """
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
        locs = [r["id"] for r in props["Location"]["relation"]] if props["Location"]["relation"] else []
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
    """
    Tarjeta con nombre y badge de tipo de location a la derecha.
    Fondo según tipo:
      - Office: verde claro
      - In House: azul claro
      - Client: naranja claro
    Seleccionado → gris, pero badge mantiene color
    """
    # Colores de fondo de card
    color_map_bg = {
        "Office": "#D9E9DC",    # verde claro
        "In House": "#E1EDF8",  # azul claro
        "Client": "#F4ECDF",    # naranja claro
    }
    # Colores del badge
    color_map_badge = {
        "Office": "#4CAF50",    # verde oscuro
        "In House": "#1565C0",  # azul oscuro
        "Client": "#FF9800",    # naranja oscuro
    }
    # Mapear letra para el badge
    badge_letter_map = {
        "Office": "O",
        "In House": "H",
        "Client": "C"
    }

    # Fondo de la card
    bg = "#e0e0e0"
    badge_html = ""
    if location_types:
        first_type = location_types.split(" • ")[0]
        bg = color_map_bg.get(first_type, "#e0e0e0")
        badge_color = color_map_badge.get(first_type, "#B3E5E6")
        letter = badge_letter_map.get(first_type, "?")
        # Badge a la derecha del card
        badge_html = f"<span style='float:right;width:20px;height:20px;line-height:20px;" \
                     f"text-align:center;font-weight:bold;color:#fff;background:{badge_color};" \
                     f"border-radius:4px;margin-left:8px'>{letter}</span>"

    if selected:
        bg = "#B3E5E6"  # fondo gris si está seleccionado

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

# ---------------- AUX ----------------
def get_location_types_for_device(dev, loc_map):
    types = []
    for lid in dev.get("location_ids", []):
        entry = loc_map.get(lid)
        if entry and entry.get("type"):
            types.append(entry["type"])
    seen = set()
    uniq = []
    for t in types:
        if t not in seen:
            uniq.append(t)
            seen.add(t)
    return " • ".join(uniq) if uniq else None

# ---------------- STATE ----------------
for key, default in [("tab1_show", False), ("sel1", []), ("sel2", []), ("sel3", []), ("tab3_loc", None), ("show_avail_tab3", False)]:
    if key not in st.session_state:
        st.session_state[key] = default

# ---------------- SIDEBAR NAV ----------------
with st.sidebar:
    menu = st.radio("Navegación", ["Disponibles para Alquilar", "Gafas para Equipo", "Próximos Envíos", "Recepcion"])
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

# Pre-cargar mapa de locations
locations_map = load_locations_map()

# ---------------- TAB 1 ----------------
if menu == "Disponibles para Alquilar":
    st.title("Disponibles para Alquilar")

    with st.expander("📘 Leyenda de estados"):
        render_legend()
    d1, d2 = st.columns(2)
    with d1: start = st.date_input("Fecha inicio", date.today())
    with d2: end = st.date_input("Fecha fin", date.today())

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
                        device_name = next((d["Name"] for d in avail if d["id"] == did), "Dispositivo")
                        status_text.text(f"⚙️ Asignando {idx + 1}: {device_name}")
                        assign_device(did, new)
                        progress_bar.progress(0.2 + 0.8 * (idx + 1) / len(st.session_state.sel1))

                    status_text.empty()
                    st.success("✅ Proceso completado")
                    clear_all_cache()
                    st.rerun()

# ---------------- TAB 2 ----------------
elif menu == "Gafas para Equipo":
    st.title("Gafas para Equipo")
    with st.expander("📘 Leyenda de estados"):
        render_legend()

    # ==========================================================
    # Inicialización de la copia local (solo 1 vez)
    # ==========================================================
    if "devices_live" not in st.session_state:
        st.session_state.devices_live = load_devices()

    devices = st.session_state.devices_live
    inh = load_inhouse()
    loc_map = load_locations_map()
    oid = office_id()

    # ==========================================================
    # Mapa persona → dispositivos
    # ==========================================================
    people_devices = {p["id"]: [] for p in inh}

    for dev in devices:
        for lid in dev["location_ids"]:
            if lid in people_devices:
                people_devices[lid].append(dev)

    people_with_devices = [
        p for p in inh if len(people_devices[p["id"]]) > 0
    ]

    st.markdown("## 👥 Equipo con dispositivos asignados")

    # ==========================================================
    # Expanders por persona, cada gafa con botón ✕
    # ==========================================================
    for person in people_with_devices:
        pid = person["id"]
        pname = person["name"]
        devs = people_devices[pid]
        count = len(devs)

        with st.expander(f"{pname} ({count})", expanded=False):

            for d in devs:
                cols = st.columns([9.2, 0.8])
                with cols[0]:
                    card(d["Name"], location_types="In House", selected=False)
                with cols[1]:
                    if st.button("✕", key=f"rm_{d['id']}"):
                        # Notion
                        assign_device(d["id"], oid)

                        # Actualización local inmediata
                        d["location_ids"] = [oid]

                        # Redibujar interfaz instantáneamente
                        st.rerun()

    st.markdown("---")

    # ==========================================================
    # Toggle mostrar/ocultar disponibles
    # ==========================================================
    label = "Ocultar otras gafas disponibles" if st.session_state.get("show_avail_home") else "Mostrar otras gafas disponibles"
    if st.button(label, key="toggle_avail_home"):
        st.session_state.show_avail_home = not st.session_state.get("show_avail_home", False)
        st.rerun()

    # ==========================================================
    # Lista de disponibles (en oficina)
    # ==========================================================
    if st.session_state.get("show_avail_home", False):

        st.subheader("Otras gafas disponibles (en oficina)")

        office_devices = [d for d in devices if oid in d["location_ids"]]

        for d in office_devices:
            key = f"o_{d['id']}"
            subtitle = get_location_types_for_device(d, loc_map)
            cols = st.columns([0.5, 9.5])
            with cols[0]:
                st.checkbox("", key=key)
            with cols[1]:
                card(d["Name"], location_types=subtitle, selected=st.session_state.get(key, False))

        st.session_state.sel2 = [
            d["id"] for d in office_devices if st.session_state.get(f"o_{d['id']}", False)
        ]
        sel_count = len(st.session_state.sel2)

        with st.sidebar:
            counter_badge(sel_count, len(office_devices))

            if sel_count > 0:
                dest = st.selectbox("Asignar a:", [x["name"] for x in inh])
                dest_id = next(x["id"] for x in inh if x["name"] == dest)

                if st.button("Asignar seleccionadas"):
                    progress_bar = st.progress(0)
                    status_text = st.empty()

                    for idx, did in enumerate(st.session_state.sel2):

                        # 1. Notion
                        assign_device(did, dest_id)

                        # 2. Actualización LOCAL inmediata
                        for d in devices:
                            if d["id"] == did:
                                d["location_ids"] = [dest_id]

                        status_text.text(f"📦 Moviendo {idx + 1}")
                        progress_bar.progress((idx + 1) / sel_count)

                    status_text.empty()
                    st.success("✅ Asignación completada")

                    # Reset selección
                    st.session_state.sel2 = []

                    # UI actualizada inmediatamente
                    st.rerun()


# ---------------- TAB 3 ----------------
elif menu == "Próximos Envíos":
    st.title("Próximos Envíos")
    with st.expander("📘 Leyenda de estados"):
        render_legend()
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
                    subtitle = get_location_types_for_device(d, locations_map)
                    card(d["Name"], location_types=subtitle)
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
                can_add = [
                    d for d in devices
                    if d.get("location_ids")
                    and available(d, ls, le)
                    and loc["id"] not in d["location_ids"]
                ]

                st.subheader("Reservar otras gafas")

                for d in can_add:
                    key = f"add_{d['id']}"
                    subtitle = get_location_types_for_device(d, locations_map)
                    cols = st.columns([0.5, 9.5])
                    with cols[0]: st.checkbox("", key=key)
                    with cols[1]: card(d["Name"], location_types=subtitle, selected=st.session_state.get(key, False))

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

# ---------------- TAB 4: CHECK-IN ----------------
elif menu == "Recepcion":
    st.title("Check-In de Gafas (de vuelta a oficina)")

    with st.expander("📘 Leyenda de estados"):
        render_legend()

    today = date.today()
    all_locs = q(LOCATIONS_ID)

        # Filtrar locations tipo Client con End Date < hoy Y con dispositivos asociados
    devices = load_devices()
    finished = []

    for p in all_locs:
        props = p["properties"]

        # 1) Debe ser tipo Client
        if not props["Type"]["select"] or props["Type"]["select"]["name"] != "Client":
            continue

        # 2) Debe tener fecha fin pasada
        ed = props["End Date"]["date"]["start"] if props["End Date"]["date"] else None
        if not ed or iso_to_date(ed) >= today:
            continue

        loc_id = p["id"]

        # 3) Debe tener al menos un dispositivo asociado
        assigned = [d for d in devices if loc_id in d["location_ids"]]
        if len(assigned) == 0:
            continue

        # Si pasa todo, añadir
        finished.append({
            "id": loc_id,
            "name": props["Name"]["title"][0]["text"]["content"],
            "end": ed
        })


    if not finished:
        st.info("No hay envíos finalizados pendientes de check-in.")
        st.stop()

    options = ["Seleccionar..."] + [f"{x['name']} (fin {x['end']})" for x in finished]
    sel = st.selectbox("Selecciona envío terminado:", options)

    if sel != "Seleccionar...":

        loc = finished[options.index(sel) - 1]
        st.write(f"📅 Finalizó el **{loc['end']}**")

        devices = load_devices()
        assigned = [d for d in devices if loc["id"] in d["location_ids"]]
        office = office_id()

        with st.expander(f"📦 Gafas para recepcionar ({len(assigned)})", expanded=True):

            for d in assigned:
                cols = st.columns([9, 1])
                with cols[0]:
                    subtitle = get_location_types_for_device(d, locations_map)
                    card(d["Name"], location_types=subtitle)

                # Botón de recepción
                with cols[1]:
                    if st.button("📥", key=f"checkin_{d['id']}"):

                        # 1) Insertar relación al histórico (igual que tu automatización)
                        requests.post(
                            "https://api.notion.com/v1/pages",
                            headers=headers,
                            json={
                                "parent": {"database_id": "2a158a35e411806d9d11c6d77598d44d"},
                                "properties": {
                                    "Name": {"title": [{"text": {"content": d['Name']}}]},
                                    "Tags": {"select": {"name": d["Tags"]}},
                                    "SN": {"rich_text": [{"text": {"content": d.get("SN", "")}}]},
                                    "Location": {"relation": [{"id": loc["id"]}]},
                                    "Start Date": {"date": {"start": d["Start"]}},
                                    "End Date": {"date": {"start": d["End"]}},
                                    "Check In": {"date": {"start": date.today().isoformat()}}
                                }
                            }
                        )

                        # 2) Quitar relación con cliente y volver a Office
                        assign_device(d["id"], office)

                        # 3) Refrescar
                        clear_all_cache()
                        st.rerun()

        st.success("Haz clic en 📥 para recepcionar cada gafa.")
