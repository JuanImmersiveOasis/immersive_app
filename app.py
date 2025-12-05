import streamlit as st
import requests
from datetime import datetime, date, timedelta
import os
from dotenv import load_dotenv
import time

load_dotenv()

st.set_page_config(page_title="Logistica", page_icon=None, layout="wide")

st.markdown("""
    <style>
    /* Botones principales */
    .stButton > button {
        background-color: #00859b;
        color: white;
        border: none;
        border-radius: 6px;
        padding: 8px 20px;
        font-weight: 600;
        transition: all 0.2s ease;
    }
    
    .stButton > button:hover {
        background-color: #006d82;
        transform: translateY(-1px);
        box-shadow: 0 2px 4px rgba(0,0,0,0.15);
    }
    
    .stButton > button:active {
        background-color: #005565;
        transform: translateY(0px);
    }
    
    .stFormSubmitButton > button {
    background-color: #00859b;
    color: white;
    border: none;
    border-radius: 6px;
    font-weight: 600;
    transition: all 0.2s ease;
    }

    .stFormSubmitButton > button:hover {
        background-color: #006d82;
        transform: translateY(-1px);
        box-shadow: 0 2px 4px rgba(0,0,0,0.15);
    }

    .stFormSubmitButton > button:active {
        background-color: #005565;
        transform: translateY(0px);
    }
        </style>
        """, unsafe_allow_html=True)


try:
    NOTION_TOKEN = st.secrets["NOTION_TOKEN"]
except:
    NOTION_TOKEN = os.getenv("NOTION_TOKEN")

if not NOTION_TOKEN:
    st.error("Falta NOTION_TOKEN")
    st.stop()

NOTION_VERSION = "2022-06-28"

DEVICES_ID = "43e15b677c8c4bd599d7c602f281f1da"
LOCATIONS_ID = "28758a35e4118045abe6e37534c44974"
HISTORIC_ID = "2a158a35e411806d9d11c6d77598d44d"
ACTIVE_INC_ID = "28c58a35e41180b8ae87fb11aec1f48e"
PAST_INC_ID = "28e58a35e41180f29199c42d33500566"

headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": NOTION_VERSION,
}

PREFERRED_TAG_ORDER = ["Ultra", "Neo 4", "Quest 2", "Quest 3", "Quest 3S", "Vision Pro"]

def show_feedback(message_type, message, duration=None):
    with st.sidebar:
        placeholder = st.empty()
        
        with placeholder.container():
            if message_type == 'success':
                st.success(message, icon="✅")
            elif message_type == 'error':
                st.error(message)
            elif message_type == 'warning':
                st.warning(message)
            elif message_type == 'info':
                st.info(message)
            elif message_type == 'spinner':
                with st.spinner(message):
                    return placeholder
        
        if duration:
            time.sleep(duration)
            placeholder.empty()
        
        return placeholder

def iso_to_date(s):
    try:
        return datetime.fromisoformat(s).date()
    except:
        return None

def fmt(date_str):
    try:
        dt = iso_to_date(date_str)
        return dt.strftime("%d/%m/%Y")
    except:
        return date_str
    
def fmt_datetime(date_str):
    try:
        dt = datetime.fromisoformat(date_str)
        return dt.strftime("%d/%m/%Y %H:%M")
    except:
        return date_str if date_str else "Sin fecha"
    
def format_relative_date(date_obj):
    today = date.today()
    days_diff = (date_obj - today).days
    
    day_names = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    day_name = day_names[date_obj.weekday()]
    day_num = date_obj.day
    
    if days_diff == 0:
        return "hoy"
    elif days_diff == 1:
        return "mañana"
    elif days_diff == -1:
        return "ayer"
    elif 2 <= days_diff <= 6:
        return f"este {day_name}, día {day_num}"
    elif 7 <= days_diff <= 13:
        return f"el {day_name} que viene, día {day_num}"
    elif -7 <= days_diff <= -2:
        return f"el {day_name}, día {day_num}"
    elif days_diff < -7:
        weeks_ago = abs(days_diff) // 7
        if weeks_ago == 1:
            return f"hace una semana, día {day_num}"
        else:
            return f"hace {weeks_ago} semanas, día {day_num}"
    else:
        return f"dentro de {days_diff} días"

@st.cache_data(ttl=300)
def q(db, payload=None):
    if payload is None:
        payload = {"page_size": 100}
    
    url = f"https://api.notion.com/v1/databases/{db}/query"
    results = []
    next_cursor = None
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
    response = requests.patch(
        f"https://api.notion.com/v1/pages/{dev_id}",
        json={"properties": {"Location": {"relation": [{"id": loc_id}]}}},
        headers=headers
    )
    load_devices.clear()
    load_future_client_locations.clear()
    q.clear()
    preload_all_data.clear()
    return response

def legend_button():
    st.markdown(
        '''
        <style>
        .legend-container {
            position: relative;
            display: flex;
            justify-content: flex-end;
            margin-bottom: 15px;
            margin-top: -45px;
        }
        
        .legend-button {
            width: 28px;
            height: 28px;
            border-radius: 50%;
            background: #e0e0e0;
            color: #666;
            border: none;
            font-size: 16px;
            font-weight: bold;
            cursor: help;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.2s ease;
        }
        
        .legend-button:hover {
            background: #00859b;
            color: white;
        }
        
        .legend-tooltip {
            visibility: hidden;
            opacity: 0;
            position: absolute;
            top: 35px;
            right: 0;
            background: white;
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 15px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            z-index: 1000;
            width: 520px;
            transition: opacity 0.3s ease, visibility 0.3s ease;
            pointer-events: none;
        }
        
        .legend-button:hover + .legend-tooltip,
        .legend-tooltip:hover {
            visibility: visible;
            opacity: 1;
            pointer-events: auto;
        }
        
        .legend-item {
            display: flex;
            align-items: center;
            margin-bottom: 8px;
        }
        
        .legend-badge {
            display: inline-block;
            width: 24px;
            height: 24px;
            line-height: 24px;
            text-align: center;
            font-weight: bold;
            color: #fff;
            border-radius: 4px;
            margin-right: 10px;
            flex-shrink: 0;
        }
        
        .legend-incident-badge {
            display: inline-block;
            min-width: 35px;
            height: 24px;
            line-height: 24px;
            text-align: center;
            font-weight: bold;
            color: #fff;
            border-radius: 4px;
            margin-right: 10px;
            padding: 0 6px;
            flex-shrink: 0;
            font-size: 11px;
        }
        
        .legend-text {
            font-size: 13px;
            color: #333;
            line-height: 1.4;
        }
        
        .legend-divider {
            height: 1px;
            background: #e0e0e0;
            margin: 12px 0;
        }
        </style>
        
        <div class="legend-container">
            <div class="legend-button">?</div>
            <div class="legend-tooltip">
                <div class="legend-item">
                    <span class="legend-badge" style="background:#4CAF50;">O</span>
                    <span class="legend-text"><strong>Office:</strong> Las gafas se encuentran DISPONIBLES en oficina, libres de compromisos.</span>
                </div>
                <div class="legend-item">
                    <span class="legend-badge" style="background:#FF9800;">C</span>
                    <span class="legend-text"><strong>Client:</strong> Las gafas se encuentran ASIGNADAS a un proyecto en otras fechas.</span>
                </div>
                <div class="legend-item">
                    <span class="legend-badge" style="background:#1565C0;">H</span>
                    <span class="legend-text"><strong>At Home:</strong> Las gafas se encuentran en casa de algun miembro del equipo.</span>
                </div>
                <div class="legend-divider"></div>
                <div class="legend-item">
                    <span class="legend-incident-badge" style="background:#9E9E9E;">0/1</span>
                    <span class="legend-text">Dispositivos con incidencias resueltas en el pasado.</span>
                </div>
                <div class="legend-item">
                    <span class="legend-incident-badge" style="background:#E53935;">1/1</span>
                    <span class="legend-text">Dispositivos con alguna incidencia sin resolver actualmente.</span>
                </div>
            </div>
        </div>
        ''',
        unsafe_allow_html=True
    )

def card(name, location_types=None, selected=False, incident_counts=None):
    color_map_bg = {
        "Office": "#D9E9DC",
        "In House": "#E1EDF8",
        "Client": "#F4ECDF"
    }
    
    color_map_badge = {
        "Office": "#4CAF50",
        "In House": "#1565C0",
        "Client": "#FF9800"
    }
    
    badge_letter_map = {
        "Office": "O",
        "In House": "H",
        "Client": "C"
    }
    
    bg = "#e0e0e0"
    badge_html = ""
    border_color = "#9e9e9e"
    text_color = "#000"
    
    if location_types:
        first_type = location_types.split("  ")[0]
        bg = color_map_bg.get(first_type, "#e0e0e0")
        badge_color = color_map_badge.get(first_type, "#B3E5E6")
        letter = badge_letter_map.get(first_type, "?")
        
        badge_html = (
            f"<span style='float:right;width:20px;height:20px;line-height:20px;"
            f"text-align:center;font-weight:bold;color:#fff;background:{badge_color};"
            f"border-radius:4px;margin-left:8px'>{letter}</span>"
        )
    
    if selected:
        bg = "#B3E5E6"
    
    incident_badge_html = ""
    if incident_counts:
        active, total = incident_counts
        
        if active > 0:
            border_color = "#E53935"
            text_color = "#E53935"
            
            incident_badge_html = (
                f"<span style='float:right;width:auto;min-width:20px;height:20px;line-height:20px;"
                f"text-align:center;font-weight:bold;color:#fff;background:#E53935;"
                f"border-radius:4px;margin-left:8px;padding:0 6px;font-size:11px;'>"
                f"{active}/{total}</span>"
            )
        elif total > 0:
            incident_badge_html = (
                f"<span style='float:right;width:auto;min-width:20px;height:20px;line-height:20px;"
                f"text-align:center;font-weight:bold;color:#fff;background:#9E9E9E;"
                f"border-radius:4px;margin-left:8px;padding:0 6px;font-size:11px;'>"
                f"0/{total}</span>"
            )
    
    st.markdown(
        f"""
        <div style='padding:7px;background:{bg};border-left:4px solid {border_color};
                    border-radius:6px;margin-bottom:4px;overflow:auto;'>
            <b style='color:{text_color};'>{name}</b> {badge_html}{incident_badge_html} 
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

@st.cache_data(ttl=600)
def load_locations_map():
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

@st.cache_data(ttl=300)
def load_devices():
    results = q(DEVICES_ID)
    out = []
    
    for p in results:
        props = p["properties"]
        
        name = props["Name"]["title"][0]["text"]["content"] if props["Name"]["title"] else "Sin nombre"
        
        tag = props["Tags"]["select"]["name"] if props.get("Tags") and props["Tags"]["select"] else None
        
        locs = [r["id"] for r in props["Location"]["relation"]] if props.get("Location") and props["Location"]["relation"] else []
        
        try:
            sn = props["SN"]["rich_text"][0]["text"]["content"]
        except:
            sn = ""
        
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
    
    out = sorted(out, key=lambda x: x["Name"])
    return out

@st.cache_data(ttl=300)
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

@st.cache_data(ttl=300)
def load_past_client_locations():
    today = date.today()
    fifteen_days_ago = today - timedelta(days=15)
    results = q(LOCATIONS_ID)
    devices = load_devices()
    historic = q(HISTORIC_ID)
    out = []
    
    for p in results:
        props = p["properties"]
        
        try:
            t = props["Type"]["select"]["name"]
        except:
            t = None
        
        if t != "Client":
            continue
        
        ed = props["End Date"]["date"]["start"] if props.get("End Date") and props["End Date"]["date"] else None
        if not ed:
            continue
        
        end_date = iso_to_date(ed)
        
        if end_date >= today or end_date < fifteen_days_ago:
            continue
        
        try:
            name = props["Name"]["title"][0]["text"]["content"]
        except:
            name = "Sin nombre"
        
        sd = props["Start Date"]["date"]["start"] if props.get("Start Date") and props["Start Date"]["date"] else None
        
        loc_id = p["id"]
        
        currently_assigned = sum(1 for d in devices if loc_id in d["location_ids"])
        
        historic_count = 0
        for entry in historic:
            hist_props = entry["properties"]
            hist_loc = hist_props.get("Location", {}).get("relation", [])
            if hist_loc and hist_loc[0]["id"] == loc_id:
                historic_count += 1
        
        device_count = currently_assigned + historic_count
        
        out.append({
            "id": loc_id,
            "name": name,
            "start": sd,
            "end": ed,
            "device_count": device_count,
            "end_date_obj": end_date
        })
    
    out = sorted(out, key=lambda x: x["end_date_obj"], reverse=True)
    
    return out

@st.cache_data(ttl=600)
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

@st.cache_data(ttl=600)
def office_id():
    r = q(LOCATIONS_ID, {"filter": {"property": "Name", "title": {"equals": "Office"}}})
    oid = r[0]["id"] if r else None
    return oid

@st.cache_data(ttl=180)
def load_active_incidents():
    r = q(ACTIVE_INC_ID)
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

@st.cache_data(ttl=300)
def load_past_incidents():
    r = q(PAST_INC_ID)
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

@st.cache_data(ttl=180)
def load_incidence_map():
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
    
    return "  ".join(uniq) if uniq else None

def smart_segmented_filter(devices, key_prefix, tag_field="Tags", show_red_for_active=False, incidence_map=None):
    present_tags = {d.get(tag_field) for d in devices if d.get(tag_field)}
    
    ordered_tags = []
    
    for preferred_tag in PREFERRED_TAG_ORDER:
        if preferred_tag in present_tags:
            ordered_tags.append(preferred_tag)
    
    new_tags = sorted([tag for tag in present_tags if tag not in PREFERRED_TAG_ORDER])
    ordered_tags.extend(new_tags)
    
    if show_red_for_active and incidence_map:
        counts_active = {"Todas": 0}
        counts_total = {"Todas": 0}
        
        for tag in ordered_tags:
            counts_active[tag] = 0
            counts_total[tag] = 0
        
        for d in devices:
            tag = d.get(tag_field)
            inc = incidence_map.get(d["id"], {"active": 0, "total": 0})
            
            counts_active["Todas"] += inc["active"]
            counts_total["Todas"] += inc["total"]
            
            if tag in counts_active:
                counts_active[tag] += inc["active"]
                counts_total[tag] += inc["total"]
    else:
        counts = {"Todas": len(devices)}
        for tag in ordered_tags:
            counts[tag] = sum(1 for d in devices if d.get(tag_field) == tag)
    
    opciones_display = []
    opciones_map = {}
    
    if show_red_for_active and incidence_map:
        if counts_active["Todas"] > 0:
            label_all = f"Todas :red[({counts_active['Todas']})]"
        else:
            label_all = f"Todas ({counts_active['Todas']})"
    else:
        label_all = f"Todas ({counts['Todas']})"
    
    opciones_display.append(label_all)
    opciones_map[label_all] = "Todas"
    
    for tag in ordered_tags:
        if show_red_for_active and incidence_map:
            if counts_active[tag] > 0:
                label = f"{tag} :red[({counts_active[tag]})]"
            else:
                label = f"{tag} ({counts_active[tag]})"
        else:
            label = f"{tag} ({counts[tag]})"
        
        opciones_display.append(label)
        opciones_map[label] = tag
    
    sel_label = st.segmented_control(
        label=None,
        options=opciones_display,
        default=opciones_display[0],
        key=f"{key_prefix}_seg"
    )
    
    if sel_label not in opciones_map:
        sel_label = opciones_display[0]
        st.session_state[f"{key_prefix}_seg"] = sel_label
    
    selected_group = opciones_map[sel_label]
    
    if selected_group == "Todas":
        filtered = devices
    else:
        filtered = [d for d in devices if d.get(tag_field) == selected_group]
    
    return filtered, selected_group

@st.cache_data(ttl=180)
def preload_all_data():
    data = {
        'locations_map': load_locations_map(),
        'devices': load_devices(),
        'future_locations': load_future_client_locations(),
        'past_locations': load_past_client_locations(),
        'inhouse': load_inhouse(),
        'office_id': office_id(),
        'active_incidents': load_active_incidents(),
        'past_incidents': load_past_incidents(),
        'incidence_map': load_incidence_map(),
        'all_locations': q(LOCATIONS_ID)
    }
    return data

for key, default in [
    ("tab1_show", False),
    ("sel1", []),
    ("sel2", []),
    ("sel3", []),
    ("tab3_loc", None),
    ("show_avail_tab3", False),
    ("show_avail_home", False),
    ("processing_action", False)
]:
    if key not in st.session_state:
        st.session_state[key] = default

with st.spinner("🔄 Cargando datos desde Notion..."):
    preloaded_data = preload_all_data()

locations_map = preload_all_data()['locations_map']
all_devices = preloaded_data['devices']
incidence_map = preloaded_data['incidence_map']

with st.sidebar:
    st.image("img/logo.png", use_container_width=True)
    
    num_proximos = len(preloaded_data['future_locations'])
    
    today = date.today()
    all_locs = preloaded_data['all_locations']
    devices_tmp = all_devices
    
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
    
    num_incidencias = len(preloaded_data['active_incidents'])
    
    st.markdown("---")
    
    def create_menu_label(text, count=0):
        if count > 0:
            return f"{text}   ({count})"
        else:
            return text
    
    opciones_menu = [
        create_menu_label("Disponibles para Alquilar", 0),
        create_menu_label("Gafas en casa", 0),
        create_menu_label("Próximos Envíos", num_proximos),
        create_menu_label("Check-In", num_finished),
        create_menu_label("Incidencias", num_incidencias)
    ]
    
    menu_mapping = {
        opciones_menu[0]: "Disponibles para Alquilar",
        opciones_menu[1]: "Gafas en casa",
        opciones_menu[2]: "Próximos Envíos",
        opciones_menu[3]: "Check-In",
        opciones_menu[4]: "Incidencias"
    }
    
    reverse_mapping = {v: k for k, v in menu_mapping.items()}
    
    if "force_incidents_tab" in st.session_state and st.session_state.get("force_incidents_tab"):
        if "nav_radio" in st.session_state:
            st.session_state.nav_radio = reverse_mapping["Incidencias"]
    
    selected_label = st.radio(
        label="nav",
        options=opciones_menu,
        label_visibility="collapsed",
        key="nav_radio"
    )
    
    st.session_state.menu = menu_mapping[selected_label]
    
    st.markdown("----")
    
    if st.button("Refrescar", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

if "force_incidents_tab" in st.session_state and st.session_state.force_incidents_tab:
    st.session_state.menu = "Incidencias"
    st.session_state.force_incidents_tab = False

if st.session_state.menu == "Disponibles para Alquilar":
    st.title("Disponibles para Alquilar")
    legend_button()
    
    c1, c2 = st.columns(2)
    with c1:
        start = st.date_input("Fecha salida", date.today())
    with c2:
        end = st.date_input("Fecha regreso", date.today())
    
    if st.button("Comprobar disponibilidad"):
        st.session_state.tab1_show = True
        st.session_state.sel1 = []
        for key in list(st.session_state.keys()):
            if key.startswith("a_"):
                del st.session_state[key]
    
    if st.session_state.tab1_show:
        devices = all_devices
        
        avail = [
            d for d in devices
            if d.get("location_ids") and available(d, start, end)
        ]
        
        avail_filtered, _ = smart_segmented_filter(avail, key_prefix="tab1")
        
        with st.container(height=400, border=True):
            for d in avail_filtered:
                key = f"a_{d['id']}"
                subtitle = get_location_types_for_device(d, locations_map)
                
                cols = st.columns([0.5, 9.5])
                with cols[0]:
                    st.checkbox("", key=key)
                
                with cols[1]:
                    inc = incidence_map.get(d["id"], {"active": 0, "total": 0})
                    card(
                        d["Name"],
                        location_types=subtitle,
                        selected=st.session_state.get(key, False),
                        incident_counts=(inc["active"], inc["total"])
                    )
        
        st.session_state.sel1 = [
            d["id"] for d in avail_filtered if st.session_state.get(f"a_{d['id']}", False)
        ]
        sel_count = len(st.session_state.sel1)
        
        with st.sidebar:
            counter_badge(sel_count, len(avail_filtered))
            
            if sel_count > 0:
                with st.form("form_assign_client"):
                    client = st.text_input("Nombre Cliente")
                    submit = st.form_submit_button("Asignar Cliente", use_container_width=True)
                    
                    if submit:
                        if not client or client.strip() == "":
                            show_feedback('error', "Debes escribir el nombre del cliente", duration=2)
                        else:
                            feedback_placeholder = st.empty()
                            with feedback_placeholder:
                                with st.spinner("Asignando dispositivos..."):
                                    response = requests.post(
                                        "https://api.notion.com/v1/pages", 
                                        headers=headers,
                                        json={
                                            "parent": {"database_id": LOCATIONS_ID},
                                            "properties": {
                                                "Name": {"title": [{"text": {"content": client}}]},
                                                "Type": {"select": {"name": "Client"}},
                                                "Start Date": {"date": {"start": start.isoformat()}},
                                                "End Date": {"date": {"start": end.isoformat()}}
                                            }
                                        }
                                    )
                                    
                                    if response.status_code == 200:
                                        new_loc_id = response.json()["id"]
                                        
                                        success_count = 0
                                        for did in st.session_state.sel1:
                                            resp = assign_device(did, new_loc_id)
                                            if resp.status_code == 200:
                                                success_count += 1
                                        
                                        st.session_state.sel1 = []
                                        for key in list(st.session_state.keys()):
                                            if key.startswith("a_"):
                                                del st.session_state[key]
                                        
                                        load_devices.clear()
                                        load_future_client_locations.clear()
                                        load_locations_map.clear()
                                        q.clear()
                                        preload_all_data.clear()
                                        
                                        feedback_placeholder.empty()
                                        show_feedback('success', f"{success_count} dispositivos asignados correctamente", duration=1.5)
                                        
                                        time.sleep(1.5)
                                        st.rerun()
                                        st.stop()
                                    else:
                                        feedback_placeholder.empty()
                                        show_feedback('error', f"Error al crear ubicación: {response.status_code}", duration=3)
                                        st.stop()

elif st.session_state.menu == "Gafas en casa":
    st.title("Gafas en casa")
    legend_button()
    
    devices = all_devices
    inh = preloaded_data['inhouse']
    oid = preloaded_data['office_id']
    
    inh_ids = [p["id"] for p in inh]
    
    inhouse_devices = [
        d for d in devices
        if any(l in inh_ids for l in d["location_ids"])
    ]
    
    with st.expander("Personal con dispositivos en casa", expanded=True):
        inhouse_filtered, _ = smart_segmented_filter(inhouse_devices, key_prefix="inhouse")
        
        people_devices = {p["id"]: [] for p in inh}
        for d in inhouse_filtered:
            for lid in d["location_ids"]:
                if lid in people_devices:
                    people_devices[lid].append(d)
        
        people_with_devices = [
            p for p in inh if len(people_devices[p["id"]]) > 0
        ]
        
        with st.container(border=False):
            for person in people_with_devices:
                pid = person["id"]
                pname = person["name"]
                devs = people_devices.get(pid, [])
                
                with st.expander(f"{pname} ({len(devs)})"):
                    for d in devs:
                        cols = st.columns([8, 2])
                        
                        with cols[0]:
                            inc = incidence_map.get(d["id"], {"active": 0, "total": 0})
                            card(
                                d["Name"],
                                location_types="In House",
                                incident_counts=(inc["active"], inc["total"])
                            )
                        
                        with cols[1]:
                            if st.button("Devolver", key=f"rm_{d['id']}", use_container_width=True):
                                if not st.session_state.processing_action:
                                    st.session_state.processing_action = True
                                    with st.sidebar:
                                        with st.spinner("Moviendo a oficina..."):
                                            resp = assign_device(d["id"], oid)
                                            
                                            if resp.status_code == 200:
                                                load_devices.clear()
                                                preload_all_data.clear()
                                                st.session_state.processing_action = False
                                                st.rerun()
                                            else:
                                                st.session_state.processing_action = False
                                                show_feedback('error', f"Error: {resp.status_code}", duration=2)
    
    office_devices = [
        d for d in devices
        if oid in d["location_ids"]
    ]
    
    expander_office_open = st.session_state.get("expander_office_open", False)
    
    with st.expander("Otras gafas disponibles en oficina", expanded=expander_office_open):
        st.session_state.expander_office_open = True
        
        office_filtered, _ = smart_segmented_filter(office_devices, key_prefix="office")
        
        with st.container(height=400, border=True):
            for d in office_filtered:
                key = f"o_{d['id']}"
                subtitle = get_location_types_for_device(d, locations_map)
                
                cols = st.columns([0.5, 9.5])
                
                with cols[0]:
                    st.checkbox("", key=key)
                
                with cols[1]:
                    inc = incidence_map.get(d["id"], {"active": 0, "total": 0})
                    card(
                        d["Name"],
                        location_types=subtitle,
                        selected=st.session_state.get(key, False),
                        incident_counts=(inc["active"], inc["total"])
                    )
        
        st.session_state.sel2 = [
            d["id"] for d in office_filtered
            if st.session_state.get(f"o_{d['id']}", False)
        ]
        sel_count = len(st.session_state.sel2)
        
        if sel_count > 0:
            with st.sidebar:
                counter_badge(sel_count, len(office_filtered))
                
                dest = st.selectbox("Asignar a:", [x["name"] for x in inh], key="dest_person")
                dest_id = next(x["id"] for x in inh if x["name"] == dest)
                
                if st.button("Asignar seleccionadas", use_container_width=True):
                    feedback_placeholder = st.empty()
                    with feedback_placeholder:
                        with st.spinner("Asignando dispositivos..."):
                            success_count = 0
                            for did in st.session_state.sel2:
                                resp = assign_device(did, dest_id)
                                if resp.status_code == 200:
                                    success_count += 1
                            
                            st.session_state.sel2 = []
                            for key in list(st.session_state.keys()):
                                if key.startswith("o_"):
                                    del st.session_state[key]
                            
                            st.session_state.expander_office_open = False
                            
                            load_devices.clear()
                            preload_all_data.clear()
                            
                            feedback_placeholder.empty()
                            show_feedback('success', f"{success_count} dispositivos asignados", duration=1.5)
                            time.sleep(1.5)
                            st.rerun()
    
    if not expander_office_open:
        st.session_state.expander_office_open = False

elif st.session_state.menu == "Próximos Envíos":
    st.title("Próximos Envíos")
    legend_button()
    
    future_locs = preloaded_data['future_locations']
    past_locs = preloaded_data['past_locations']
    
    with st.expander(f"Envíos futuros ({len(future_locs)})", expanded=True):
        if len(future_locs) == 0:
            st.info("No hay envíos futuros.")
        else:
            for loc in future_locs:
                lname = loc["name"]
                start = fmt(loc["start"])
                end = fmt(loc["end"])
                loc_id = loc["id"]
                
                devices = all_devices
                
                expander_key = f"expander_loc_{loc_id}"
                is_expanded = st.session_state.get(expander_key, False)
                
                with st.expander(f"{lname} ({start} → {end})", expanded=is_expanded):
                    st.session_state[expander_key] = True
                    
                    with st.form(key=f"edit_dates_{loc_id}"):
                        st.subheader("📅 Editar fechas del envío")
                        
                        col_start, col_end = st.columns(2)
                        
                        with col_start:
                            current_start = iso_to_date(loc["start"])
                            new_start = st.date_input(
                                "Fecha salida",
                                value=current_start,
                                key=f"new_start_{loc_id}"
                            )
                        
                        with col_end:
                            current_end = iso_to_date(loc["end"]) if loc["end"] else None
                            new_end = st.date_input(
                                "Fecha regreso",
                                value=current_end if current_end else date.today(),
                                key=f"new_end_{loc_id}"
                            )
                        
                        submit_dates = st.form_submit_button("Actualizar fechas", use_container_width=True)
                        
                        if submit_dates:
                            if new_start > new_end:
                                show_feedback('error', "La fecha de salida no puede ser posterior a la de regreso", duration=3)
                            else:
                                with st.sidebar:
                                    with st.spinner("Actualizando fechas..."):
                                        update_response = requests.patch(
                                            f"https://api.notion.com/v1/pages/{loc_id}",
                                            headers=headers,
                                            json={
                                                "properties": {
                                                    "Start Date": {"date": {"start": new_start.isoformat()}},
                                                    "End Date": {"date": {"start": new_end.isoformat()}}
                                                }
                                            }
                                        )
                                        
                                        if update_response.status_code == 200:
                                            load_future_client_locations.clear()
                                            q.clear()
                                            preload_all_data.clear()
                                            
                                            st.session_state[expander_key] = True
                                            
                                            show_feedback('success', "Fechas actualizadas correctamente", duration=1.5)
                                            time.sleep(1.5)
                                            st.rerun()
                                        else:
                                            show_feedback('error', f"Error al actualizar: {update_response.status_code}", duration=3)
                    
                    st.markdown("---")
                    
                    assigned = [
                        d for d in devices
                        if loc_id in d["location_ids"]
                    ]
                    
                    if len(assigned) == 0:
                        st.warning("Este envío no tiene dispositivos asignados")
                        
                        if st.button("Borrar envío", key=f"delete_loc_{loc_id}", use_container_width=True):
                            with st.sidebar:
                                with st.spinner("Eliminando envío..."):
                                    delete_response = requests.patch(
                                        f"https://api.notion.com/v1/pages/{loc_id}",
                                        headers=headers,
                                        json={"archived": True}
                                    )
                                    
                                    if delete_response.status_code == 200:
                                        load_future_client_locations.clear()
                                        q.clear()
                                        preload_all_data.clear()
                                        st.rerun()
                                    else:
                                        show_feedback('error', f"Error al eliminar: {delete_response.status_code}", duration=3)
                    else:
                        st.subheader("Dispositivos asignados")
                        
                        assigned_filtered, _ = smart_segmented_filter(assigned, key_prefix=f"assigned_{loc_id}")
                        
                        with st.container(border=False):
                            for d in assigned_filtered:
                                cols = st.columns([8, 2])
                                
                                with cols[0]:
                                    subtitle = get_location_types_for_device(d, locations_map)
                                    inc = incidence_map.get(d["id"], {"active": 0, "total": 0})
                                    card(
                                        d["Name"],
                                        location_types=subtitle,
                                        incident_counts=(inc["active"], inc["total"])
                                    )
                                
                                with cols[1]:
                                    if st.button("Quitar", key=f"rm_{loc_id}_{d['id']}", use_container_width=True):
                                        if not st.session_state.processing_action:
                                            st.session_state.processing_action = True
                                            with st.sidebar:
                                                with st.spinner("Quitando dispositivo..."):
                                                    resp = assign_device(d["id"], office_id())
                                                    
                                                    if resp.status_code == 200:
                                                        load_devices.clear()
                                                        preload_all_data.clear()
                                                        st.session_state[expander_key] = True
                                                        st.session_state.processing_action = False
                                                        st.rerun()
                                                    else:
                                                        st.session_state.processing_action = False
                                                        show_feedback('error', f"Error: {resp.status_code}", duration=2)
                    
                    add_expander_key = f"add_expander_{loc_id}"
                    add_expanded = st.session_state.get(add_expander_key, False)
                    
                    with st.expander("Más gafas disponibles", expanded=add_expanded):
                        
                        ls = iso_to_date(loc["start"])
                        le = iso_to_date(loc["end"])
                        
                        can_add = [
                            d for d in devices
                            if d.get("location_ids")
                            and available(d, ls, le)
                            and loc_id not in d["location_ids"]
                        ]
                        
                        can_add_filtered, _ = smart_segmented_filter(can_add, key_prefix=f"canadd_{loc_id}")
                        
                        checkbox_keys = []
                        
                        with st.container(height=400, border=True):
                            for d in can_add_filtered:
                                key = f"add_{loc_id}_{d['id']}"
                                checkbox_keys.append(key)
                                
                                subtitle = get_location_types_for_device(d, locations_map)
                                
                                cols = st.columns([0.5, 9.5])
                                
                                with cols[0]:
                                    st.checkbox("", key=key)
                                
                                with cols[1]:
                                    inc = incidence_map.get(d["id"], {"active": 0, "total": 0})
                                    card(
                                        d["Name"],
                                        location_types=subtitle,
                                        selected=st.session_state.get(key, False),
                                        incident_counts=(inc["active"], inc["total"])
                                    )
                        
                        selected_ids = [
                            key.split("_")[-1]
                            for key in checkbox_keys
                            if st.session_state.get(key, False)
                        ]
                        
                        sel_count = len(selected_ids)
                        
                        if sel_count > 0:
                            st.session_state[add_expander_key] = True
                        
                        if sel_count > 0:
                            with st.sidebar:
                                counter_badge(sel_count, len(can_add_filtered))
                                
                                if st.button(f"Añadir a {lname}", key=f"assign_btn_{loc_id}", use_container_width=True):
                                    with st.spinner("Añadiendo dispositivos..."):
                                        success_count = 0
                                        for did in selected_ids:
                                            resp = assign_device(did, loc_id)
                                            if resp.status_code == 200:
                                                success_count += 1
                                        
                                        for key in checkbox_keys:
                                            if key in st.session_state:
                                                del st.session_state[key]
                                        
                                        load_devices.clear()
                                        preload_all_data.clear()
                                        
                                        st.session_state[expander_key] = True
                                        st.session_state[add_expander_key] = False
                                        st.rerun()
                
                if not is_expanded:
                    st.session_state[expander_key] = False
    
    with st.expander(f"Envíos realizados (últimos 15 días) ({len(past_locs)})", expanded=True):
        if len(past_locs) == 0:
            st.info("No hay envíos realizados en los últimos 15 días.")
        else:
            for loc in past_locs:
                lname = loc["name"]
                loc_id = loc["id"]
                device_count = loc["device_count"]
                end_date_obj = loc["end_date_obj"]
                
                relative_date = format_relative_date(end_date_obj)
                
                if end_date_obj < date.today():
                    status_text = f"Volvieron {relative_date}"
                else:
                    status_text = f"Vuelven {relative_date}"
                
                devices = all_devices
                
                expander_key = f"expander_past_loc_{loc_id}"
                is_expanded = st.session_state.get(expander_key, False)
                
                with st.expander(f"✅ {lname} [{device_count}] ({status_text})", expanded=is_expanded):
                    st.session_state[expander_key] = True
                    
                    assigned = [
                        d for d in devices
                        if loc_id in d["location_ids"]
                    ]
                    
                    if end_date_obj < date.today():
                        st.success("Estos dispositivos ya han sido devueltos")
                        
                        if len(assigned) > 0:
                            st.markdown("---")
                            st.caption("Dispositivos que se enviaron:")
                            
                            assigned_filtered, _ = smart_segmented_filter(assigned, key_prefix=f"past_assigned_{loc_id}")
                            
                            with st.container(border=False):
                                for d in assigned_filtered:
                                    subtitle = get_location_types_for_device(d, locations_map)
                                    inc = incidence_map.get(d["id"], {"active": 0, "total": 0})
                                    card(
                                        d["Name"],
                                        location_types=subtitle,
                                        incident_counts=(inc["active"], inc["total"])
                                    )
                    else:
                        st.warning("⏳ Pendientes de devolución")
                        
                        if len(assigned) == 0:
                            st.info("Este envío no tiene dispositivos registrados.")
                        else:
                            st.subheader("Dispositivos asignados")
                            
                            assigned_filtered, _ = smart_segmented_filter(assigned, key_prefix=f"past_assigned_{loc_id}")
                            
                            with st.container(border=False):
                                for d in assigned_filtered:
                                    subtitle = get_location_types_for_device(d, locations_map)
                                    inc = incidence_map.get(d["id"], {"active": 0, "total": 0})
                                    card(
                                        d["Name"],
                                        location_types=subtitle,
                                        incident_counts=(inc["active"], inc["total"])
                                    )
                
                if not is_expanded:
                    st.session_state[expander_key] = False

elif st.session_state.menu == "Check-In":
    st.title("Check-In de dispositivos")
    legend_button()
    
    today = date.today()
    all_locs = preloaded_data['all_locations']
    devices = all_devices
    
    finished = []
    
    for p in all_locs:
        props = p["properties"]
        
        if not props.get("Type") or props["Type"]["select"]["name"] != "Client":
            continue
        
        ed = None
        if props.get("End Date") and props["End Date"].get("date"):
            ed = props["End Date"]["date"]["start"]
        
        if not ed:
            continue
        
        if iso_to_date(ed) >= today:
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
        
        st.write(f"Finalizó el **{fmt(loc['end'])}**")
        
        assigned = [
            d for d in devices
            if loc["id"] in d["location_ids"]
        ]
        
        office = office_id()
        
        with st.expander(f"Gafas para recepcionar ({len(assigned)})", expanded=True):
            
            with st.container(border=False):
                for d in assigned:
                    cols = st.columns([8, 2])
                    
                    with cols[0]:
                        subtitle = get_location_types_for_device(d, locations_map)
                        inc = incidence_map.get(d["id"], {"active": 0, "total": 0})
                        card(
                            d["Name"],
                            location_types=subtitle,
                            incident_counts=(inc["active"], inc["total"])
                        )
                    
                    with cols[1]:
                        if st.button("Check-In", key=f"checkin_{d['id']}", use_container_width=True):
                            if not st.session_state.processing_action:
                                st.session_state.processing_action = True
                                with st.sidebar:
                                    with st.spinner("Procesando Check-In..."):
                                        payload = {
                                            "parent": {"database_id": HISTORIC_ID},
                                            "properties": {
                                                "Name": {"title": [{"text": {"content": d['Name']}}]},
                                                "Tags": {"select": {"name": d["Tags"]}} if d.get("Tags") else None,
                                                "SN": {"rich_text": [{"text": {"content": d.get("SN", "")}}]},
                                                "Location": {"relation": [{"id": loc["id"]}]},
                                                "Start Date": {"date": {"start": d["Start"]}} if d.get("Start") else None,
                                                "End Date": {"date": {"start": d["End"]}} if d.get("End") else None,
                                                "Check In": {"date": {"start": date.today().isoformat()}}
                                            }
                                        }
                                        
                                        payload["properties"] = {
                                            k: v for k, v in payload["properties"].items() if v is not None
                                        }
                                        
                                        r = requests.post(
                                            "https://api.notion.com/v1/pages",
                                            headers=headers,
                                            json=payload
                                        )
                                        
                                        if r.status_code != 200:
                                            st.session_state.processing_action = False
                                            show_feedback('error', f"Error al registrar en histórico: {r.status_code}", duration=3)
                                        else:
                                            resp = assign_device(d["id"], office)
                                            
                                            if resp.status_code == 200:
                                                load_devices.clear()
                                                q.clear()
                                                preload_all_data.clear()
                                                st.session_state.processing_action = False
                                                st.rerun()
                                            else:
                                                st.session_state.processing_action = False
                                                show_feedback('error', f"Error al mover a oficina: {resp.status_code}", duration=3)


elif st.session_state.menu == "Incidencias":
    st.title("Incidencias en dispositivos")
    legend_button()
    
    actives = preloaded_data['active_incidents']
    pasts = preloaded_data['past_incidents']
    devices = all_devices

    device_map = {d["id"]: d for d in devices}

    incidents_by_device = {}
    
    for inc in actives:
        did = inc.get("Device")
        if not did:
            continue
        incidents_by_device.setdefault(did, {"active": [], "past": []})
        incidents_by_device[did]["active"].append(inc)

    for inc in pasts:
        did = inc.get("Device")
        if not did:
            continue
        incidents_by_device.setdefault(did, {"active": [], "past": []})
        incidents_by_device[did]["past"].append(inc)

    total_active = sum(len(v["active"]) for v in incidents_by_device.values())

    with st.expander(f"Incidencias en dispositivos ({total_active} activas)", expanded=True):
        
        devices_with_incidents = [
        device_map[did] for did in incidents_by_device.keys() if did in device_map
    ]

        # 🔍 BUSCADOR DINÁMICO (PÉGALO AQUÍ)
        search_query = st.text_input(
            "Buscar dispositivo...",
            placeholder="Ej: Quest 3, Quest 2, Vision Pro...",
            key="inc_dynamic_search"
        )

        if search_query:
            q = search_query.lower().strip()
            devices_with_incidents = [
                d for d in devices_with_incidents 
                if q in d["Name"].lower()
            ]

        # 👉 EL FILTRO SEGMENTADO VA DESPUÉS — NO LO MUEVAS
        devices_filtered, selected_group = smart_segmented_filter(
            devices_with_incidents, 
            key_prefix="incidents_filter",
            show_red_for_active=True,
            incidence_map=incidence_map
        )

        
        filtered_device_ids = {d["id"] for d in devices_filtered}
        filtered_incidents_by_device = {
            did: lists for did, lists in incidents_by_device.items() 
            if did in filtered_device_ids
        }
        
        total_active_filtered = sum(len(v["active"]) for v in filtered_incidents_by_device.values())

        if not filtered_incidents_by_device:
            st.info("No hay incidencias registradas para este tipo de dispositivo.")
        else:
            all_incidents_list = []
            for did, lists in filtered_incidents_by_device.items():
                dev = device_map.get(did)
                dev_name = dev["Name"] if dev else "Dispositivo desconocido"
                
                active_sorted = sorted(
                    lists["active"], key=lambda x: x.get("Created") or "", reverse=True
                )
                for inc in active_sorted:
                    all_incidents_list.append({
                        "type": "active",
                        "dev_name": dev_name,
                        "inc": inc
                    })
                
                past_sorted = sorted(
                    lists["past"], key=lambda x: x.get("Created") or "", reverse=True
                )
                for inc in past_sorted:
                    all_incidents_list.append({
                        "type": "past",
                        "dev_name": dev_name,
                        "inc": inc
                    })
            
            with st.container(height=500, border=True):
                for item in all_incidents_list:
                    inc = item["inc"]
                    dev_name = item["dev_name"]
                    inc_type = item["type"]
                    
                    if inc_type == "active":
                        notes = inc.get("Notes", "").replace("<", "&lt;").replace(">", "&gt;")
                        created = fmt_datetime(inc.get("Created"))

                        cols = st.columns([8, 2])
                        with cols[0]:
                            st.markdown(
                                f"""<div style='margin-left:20px;margin-bottom:10px;padding:8px;background:#FFEBEE;border-radius:4px;'><div style='display:flex;align-items:center;margin-bottom:4px;'><div style='width:10px;height:10px;background:#E53935;border-radius:50%;margin-right:8px;'></div><strong style='font-size:14px;color:#333;'>{dev_name}</strong><span style='margin:0 6px;color:#AAA;'>|</span><strong style='font-size:14px;color:#333;'>{inc['Name']}</strong><span style='margin-left:8px;color:#888;font-size:12px;'>{created}</span></div><div style='margin-left:18px;color:#666;font-size:13px;'>{notes if notes else '<em>Sin notas</em>'}</div></div>""",
                                unsafe_allow_html=True
                            )

                        with cols[1]:
                            if st.button("Resolver", key=f"resolve_{inc['id']}", use_container_width=True):
                                st.session_state.solve_inc = inc
                                st.session_state.force_incidents_tab = True
                                st.rerun()
                    
                    else:
                        notes = inc.get("Notes", "").replace("<", "&lt;").replace(">", "&gt;")
                        created = fmt_datetime(inc.get("Created"))
                        resolved = fmt_datetime(inc.get("Resolved"))

                        rnotes = inc.get("ResolutionNotes", "")
                        rnotes_html = ""
                        if rnotes:
                            rnotes = rnotes.replace("<", "&lt;").replace(">", "&gt;")
                            rnotes_html = f"<div style='margin-left:18px;color:#4CAF50;font-size:13px;margin-top:4px;'>{rnotes}</div>"

                        st.markdown(
                            f"""<div style='margin-left:20px;margin-bottom:10px;padding:8px;background:#F5F5F5;border-radius:4px;'><div style='display:flex;align-items:center;margin-bottom:4px;'><div style='width:10px;height:10px;background:#9E9E9E;border-radius:50%;margin-right:8px;'></div><strong style='font-size:14px;color:#555;'>{dev_name}</strong><span style='margin:0 6px;color:#AAA;'>|</span><strong style='font-size:14px;color:#555;'>{inc['Name']}</strong><span style='margin-left:8px;color:#888;font-size:12px;'>Creada: {created} → Resuelta: {resolved}</span></div><div style='margin-left:18px;color:#666;font-size:13px;'>{notes if notes else '<em>Sin notas</em>'}</div>{rnotes_html}</div>""",
                            unsafe_allow_html=True
                        )

    if "solve_inc" not in st.session_state:
        st.session_state.solve_inc = None

    if st.session_state.solve_inc:
        inc = st.session_state.solve_inc

        with st.sidebar:
            st.header("Resolver incidencia")
            st.write(f"**{inc['Name']}**")
            st.caption(f"Creada: {fmt_datetime(inc.get('Created'))}")

            if inc.get("Notes"):
                st.caption(f"Notas: {inc['Notes']}")

            col_date, col_time = st.columns(2)

            with col_date:
                resolved_date = st.date_input("Fecha de resolución", value=date.today())

            with col_time:
                resolved_time = st.time_input("Hora de resolución", value=datetime.now().time())

            rnotes = st.text_area("Notas de resolución")

            col1, col2 = st.columns(2)

            with col1:
                if st.button("Confirmar", use_container_width=True):

                    feedback = st.empty()
                    with feedback:
                        with st.spinner("Resolviendo incidencia..."):

                            resolved_datetime = datetime.combine(resolved_date, resolved_time)
                            resolved_iso = resolved_datetime.isoformat()

                            properties = {
                                "Name": {"title": [{"text": {"content": inc["Name"]}}]},
                                "Device": {"relation": [{"id": inc["Device"]}]},
                                "Created Date": {"date": {"start": inc.get("Created")}},
                                "Notes": {"rich_text": [{"text": {"content": inc.get("Notes", "")}}]},
                                "Resolved Date": {"date": {"start": resolved_iso}},
                            }

                            if rnotes:
                                properties["Resolution Notes"] = {
                                    "rich_text": [{"text": {"content": rnotes}}]
                                }

                            r1 = requests.post(
                                "https://api.notion.com/v1/pages",
                                headers=headers,
                                json={"parent": {"database_id": PAST_INC_ID}, "properties": properties}
                            )

                            if r1.status_code == 200:
                                r2 = requests.patch(
                                    f"https://api.notion.com/v1/pages/{inc['id']}",
                                    headers=headers,
                                    json={"archived": True}
                                )

                                if r2.status_code == 200:
                                    st.session_state.solve_inc = None
                                    st.session_state.add_new_incident_expander = False
                                    st.session_state.force_incidents_tab = True
                                    
                                    load_active_incidents.clear()
                                    load_past_incidents.clear()
                                    load_incidence_map.clear()
                                    q.clear()
                                    preload_all_data.clear()

                                    feedback.empty()
                                    show_feedback("success", "Incidencia resuelta", duration=1.5)
                                    time.sleep(1.5)
                                    st.rerun()

                                else:
                                    feedback.empty()
                                    show_feedback("error", f"Error al archivar incidencia: {r2.status_code}", duration=3)

                            else:
                                feedback.empty()
                                show_feedback("error", f"Error al crear incidencia resuelta: {r1.status_code}", duration=3)

            with col2:
                if st.button("Cancelar", use_container_width=True):
                    st.session_state.solve_inc = None
                    st.rerun()

    add_new_expanded = st.session_state.get("add_new_incident_expander", False)

    with st.expander("Añadir nueva incidencia", expanded=add_new_expanded):

        devices_with_location = [
            d for d in devices 
            if d.get("location_ids") and len(d["location_ids"]) > 0
        ]

        devices_filtered_new, _ = smart_segmented_filter(devices_with_location, key_prefix="new_inc")

        sel_keys = []

        with st.container(height=300, border=True):
            for d in devices_filtered_new:
                key = f"newinc_{d['id']}"
                sel_keys.append(key)

                cols = st.columns([0.5, 9.5])

                with cols[0]:
                    st.checkbox("", key=key)

                with cols[1]:
                    inc = incidence_map.get(d["id"], {"active": 0, "total": 0})
                    subtitle = get_location_types_for_device(d, locations_map)
                    card(
                        d["Name"],
                        location_types=subtitle,
                        incident_counts=(inc["active"], inc["total"])
                    )

        selected_devices = [
            key.split("_")[1] for key in sel_keys if st.session_state.get(key, False)
        ]

        with st.sidebar:
            if selected_devices:
                counter_badge(len(selected_devices), len(devices_filtered_new))

                name = st.text_input("Título incidencia", key="new_inc_name")
                notes = st.text_area("Notas", key="new_inc_notes")

                if st.button("Crear incidencia", use_container_width=True):

                    if not name or name.strip() == "":
                        show_feedback("error", "Debes poner un título", duration=2)

                    else:
                        feedback = st.empty()
                        with feedback:
                            with st.spinner("Creando incidencia..."):
                                now = datetime.now().isoformat()
                                ok = True

                                for did in selected_devices:
                                    payload = {
                                        "parent": {"database_id": ACTIVE_INC_ID},
                                        "properties": {
                                            "Name": {"title": [{"text": {"content": name}}]},
                                            "Device": {"relation": [{"id": did}]},
                                            "Notes": {"rich_text": [{"text": {"content": notes}}]},
                                            "Created Date": {"date": {"start": now}},
                                        },
                                    }

                                    r = requests.post(
                                        "https://api.notion.com/v1/pages",
                                        headers=headers,
                                        json=payload,
                                    )

                                    if r.status_code != 200:
                                        ok = False
                                        feedback.empty()
                                        show_feedback("error", f"Error: {r.status_code}", duration=3)
                                        break

                                if ok:
                                    for key in sel_keys:
                                        if key in st.session_state:
                                            del st.session_state[key]

                                    if "new_inc_name" in st.session_state:
                                        del st.session_state["new_inc_name"]
                                    if "new_inc_notes" in st.session_state:
                                        del st.session_state["new_inc_notes"]

                                    st.session_state.add_new_incident_expander = False
                                    st.session_state.force_incidents_tab = True
                                    
                                    load_active_incidents.clear()
                                    load_incidence_map.clear()
                                    q.clear()
                                    preload_all_data.clear()

                                    feedback.empty()
                                    show_feedback("success", "Incidencia creada", duration=1.5)
                                    time.sleep(1.5)
                                    st.rerun()