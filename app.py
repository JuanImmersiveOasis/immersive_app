import streamlit as st
import requests
from datetime import datetime, date, timedelta
import os
from dotenv import load_dotenv
import time

load_dotenv()

# ============================================================
# CONFIGURACIÓN INICIAL
# ============================================================
st.set_page_config(page_title="Logistica", page_icon=None, layout="wide")

# ============================================================
# CREDENCIALES Y CONFIGURACIÓN DE NOTION
# ============================================================
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

# ============================================================
# ORDEN PREFERIDO DE TAGS
# ============================================================
# Esta lista define el orden en que queremos mostrar los tipos de gafas
# Si aparece un tipo nuevo que no está aquí, se añadirá al final alfabéticamente
PREFERRED_TAG_ORDER = ["Ultra", "Neo 4", "Quest 2", "Quest 3", "Quest 3S", "Vision Pro"]

# ============================================================
# CONTENEDOR PARA FEEDBACK EN SIDEBAR
# ============================================================

def show_feedback(message_type, message, duration=None):
    """
    Muestra feedback en el sidebar con ancho completo
    message_type: 'success', 'error', 'warning', 'info', 'spinner'
    """
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

# ============================================================
# SISTEMA DE CACHÉ MEJORADO CON TTL
# ============================================================

class CacheManager:
    def __init__(self):
        if 'cache_store' not in st.session_state:
            st.session_state.cache_store = {}
    
    def get(self, key, default=None):
        cache = st.session_state.cache_store.get(key)
        if not cache:
            return default
        elapsed = time.time() - cache['timestamp']
        if elapsed > cache['ttl']:
            del st.session_state.cache_store[key]
            return default
        return cache['data']
    
    def set(self, key, data, ttl=300):
        st.session_state.cache_store[key] = {
            'data': data,
            'timestamp': time.time(),
            'ttl': ttl
        }
    
    def invalidate(self, *keys):
        for key in keys:
            if key in st.session_state.cache_store:
                del st.session_state.cache_store[key]
    
    def clear_all(self):
        st.session_state.cache_store = {}

cache_mgr = CacheManager()

# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

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

def q(db, payload=None, use_cache=True, cache_ttl=300):
    if payload is None:
        payload = {"page_size": 100}
    
    cache_key = f"query_{db}_{str(payload)}"
    
    if use_cache:
        cached = cache_mgr.get(cache_key)
        if cached is not None:
            return cached
    
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
    
    if use_cache:
        cache_mgr.set(cache_key, results, ttl=cache_ttl)
    
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
    cache_mgr.invalidate('devices', 'future_locations', 'inhouse')
    return response

# ============================================================
# COMPONENTES DE UI
# ============================================================

def legend_button():
    """
    Crea un botón de ayuda (?) que muestra la leyenda al hacer hover
    Se coloca alineado a la derecha
    """
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
            # Si hay incidencias activas, cambiar borde y color de texto a rojo
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

# ============================================================
# FUNCIONES DE CARGA DE DATOS
# ============================================================

def load_locations_map():
    cached = cache_mgr.get('locations_map')
    if cached is not None:
        return cached
    
    results = q(LOCATIONS_ID, cache_ttl=600)
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
    
    cache_mgr.set('locations_map', out, ttl=600)
    return out

def load_devices():
    cached = cache_mgr.get('devices')
    if cached is not None:
        return cached
    
    results = q(DEVICES_ID, cache_ttl=300)
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
    cache_mgr.set('devices', out, ttl=300)
    return out

def load_future_client_locations():
    cached = cache_mgr.get('future_locations')
    if cached is not None:
        return cached
    
    today = date.today()
    results = q(LOCATIONS_ID, cache_ttl=300)
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
    
    cache_mgr.set('future_locations', out, ttl=300)
    return out

def load_inhouse():
    cached = cache_mgr.get('inhouse')
    if cached is not None:
        return cached
    
    results = q(LOCATIONS_ID, {"filter": {"property": "Type", "select": {"equals": "In House"}}}, cache_ttl=600)
    out = []
    
    for p in results:
        try:
            name = p["properties"]["Name"]["title"][0]["text"]["content"]
        except:
            name = "Sin nombre"
        
        out.append({"id": p["id"], "name": name})
    
    cache_mgr.set('inhouse', out, ttl=600)
    return out

def office_id():
    cached = cache_mgr.get('office_id')
    if cached is not None:
        return cached
    
    r = q(LOCATIONS_ID, {"filter": {"property": "Name", "title": {"equals": "Office"}}}, cache_ttl=600)
    oid = r[0]["id"] if r else None
    
    cache_mgr.set('office_id', oid, ttl=600)
    return oid

def load_active_incidents():
    cached = cache_mgr.get('active_incidents')
    if cached is not None:
        return cached
    
    r = q(ACTIVE_INC_ID, cache_ttl=180)
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
    
    cache_mgr.set('active_incidents', out, ttl=180)
    return out

def load_past_incidents():
    cached = cache_mgr.get('past_incidents')
    if cached is not None:
        return cached
    
    r = q(PAST_INC_ID, cache_ttl=300)
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
    
    cache_mgr.set('past_incidents', out, ttl=300)
    return out

def load_incidence_map():
    cached = cache_mgr.get('incidence_map')
    if cached is not None:
        return cached
    
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
    
    cache_mgr.set('incidence_map', m, ttl=180)
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

# ============================================================
# SEGMENTADOR INTELIGENTE - FUNCIÓN HELPER PRINCIPAL
# ============================================================

def smart_segmented_filter(devices, key_prefix, tag_field="Tags", show_red_for_active=False, incidence_map=None):
    """
    Crea un segmentador inteligente que:
    1. Detecta automáticamente qué tags existen en los dispositivos
    2. Solo muestra botones de tags que tienen dispositivos
    3. Ordena según PREFERRED_TAG_ORDER (tags nuevos al final alfabéticamente)
    4. Opcionalmente muestra en rojo si hay incidencias activas
    
    Parámetros:
    -----------
    devices : list
        Lista de dispositivos a filtrar
    key_prefix : str
        Prefijo único para el widget (ej: "tab1", "inhouse")
    tag_field : str
        Campo a usar para filtrar (por defecto "Tags")
    show_red_for_active : bool
        Si True, muestra en rojo el contador cuando hay incidencias activas
    incidence_map : dict
        Mapa de incidencias {device_id: {"active": n, "total": m}}
    
    Retorna:
    --------
    tuple : (devices_filtered, selected_group)
        - devices_filtered: Lista de dispositivos del grupo seleccionado
        - selected_group: Nombre del grupo seleccionado ("Todas" o nombre del tag)
    """
    
    # PASO 1: Extraer todos los tags únicos que existen en los dispositivos
    present_tags = {d.get(tag_field) for d in devices if d.get(tag_field)}
    
    # PASO 2: Ordenar los tags según el orden preferido
    # Los tags que están en PREFERRED_TAG_ORDER van primero en ese orden
    # Los tags nuevos (no en la lista) se añaden al final alfabéticamente
    ordered_tags = []
    
    # Añadir primero los tags conocidos que existen
    for preferred_tag in PREFERRED_TAG_ORDER:
        if preferred_tag in present_tags:
            ordered_tags.append(preferred_tag)
    
    # Añadir tags nuevos que no están en la lista preferida
    new_tags = sorted([tag for tag in present_tags if tag not in PREFERRED_TAG_ORDER])
    ordered_tags.extend(new_tags)
    
    # PASO 3: Calcular contadores para cada grupo
    if show_red_for_active and incidence_map:
        # Para incidencias: contar activas y totales
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
        # Para dispositivos normales: contar cantidad
        counts = {"Todas": len(devices)}
        for tag in ordered_tags:
            counts[tag] = sum(1 for d in devices if d.get(tag_field) == tag)
    
    # PASO 4: Crear opciones del segmentador
    opciones_display = []
    opciones_map = {}
    
    # Opción "Todas"
    if show_red_for_active and incidence_map:
        if counts_active["Todas"] > 0:
            label_all = f"Todas :red[({counts_active['Todas']})]"
        else:
            label_all = f"Todas ({counts_active['Todas']})"
    else:
        label_all = f"Todas ({counts['Todas']})"
    
    opciones_display.append(label_all)
    opciones_map[label_all] = "Todas"
    
    # Opciones por tag (solo los que existen)
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
    
    # PASO 5: Mostrar el segmentador
    sel_label = st.segmented_control(
        label=None,
        options=opciones_display,
        default=opciones_display[0],
        key=f"{key_prefix}_seg"
    )
    
    # Validar selección
    if sel_label not in opciones_map:
        sel_label = opciones_display[0]
        st.session_state[f"{key_prefix}_seg"] = sel_label
    
    selected_group = opciones_map[sel_label]
    
    # PASO 6: Filtrar dispositivos según la selección
    if selected_group == "Todas":
        filtered = devices
    else:
        filtered = [d for d in devices if d.get(tag_field) == selected_group]
    
    return filtered, selected_group

# ============================================================
# INICIALIZAR SESSION STATE
# ============================================================

for key, default in [
    ("tab1_show", False), 
    ("sel1", []), 
    ("sel2", []),
    ("sel3", []), 
    ("tab3_loc", None), 
    ("show_avail_tab3", False),
    ("show_avail_home", False)
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ============================================================
# SIDEBAR - NAVEGACIÓN
# ============================================================

with st.sidebar:
    # Logo completo que ocupa todo el ancho
    st.image("img/logo.png", use_container_width=True)
    
    try:
        num_proximos = len(load_future_client_locations())
    except:
        num_proximos = 0
    
    today = date.today()
    all_locs = q(LOCATIONS_ID, cache_ttl=300)
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
    
    try:
        actives_nav = load_active_incidents()
        num_incidencias = len(actives_nav)
    except:
        num_incidencias = 0
    
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
    
    selected_label = st.radio(
        label="nav",
        options=opciones_menu,
        label_visibility="collapsed",
        key="nav_radio"
    )
    
    st.session_state.menu = menu_mapping[selected_label]
    
    st.markdown("----")
    
    if st.button("Refrescar", use_container_width=True):
        cache_mgr.clear_all()
        st.rerun()

locations_map = load_locations_map()
incidence_map = load_incidence_map()

# ============================================================
# PANTALLA 1: DISPONIBLES PARA ALQUILAR
# ============================================================

if st.session_state.menu == "Disponibles para Alquilar":
    st.title("Disponibles para Alquilar")
    # Botón de leyenda alineado a la derecha
    legend_button()
    
    c1, c2 = st.columns(2)
    with c1:
        start = st.date_input("Fecha inicio", date.today())
    with c2:
        end = st.date_input("Fecha fin", date.today())
    
    if st.button("Comprobar disponibilidad"):
        st.session_state.tab1_show = True
        st.session_state.sel1 = []
        for key in list(st.session_state.keys()):
            if key.startswith("a_"):
                del st.session_state[key]
    
    if st.session_state.tab1_show:
        devices = load_devices()
        
        avail = [
            d for d in devices
            if d.get("location_ids") and available(d, start, end)
        ]
        
        # Segmentador fuera del contenedor con scroll
        avail_filtered, _ = smart_segmented_filter(avail, key_prefix="tab1")
        
       
        
        # Contenedor con scroll para las cards
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
                                        
                                        # Limpiar selección
                                        st.session_state.sel1 = []
                                        for key in list(st.session_state.keys()):
                                            if key.startswith("a_"):
                                                del st.session_state[key]
                                        
                                        # Borrar TODOS los cachés
                                        cache_mgr.clear_all()
                                        
                                        # Mostrar feedback
                                        feedback_placeholder.empty()
                                        show_feedback('success', f"{success_count} dispositivos asignados correctamente", duration=1.5)
                                        
                                        # Esperar y recargar
                                        time.sleep(1.5)
                                        st.rerun()
                                    else:
                                        feedback_placeholder.empty()
                                        show_feedback('error', f"Error al crear ubicación: {response.status_code}", duration=3)

# ============================================================
# PANTALLA 2: GAFAS EN CASA
# ============================================================

elif st.session_state.menu == "Gafas en casa":
    st.title("Gafas en casa")
    # Botón de leyenda
    legend_button()
    
    # SIEMPRE cargar datos frescos si no existen
    if "devices_live" not in st.session_state:
        st.session_state.devices_live = load_devices()
    
    devices = st.session_state.devices_live
    inh = load_inhouse()
    oid = office_id()
    
    inh_ids = [p["id"] for p in inh]
    
    inhouse_devices = [
        d for d in devices
        if any(l in inh_ids for l in d["location_ids"])
    ]
    
    with st.expander("Personal con dispositivos en casa", expanded=True):
        # Segmentador fuera del contenedor con scroll
        inhouse_filtered, _ = smart_segmented_filter(inhouse_devices, key_prefix="inhouse")
        
        
        
        people_devices = {p["id"]: [] for p in inh}
        for d in inhouse_filtered:
            for lid in d["location_ids"]:
                if lid in people_devices:
                    people_devices[lid].append(d)
        
        people_with_devices = [
            p for p in inh if len(people_devices[p["id"]]) > 0
        ]
        
        # Contenedor con scroll
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
                                with st.sidebar:
                                    feedback_placeholder = st.empty()
                                    with feedback_placeholder:
                                        with st.spinner("Moviendo a oficina..."):
                                            resp = assign_device(d["id"], oid)
                                            
                                            if resp.status_code == 200:
                                                # Borrar TODOS los cachés
                                                cache_mgr.clear_all()
                                                
                                                # Borrar devices_live
                                                if 'devices_live' in st.session_state:
                                                    del st.session_state['devices_live']
                                                
                                                # Mostrar feedback
                                                feedback_placeholder.empty()
                                                show_feedback('success', "Movido a oficina", duration=1.5)
                                                
                                                # Esperar MÁS tiempo para que Notion actualice
                                                time.sleep(1.5)
                                                st.rerun()
                                            else:
                                                feedback_placeholder.empty()
                                                show_feedback('error', f"Error: {resp.status_code}", duration=2)
    
    office_devices = [
        d for d in devices
        if oid in d["location_ids"]
    ]
    
    expander_office_open = st.session_state.get("expander_office_open", False)
    
    with st.expander("Otras gafas disponibles en oficina", expanded=expander_office_open):
        st.session_state.expander_office_open = True
        
        # Segmentador fuera del contenedor con scroll
        office_filtered, _ = smart_segmented_filter(office_devices, key_prefix="office")
        
        # Contenedor con scroll
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
                            
                            # Limpiar selección
                            st.session_state.sel2 = []
                            for key in list(st.session_state.keys()):
                                if key.startswith("o_"):
                                    del st.session_state[key]
                            
                            # Cerrar expander
                            st.session_state.expander_office_open = False
                            
                            # Borrar TODOS los cachés
                            cache_mgr.clear_all()
                            
                            # Borrar devices_live
                            if 'devices_live' in st.session_state:
                                del st.session_state['devices_live']
                            
                            # Feedback y rerun
                            feedback_placeholder.empty()
                            show_feedback('success', f"{success_count} dispositivos asignados", duration=1.5)
                            time.sleep(1.5)
                            st.rerun()
    
    if not expander_office_open:
        st.session_state.expander_office_open = False

# ============================================================
# PANTALLA 3: PRÓXIMOS ENVÍOS
# ============================================================

elif st.session_state.menu == "Próximos Envíos":
    st.title("Próximos Envíos")
    # Botón de leyenda
    legend_button()
    
    future_locs = load_future_client_locations()
    
    with st.expander(f"Envíos futuros ({len(future_locs)})", expanded=True):
        if len(future_locs) == 0:
            st.info("No hay envíos futuros.")
            st.stop()
        
        for loc in future_locs:
            lname = loc["name"]
            start = fmt(loc["start"])
            end = fmt(loc["end"])
            loc_id = loc["id"]
            
            devices = load_devices()
            
            expander_key = f"expander_loc_{loc_id}"
            is_expanded = st.session_state.get(expander_key, False)
            
            with st.expander(f"{lname} ({start} → {end})", expanded=is_expanded):
                st.session_state[expander_key] = True
                
                assigned = [
                    d for d in devices
                    if loc_id in d["location_ids"]
                ]
                
                st.subheader("Dispositivos asignados")
                
                # Segmentador fuera del contenedor
                assigned_filtered, _ = smart_segmented_filter(assigned, key_prefix=f"assigned_{loc_id}")
                
                # Contenedor con scroll
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
                                with st.sidebar:
                                    feedback_placeholder = st.empty()
                                    with feedback_placeholder:
                                        with st.spinner("Quitando dispositivo..."):
                                            resp = assign_device(d["id"], office_id())
                                            
                                            if resp.status_code == 200:
                                                # Borrar TODOS los cachés
                                                cache_mgr.clear_all()
                                                
                                                # Mostrar feedback
                                                feedback_placeholder.empty()
                                                show_feedback('success', "Dispositivo quitado", duration=1.5)
                                                
                                                # Mantener expander abierto
                                                st.session_state[expander_key] = True
                                                
                                                # Esperar y recargar
                                                time.sleep(1.5)
                                                st.rerun()
                                            else:
                                                feedback_placeholder.empty()
                                                show_feedback('error', f"Error: {resp.status_code}", duration=2)
                
                add_expander_key = f"add_expander_{loc_id}"
                add_expanded = st.session_state.get(add_expander_key, False)
                
                with st.expander("Más gafas disponibles", expanded=add_expanded):
                    st.session_state[add_expander_key] = True
                    
                    ls = iso_to_date(loc["start"])
                    le = iso_to_date(loc["end"])
                    
                    can_add = [
                        d for d in devices
                        if d.get("location_ids")
                        and available(d, ls, le)
                        and loc_id not in d["location_ids"]
                    ]
                    
                    # Segmentador fuera del contenedor
                    can_add_filtered, _ = smart_segmented_filter(can_add, key_prefix=f"canadd_{loc_id}")
                    
                    checkbox_keys = []
                    
                    # Contenedor con scroll
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
                        with st.sidebar:
                            counter_badge(sel_count, len(can_add_filtered))
                            
                            if st.button(f"Añadir a {lname}", key=f"assign_btn_{loc_id}", use_container_width=True):
                                feedback_placeholder = st.empty()
                                with feedback_placeholder:
                                    with st.spinner("Añadiendo dispositivos..."):
                                        success_count = 0
                                        for did in selected_ids:
                                            resp = assign_device(did, loc_id)
                                            if resp.status_code == 200:
                                                success_count += 1
                                        
                                        # Limpiar checkboxes
                                        for key in checkbox_keys:
                                            if key in st.session_state:
                                                del st.session_state[key]
                                        
                                        # Borrar TODOS los cachés
                                        cache_mgr.clear_all()
                                        
                                        # Configurar estados de expanders
                                        st.session_state[expander_key] = True
                                        st.session_state[add_expander_key] = False
                                        
                                        # Mostrar feedback
                                        feedback_placeholder.empty()
                                        show_feedback('success', f"{success_count} dispositivos añadidos", duration=1.5)
                                        
                                        # Esperar y recargar
                                        time.sleep(1.5)
                                        st.rerun()
                
                if not add_expanded:
                    st.session_state[add_expander_key] = False
            
            if not is_expanded:
                st.session_state[expander_key] = False

# ============================================================
# PANTALLA 4: CHECK-IN
# ============================================================

elif st.session_state.menu == "Check-In":
    st.title("Check-In de Gafas")
    
    today = date.today()
    all_locs = q(LOCATIONS_ID, cache_ttl=300)
    devices = load_devices()
    
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
            
            # Contenedor con scroll
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
                            with st.sidebar:
                                feedback_placeholder = st.empty()
                                with feedback_placeholder:
                                    with st.spinner("Procesando Check-In..."):
                                        # PASO 1: Crear registro en histórico
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
                                            feedback_placeholder.empty()
                                            show_feedback('error', f"Error al registrar en histórico: {r.status_code}", duration=3)
                                        else:
                                            # PASO 2: Mover dispositivo a oficina
                                            resp = assign_device(d["id"], office)
                                            
                                            if resp.status_code == 200:
                                                # PASO 3: Borrar TODOS los cachés
                                                cache_mgr.clear_all()
                                                
                                                # PASO 4: Mostrar feedback
                                                feedback_placeholder.empty()
                                                show_feedback('success', "Check-In completado", duration=1.5)
                                                
                                                # PASO 5: Esperar y recargar
                                                time.sleep(1.5)
                                                st.rerun()
                                            else:
                                                feedback_placeholder.empty()
                                                show_feedback('error', f"Error al mover a oficina: {resp.status_code}", duration=3)

                                                
# ============================================================
# PANTALLA 5: INCIDENCIAS
# ============================================================

elif st.session_state.menu == "Incidencias":
    st.title("Incidencias de dispositivos")
    
    # Cargar incidencias
    actives = load_active_incidents()
    pasts = load_past_incidents()
    devices = load_devices()

    # Crear mapa de dispositivos (solo nombre y referencia)
    device_map = {d["id"]: d for d in devices}

    # Estructurar incidencias por dispositivo
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

    # Calcular total activas
    total_active = sum(len(v["active"]) for v in incidents_by_device.values())

    # ============================================================
    # EXPANDER 1 – LISTADO DE INCIDENCIAS (SIEMPRE ABIERTO)
    # ============================================================

    with st.expander(f"Incidencias en dispositivos ({total_active} activas)", expanded=True):
        
        # Obtener todos los dispositivos con incidencias
        devices_with_incidents = [device_map[did] for did in incidents_by_device.keys() if did in device_map]
        
        # Segmentador fuera del contenedor
        devices_filtered, selected_group = smart_segmented_filter(
            devices_with_incidents, 
            key_prefix="incidents_filter",
            show_red_for_active=True,
            incidence_map=incidence_map
        )
        
        # Filtrar incidents_by_device según los dispositivos filtrados
        filtered_device_ids = {d["id"] for d in devices_filtered}
        filtered_incidents_by_device = {
            did: lists for did, lists in incidents_by_device.items() 
            if did in filtered_device_ids
        }
        
        # Resetear a página 1 cuando cambia el filtro
        if "last_selected_group" not in st.session_state:
            st.session_state.last_selected_group = selected_group
        elif st.session_state.last_selected_group != selected_group:
            st.session_state.incidents_current_page = 1
            st.session_state.last_selected_group = selected_group
        
        # Recalcular total activas después del filtro
        total_active_filtered = sum(len(v["active"]) for v in filtered_incidents_by_device.values())

        if not filtered_incidents_by_device:
            st.info("No hay incidencias registradas para este tipo de dispositivo.")
        else:
            # ============================================================
            # PREPARAR LISTA DE INCIDENCIAS PARA PAGINAR
            # ============================================================
            
            # Crear lista de todas las incidencias para paginar
            all_incidents_list = []
            for did, lists in filtered_incidents_by_device.items():
                dev = device_map.get(did)
                dev_name = dev["Name"] if dev else "Dispositivo desconocido"
                
                # Añadir incidencias activas
                active_sorted = sorted(
                    lists["active"], key=lambda x: x.get("Created") or "", reverse=True
                )
                for inc in active_sorted:
                    all_incidents_list.append({
                        "type": "active",
                        "dev_name": dev_name,
                        "inc": inc
                    })
                
                # Añadir incidencias pasadas
                past_sorted = sorted(
                    lists["past"], key=lambda x: x.get("Created") or "", reverse=True
                )
                for inc in past_sorted:
                    all_incidents_list.append({
                        "type": "past",
                        "dev_name": dev_name,
                        "inc": inc
                    })
            
            # ============================================================
            # CONFIGURACIÓN DEL PAGINADOR
            # ============================================================
            
            items_per_page = 10  # Número de incidencias por página
            total_items = len(all_incidents_list)
            total_pages = max(1, (total_items + items_per_page - 1) // items_per_page)
            
            # Inicializar página actual en session_state
            if "incidents_current_page" not in st.session_state:
                st.session_state.incidents_current_page = 1
            
            # Asegurarse de que la página actual esté dentro del rango válido
            if st.session_state.incidents_current_page > total_pages:
                st.session_state.incidents_current_page = 1
            
            # Calcular índices para la página actual
            start_idx = (st.session_state.incidents_current_page - 1) * items_per_page
            end_idx = start_idx + items_per_page
            
            # Obtener incidencias de la página actual
            current_page_incidents = all_incidents_list[start_idx:end_idx]
            
            # ============================================================
            # MOSTRAR INCIDENCIAS DE LA PÁGINA ACTUAL (CON SCROLL)
            # ============================================================
            
            with st.container( border=True):
                for item in current_page_incidents:
                    inc = item["inc"]
                    dev_name = item["dev_name"]
                    inc_type = item["type"]
                    
                    if inc_type == "active":
                        # ============================================================
                        # INCIDENCIAS ACTIVAS (ROJO)
                        # ============================================================
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
                                st.rerun()
                    
                    else:
                        # ============================================================
                        # INCIDENCIAS PASADAS (GRIS)
                        # ============================================================
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
            
            # ============================================================
            # PAGINADOR CON NÚMEROS (ABAJO A LA DERECHA)
            # ============================================================
            
            if total_pages > 1:
                st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
                # Botón de leyenda
                legend_button()
                
                # Crear contenedor alineado a la derecha
                col_spacer, col_pagination = st.columns([8, 2])
                
                with col_pagination:
                    # Determinar qué páginas mostrar
                    max_visible_pages = 5  # Número máximo de botones de página visibles
                    
                    # Calcular rango de páginas a mostrar
                    if total_pages <= max_visible_pages:
                        page_range = range(1, total_pages + 1)
                    else:
                        # Mostrar páginas alrededor de la página actual
                        start_page = max(1, st.session_state.incidents_current_page - 2)
                        end_page = min(total_pages, start_page + max_visible_pages - 1)
                        
                        # Ajustar si estamos cerca del final
                        if end_page == total_pages:
                            start_page = max(1, end_page - max_visible_pages + 1)
                        
                        page_range = range(start_page, end_page + 1)
                    
                    # Crear botones de página
                    page_buttons = []
                    
                    # Botón "Primera página" si no está visible
                    if 1 not in page_range and total_pages > max_visible_pages:
                        page_buttons.append("1")
                        if min(page_range) > 2:
                            page_buttons.append("...")
                    
                    # Botones de páginas
                    for page_num in page_range:
                        page_buttons.append(str(page_num))
                    
                    # Botón "Última página" si no está visible
                    if total_pages not in page_range and total_pages > max_visible_pages:
                        if max(page_range) < total_pages - 1:
                            page_buttons.append("...")
                        page_buttons.append(str(total_pages))
                    
                    # Crear HTML para los botones
                    buttons_html = "<div style='display:flex;justify-content:flex-end;gap:5px;flex-wrap:wrap;'>"
                    
                    for btn_text in page_buttons:
                        if btn_text == "...":
                            buttons_html += "<span style='padding:6px 10px;color:#999;'>...</span>"
                        else:
                            page_num = int(btn_text)
                            is_current = (page_num == st.session_state.incidents_current_page)
                            
                            bg_color = "#B3E5E6" if is_current else "#E0E0E0"
                            text_color = "#000" if is_current else "#666"
                            cursor = "default" if is_current else "pointer"
                            font_weight = "bold" if is_current else "normal"
                            
                            buttons_html += f"""
                            <div style='padding:6px 12px;background:{bg_color};color:{text_color};
                                        border-radius:4px;cursor:{cursor};font-weight:{font_weight};
                                        user-select:none;min-width:30px;text-align:center;'>
                                {btn_text}
                            </div>
                            """
                    
                    buttons_html += "</div>"
                    
                    st.markdown(buttons_html, unsafe_allow_html=True)
                    
                    # Crear columnas para los botones clicables
                    cols = st.columns(len(page_buttons))
                    
                    for idx, btn_text in enumerate(page_buttons):
                        if btn_text != "...":
                            page_num = int(btn_text)
                            with cols[idx]:
                                if st.button(
                                    " ", 
                                    key=f"page_{page_num}", 
                                    disabled=(page_num == st.session_state.incidents_current_page),
                                    use_container_width=True
                                ):
                                    st.session_state.incidents_current_page = page_num
                                    st.rerun()

    # ============================================================
    # SIDEBAR – RESOLVER INCIDENCIA
    # ============================================================

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

                            # Crear en PAST
                            r1 = requests.post(
                                "https://api.notion.com/v1/pages",
                                headers=headers,
                                json={"parent": {"database_id": PAST_INC_ID}, "properties": properties}
                            )

                            if r1.status_code == 200:
                                # Archivar active
                                r2 = requests.patch(
                                    f"https://api.notion.com/v1/pages/{inc['id']}",
                                    headers=headers,
                                    json={"archived": True}
                                )

                                if r2.status_code == 200:
                                    st.session_state.solve_inc = None
                                    st.session_state.add_new_incident_expander = False

                                    cache_mgr.invalidate(
                                        "active_incidents", "past_incidents", "incidence_map"
                                    )

                                    feedback.empty()
                                    show_feedback("success", "Incidencia resuelta", duration=1)
                                    time.sleep(1)
                                    st.rerun()

                                else:
                                    feedback.empty()
                                    show_feedback("error", f"Error al archivar incidencia: {r2.status_code}")

                            else:
                                feedback.empty()
                                show_feedback("error", f"Error al crear incidencia resuelta: {r1.status_code}")

            with col2:
                if st.button("Cancelar", use_container_width=True):
                    st.session_state.solve_inc = None
                    st.rerun()

    # ============================================================
    # EXPANDER 2 – AÑADIR NUEVA INCIDENCIA
    # ============================================================

    add_new_expanded = st.session_state.get("add_new_incident_expander", False)

    with st.expander("Añadir nueva incidencia", expanded=add_new_expanded):

        # Filtrar solo dispositivos con localización asignada (C, H o O)
        devices_with_location = [
            d for d in devices 
            if d.get("location_ids") and len(d["location_ids"]) > 0
        ]

        # Segmentador fuera del contenedor
        devices_filtered_new, _ = smart_segmented_filter(devices_with_location, key_prefix="new_inc")
        


        sel_keys = []

        # Contenedor con scroll
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
                                        show_feedback("error", f"Error: {r.status_code}")
                                        break

                                if ok:
                                    # Limpiar checkboxes
                                    for key in sel_keys:
                                        st.session_state[key] = False

                                    # Borrar formulario
                                    if "new_inc_name" in st.session_state:
                                        del st.session_state["new_inc_name"]
                                    if "new_inc_notes" in st.session_state:
                                        del st.session_state["new_inc_notes"]

                                    st.session_state.add_new_incident_expander = False
                                    
                                    # Resetear página a 1 cuando se crean nuevas incidencias
                                    st.session_state.incidents_current_page = 1

                                    cache_mgr.invalidate(
                                        "active_incidents", "past_incidents", "incidence_map"
                                    )

                                    feedback.empty()
                                    show_feedback("success", "Incidencia creada", duration=1)
                                    time.sleep(1)
                                    st.rerun()