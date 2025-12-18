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
        return f"el {day_name} pasado, día {day_num}"
    elif days_diff < -7:
        weeks_ago = abs(days_diff) // 7
        if weeks_ago == 1:
            return f"hace una semana, día {day_num}"
        else:
            return f"hace {weeks_ago} semanas, día {day_num}"
    else:
        return f"dentro de {days_diff} días"

def get_shipment_status_icon(loc_id):
    status = st.session_state.get(f"status_{loc_id}", "📋 Planificado")
    return status.split()[0]

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
    load_active_client_locations.clear()
    load_pending_reception_locations.clear()
    load_historic_client_locations.clear()
    q.clear()
    preload_all_data.clear()
    return response

@st.dialog("⚠️ Check-In de dispositivo")
def confirm_checkin(device_name, location_name, device_id, location_id, device_data):
    st.write(f"**Vas a recepcionar el dispositivo:**")
    st.write(f"• Dispositivo: **{device_name}**")
    st.write(f"• Del envío: **{location_name}**")
    st.info("Se registrará en el histórico y volverá a oficina.")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Cancelar", use_container_width=True):
            st.rerun()
    with col2:
        if st.button("Confirmar", use_container_width=True, type="primary"):
            with st.spinner("Procesando Check-In..."):
                payload = {
                    "parent": {"database_id": HISTORIC_ID},
                    "properties": {
                        "Name": {"title": [{"text": {"content": device_data['Name']}}]},
                        "Tags": {"select": {"name": device_data["Tags"]}} if device_data.get("Tags") else None,
                        "SN": {"rich_text": [{"text": {"content": device_data.get("SN", "")}}]},
                        "Location": {"relation": [{"id": location_id}]},
                        "Start Date": {"date": {"start": device_data["Start"]}} if device_data.get("Start") else None,
                        "End Date": {"date": {"start": device_data["End"]}} if device_data.get("End") else None,
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
                    show_feedback('error', f"Error al registrar en histórico: {r.status_code}", duration=3)
                else:
                    resp = assign_device(device_id, office_id())
                    
                    if resp.status_code == 200:
                        st.session_state.keep_almacen_tab = True
                        st.session_state.keep_expander_open = f"expander_pending_loc_{location_id}"
                        
                        load_devices.clear()
                        load_pending_reception_locations.clear()
                        load_historic_client_locations.clear()
                        q.clear()
                        preload_all_data.clear()
                        show_feedback('success', "Check-in completado", duration=1.5)
                        time.sleep(1.5)
                        st.rerun()
                    else:
                        show_feedback('error', f"Error al mover a oficina: {resp.status_code}", duration=3)

@st.dialog("⚠️ Devolver dispositivo a oficina")
def confirm_return_device(device_name, location_name, device_id):
    st.write(f"**Vas a devolver el dispositivo:**")
    st.write(f"• Dispositivo: **{device_name}**")
    st.write(f"• Desde: **{location_name}**")
    st.write(f"• Hacia: **Office**")
    st.info("El dispositivo volverá a estar disponible en oficina.")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Cancelar", use_container_width=True):
            st.rerun()
    with col2:
        if st.button("Confirmar", use_container_width=True, type="primary"):
            with st.spinner("Devolviendo dispositivo..."):
                resp = assign_device(device_id, office_id())
                
                if resp.status_code == 200:
                    load_devices.clear()
                    preload_all_data.clear()
                    show_feedback('success', "Dispositivo devuelto a oficina", duration=1.5)
                    time.sleep(1.5)
                    st.rerun()
                else:
                    show_feedback('error', f"Error: {resp.status_code}", duration=2)

@st.dialog("⚠️ Quitar dispositivo del envío")
def confirm_remove_device(device_name, location_name, device_id):
    st.write(f"**Vas a quitar el dispositivo:**")
    st.write(f"• Dispositivo: **{device_name}**")
    st.write(f"• Del envío: **{location_name}**")
    st.info("El dispositivo volverá a oficina.")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Cancelar", use_container_width=True):
            st.rerun()
    with col2:
        if st.button("Confirmar", use_container_width=True, type="primary"):
            with st.spinner("Quitando dispositivo..."):
                resp = assign_device(device_id, office_id())
                
                if resp.status_code == 200:
                    load_devices.clear()
                    preload_all_data.clear()
                    show_feedback('success', "Dispositivo quitado", duration=1.5)
                    time.sleep(1.5)
                    st.rerun()
                else:
                    show_feedback('error', f"Error: {resp.status_code}", duration=2)

@st.dialog("⚠️ Borrar envío")
def confirm_delete_shipment(location_name, location_id):
    st.write(f"**Vas a eliminar el envío:**")
    st.write(f"• Cliente: **{location_name}**")
    st.warning("Esta acción no se puede deshacer.")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Cancelar", use_container_width=True):
            st.rerun()
    with col2:
        if st.button("Confirmar eliminación", use_container_width=True, type="primary"):
            with st.spinner("Eliminando envío..."):
                delete_response = requests.patch(
                    f"https://api.notion.com/v1/pages/{location_id}",
                    headers=headers,
                    json={"archived": True}
                )
                
                if delete_response.status_code == 200:
                    load_future_client_locations.clear()
                    q.clear()
                    preload_all_data.clear()
                    show_feedback('success', "Envío eliminado", duration=1.5)
                    time.sleep(1.5)
                    st.rerun()
                else:
                    show_feedback('error', f"Error al eliminar: {delete_response.status_code}", duration=3)

@st.dialog("⚠️ Terminar envío")
def confirm_end_shipment(location_name, device_count, location_id):
    st.write(f"**Vas a finalizar el envío:**")
    st.write(f"• Cliente: **{location_name}**")
    st.write(f"• Dispositivos: **{device_count}**")
    st.write(f"• Nueva fecha fin: **{date.today().strftime('%d/%m/%Y')}**")
    st.info("El envío pasará a 'Pendientes de recepcionar'.")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Cancelar", use_container_width=True):
            st.rerun()
    with col2:
        if st.button("Confirmar", use_container_width=True, type="primary"):
            with st.spinner("Finalizando envío..."):
                update_response = requests.patch(
                    f"https://api.notion.com/v1/pages/{location_id}",
                    headers=headers,
                    json={
                        "properties": {
                            "End Date": {"date": {"start": date.today().isoformat()}}
                        }
                    }
                )
                
                if update_response.status_code == 200:
                    load_active_client_locations.clear()
                    load_pending_reception_locations.clear()
                    q.clear()
                    preload_all_data.clear()
                    show_feedback('success', "Envío finalizado", duration=1.5)
                    time.sleep(1.5)
                    st.rerun()
                else:
                    show_feedback('error', f"Error: {update_response.status_code}", duration=2)

@st.dialog("⚠️ Añadir dispositivos al envío")
def confirm_add_devices(location_name, device_count, location_id, selected_devices):
    st.write(f"**Vas a añadir dispositivos:**")
    st.write(f"• Al envío: **{location_name}**")
    st.write(f"• Cantidad: **{device_count}**")
    
    st.markdown("---")
    st.write("📦 **Dispositivos a añadir:**")
    
    devices = load_devices()
    incidents = load_active_incidents()
    incident_map_local = {}
    for inc in incidents:
        did = inc.get("Device")
        if did:
            if did not in incident_map_local:
                incident_map_local[did] = []
            incident_map_local[did].append(inc)
    
    devices_with_issues = 0
    
    for dev_id in selected_devices:
        dev = next((d for d in devices if d["id"] == dev_id), None)
        if not dev:
            continue
        
        dev_incidents = incident_map_local.get(dev_id, [])
        
        if dev_incidents:
            devices_with_issues += 1
            for inc in dev_incidents:
                st.markdown(f"⚠️ **{dev['Name']}** - Incidencia activa: *\"{inc['Name']}\"*")
        else:
            st.markdown(f"✅ {dev['Name']}")
    
    if devices_with_issues > 0:
        st.warning(f"⚠️ **ADVERTENCIA:** {devices_with_issues} dispositivo(s) tienen incidencias activas. Se recomienda resolver las incidencias antes de añadir.")
    
    st.markdown("---")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Cancelar", use_container_width=True):
            st.rerun()
    with col2:
        if st.button("Confirmar", use_container_width=True, type="primary"):
            with st.spinner("Añadiendo dispositivos..."):
                success_count = 0
                for did in selected_devices:
                    resp = assign_device(did, location_id)
                    if resp.status_code == 200:
                        success_count += 1
                
                load_devices.clear()
                preload_all_data.clear()
                
                show_feedback('success', f"{success_count} dispositivos añadidos", duration=1.5)
                time.sleep(1.5)
                st.rerun()

@st.dialog("⚠️ Check-In de dispositivo")
def confirm_checkin(device_name, location_name, device_id, location_id, device_data):
    st.write(f"**Vas a recepcionar el dispositivo:**")
    st.write(f"• Dispositivo: **{device_name}**")
    st.write(f"• Del envío: **{location_name}**")
    st.info("Se registrará en el histórico y volverá a oficina.")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Cancelar", use_container_width=True):
            st.rerun()
    with col2:
        if st.button("Confirmar", use_container_width=True, type="primary"):
            with st.spinner("Procesando Check-In..."):
                payload = {
                    "parent": {"database_id": HISTORIC_ID},
                    "properties": {
                        "Name": {"title": [{"text": {"content": device_data['Name']}}]},
                        "Tags": {"select": {"name": device_data["Tags"]}} if device_data.get("Tags") else None,
                        "SN": {"rich_text": [{"text": {"content": device_data.get("SN", "")}}]},
                        "Location": {"relation": [{"id": location_id}]},
                        "Start Date": {"date": {"start": device_data["Start"]}} if device_data.get("Start") else None,
                        "End Date": {"date": {"start": device_data["End"]}} if device_data.get("End") else None,
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
                    show_feedback('error', f"Error al registrar en histórico: {r.status_code}", duration=3)
                else:
                    resp = assign_device(device_id, office_id())
                    
                    if resp.status_code == 200:
                        st.session_state.keep_almacen_tab = True
                        
                        load_devices.clear()
                        load_pending_reception_locations.clear()
                        load_historic_client_locations.clear()
                        q.clear()
                        preload_all_data.clear()
                        show_feedback('success', "Check-in completado", duration=1.5)
                        time.sleep(1.5)
                        st.rerun()
                    else:
                        show_feedback('error', f"Error al mover a oficina: {resp.status_code}", duration=3)

@st.dialog("⚠️ Asignar dispositivos a persona")
def confirm_assign_to_person(person_name, device_count, person_id, selected_devices):
    st.write(f"**Vas a asignar dispositivos:**")
    st.write(f"• A: **{person_name}**")
    st.write(f"• Cantidad: **{device_count}**")
    
    st.markdown("---")
    st.write("📦 **Dispositivos a asignar:**")
    
    devices = load_devices()
    incidents = load_active_incidents()
    incident_map_local = {}
    for inc in incidents:
        did = inc.get("Device")
        if did:
            if did not in incident_map_local:
                incident_map_local[did] = []
            incident_map_local[did].append(inc)
    
    devices_with_issues = 0
    
    for dev_id in selected_devices:
        dev = next((d for d in devices if d["id"] == dev_id), None)
        if not dev:
            continue
        
        dev_incidents = incident_map_local.get(dev_id, [])
        
        if dev_incidents:
            devices_with_issues += 1
            for inc in dev_incidents:
                st.markdown(f"⚠️ **{dev['Name']}** - Incidencia activa: *\"{inc['Name']}\"*")
        else:
            st.markdown(f"✅ {dev['Name']}")
    
    if devices_with_issues > 0:
        st.warning(f"⚠️ **ADVERTENCIA:** {devices_with_issues} dispositivo(s) tienen incidencias activas. Se recomienda resolver las incidencias antes de asignar.")
    
    st.markdown("---")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Cancelar", use_container_width=True):
            st.rerun()
    with col2:
        if st.button("Confirmar", use_container_width=True, type="primary"):
            with st.spinner("Asignando dispositivos..."):
                success_count = 0
                for did in selected_devices:
                    resp = assign_device(did, person_id)
                    if resp.status_code == 200:
                        success_count += 1
                
                load_devices.clear()
                preload_all_data.clear()
                
                show_feedback('success', f"{success_count} dispositivos asignados", duration=1.5)
                time.sleep(1.5)
                st.rerun()

@st.dialog("⚠️ Reasignar dispositivos a nuevo proyecto")
def confirm_reassign_pending(client_name, devices, start_date, end_date, old_loc_id, old_loc_name, device_ids):
    st.write(f"**Vas a reasignar los dispositivos pendientes:**")
    st.write(f"• Desde envío: **{old_loc_name}**")
    st.write(f"• Hacia nuevo proyecto: **{client_name}**")
    st.write(f"• Dispositivos: **{len(devices)}**")
    st.write(f"• Desde: **{start_date.strftime('%d/%m/%Y')}**")
    st.write(f"• Hasta: **{end_date.strftime('%d/%m/%Y')}**")
    
    total_days = (end_date - start_date).days
    st.write(f"• Duración: **{total_days} días**")
    
    st.markdown("---")
    st.write("📦 **Dispositivos a reasignar:**")
    
    incidents = load_active_incidents()
    incident_map_local = {}
    for inc in incidents:
        did = inc.get("Device")
        if did:
            if did not in incident_map_local:
                incident_map_local[did] = []
            incident_map_local[did].append(inc)
    
    devices_with_issues = 0
    
    for dev in devices:
        dev_incidents = incident_map_local.get(dev["id"], [])
        
        if dev_incidents:
            devices_with_issues += 1
            for inc in dev_incidents:
                st.markdown(f"⚠️ **{dev['Name']}** - Incidencia activa: *\"{inc['Name']}\"*")
        else:
            st.markdown(f"✅ {dev['Name']}")
    
    if devices_with_issues > 0:
        st.warning(f"⚠️ **ADVERTENCIA:** {devices_with_issues} dispositivo(s) tienen incidencias activas. Se recomienda resolver las incidencias antes de reasignar.")
    
    st.markdown("---")
    
    conflicts = []
    for dev in devices:
        if dev.get("Start") and dev.get("End"):
            dev_start = iso_to_date(dev["Start"])
            dev_end = iso_to_date(dev["End"])
            
            if dev_start and dev_end:
                if not (start_date > dev_end or end_date < dev_start):
                    conflicts.append(dev["Name"])
    
    if conflicts:
        st.error(f"⚠️ **Conflicto detectado:** Los siguientes dispositivos ya están asignados a otros proyectos en esas fechas:")
        for dev_name in conflicts:
            st.write(f"• {dev_name}")
        st.warning("Si continúas, estos dispositivos tendrán solapamiento de fechas.")
    
    st.info("Se hará check-in automático de todos los dispositivos pendientes y se asignarán al nuevo proyecto.")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Cancelar", use_container_width=True):
            st.rerun()
    with col2:
        if st.button("Confirmar reasignación", use_container_width=True, type="primary"):
            with st.spinner("Procesando reasignación..."):
                
                checkin_success = 0
                for dev in devices:
                    payload = {
                        "parent": {"database_id": HISTORIC_ID},
                        "properties": {
                            "Name": {"title": [{"text": {"content": dev['Name']}}]},
                            "Tags": {"select": {"name": dev["Tags"]}} if dev.get("Tags") else None,
                            "SN": {"rich_text": [{"text": {"content": dev.get("SN", "")}}]},
                            "Location": {"relation": [{"id": old_loc_id}]},
                            "Start Date": {"date": {"start": dev["Start"]}} if dev.get("Start") else None,
                            "End Date": {"date": {"start": dev["End"]}} if dev.get("End") else None,
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
                    
                    if r.status_code == 200:
                        checkin_success += 1
                
                response = requests.post(
                    "https://api.notion.com/v1/pages", 
                    headers=headers,
                    json={
                        "parent": {"database_id": LOCATIONS_ID},
                        "properties": {
                            "Name": {"title": [{"text": {"content": client_name}}]},
                            "Type": {"select": {"name": "Client"}},
                            "Start Date": {"date": {"start": start_date.isoformat()}},
                            "End Date": {"date": {"start": end_date.isoformat()}}
                        }
                    }
                )
                
                if response.status_code == 200:
                    new_loc_id = response.json()["id"]
                    
                    assign_success = 0
                    for did in device_ids:
                        resp = assign_device(did, new_loc_id)
                        if resp.status_code == 200:
                            assign_success += 1
                    
                    load_devices.clear()
                    load_future_client_locations.clear()
                    load_pending_reception_locations.clear()
                    load_historic_client_locations.clear()
                    load_locations_map.clear()
                    q.clear()
                    preload_all_data.clear()
                    
                    show_feedback('success', f"Check-in: {checkin_success}/{len(devices)} | Asignados: {assign_success}/{len(devices)}", duration=2)
                    time.sleep(2)
                    st.rerun()
                else:
                    show_feedback('error', f"Error al crear nuevo proyecto: {response.status_code}", duration=3)

@st.dialog("⚠️ Renovar alquiler")
def confirm_renew_rental(client_name, devices, start_date, end_date, old_loc_id, old_loc_name, device_ids):
    st.write(f"**Vas a renovar el alquiler:**")
    st.write(f"• Alquiler actual: **{old_loc_name}**")
    st.write(f"• Nuevo alquiler: **{client_name}**")
    st.write(f"• Dispositivos: **{len(devices)}**")
    st.write(f"• Desde: **{start_date.strftime('%d/%m/%Y')}**")
    st.write(f"• Hasta: **{end_date.strftime('%d/%m/%Y')}**")
    
    total_days = (end_date - start_date).days
    st.write(f"• Duración: **{total_days} días**")
    
    st.markdown("---")
    st.write("📦 **Dispositivos a renovar:**")
    
    incidents = load_active_incidents()
    incident_map_local = {}
    for inc in incidents:
        did = inc.get("Device")
        if did:
            if did not in incident_map_local:
                incident_map_local[did] = []
            incident_map_local[did].append(inc)
    
    devices_with_issues = 0
    
    for dev in devices:
        dev_incidents = incident_map_local.get(dev["id"], [])
        
        if dev_incidents:
            devices_with_issues += 1
            for inc in dev_incidents:
                st.markdown(f"⚠️ **{dev['Name']}** - Incidencia activa: *\"{inc['Name']}\"*")
        else:
            st.markdown(f"✅ {dev['Name']}")
    
    if devices_with_issues > 0:
        st.warning(f"⚠️ **ADVERTENCIA:** {devices_with_issues} dispositivo(s) tienen incidencias activas. Se recomienda resolver las incidencias antes de renovar.")
    
    st.markdown("---")
    
    conflicts = []
    for dev in devices:
        if dev.get("Start") and dev.get("End"):
            dev_start = iso_to_date(dev["Start"])
            dev_end = iso_to_date(dev["End"])
            
            if dev_start and dev_end:
                if not (start_date > dev_end or end_date < dev_start):
                    conflicts.append(dev["Name"])
    
    if conflicts:
        st.error(f"⚠️ **Conflicto detectado:** Los siguientes dispositivos ya están asignados a otros proyectos en esas fechas:")
        for dev_name in conflicts:
            st.write(f"• {dev_name}")
        st.warning("Si continúas, estos dispositivos tendrán solapamiento de fechas.")
    
    st.info("Se hará check-in automático de todos los dispositivos del alquiler actual y se crearán nuevas asignaciones para la renovación.")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Cancelar", use_container_width=True):
            st.rerun()
    with col2:
        if st.button("Confirmar renovación", use_container_width=True, type="primary"):
            with st.spinner("Procesando renovación..."):
                
                checkin_success = 0
                for dev in devices:
                    payload = {
                        "parent": {"database_id": HISTORIC_ID},
                        "properties": {
                            "Name": {"title": [{"text": {"content": dev['Name']}}]},
                            "Tags": {"select": {"name": dev["Tags"]}} if dev.get("Tags") else None,
                            "SN": {"rich_text": [{"text": {"content": dev.get("SN", "")}}]},
                            "Location": {"relation": [{"id": old_loc_id}]},
                            "Start Date": {"date": {"start": dev["Start"]}} if dev.get("Start") else None,
                            "End Date": {"date": {"start": dev["End"]}} if dev.get("End") else None,
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
                    
                    if r.status_code == 200:
                        checkin_success += 1
                
                response = requests.post(
                    "https://api.notion.com/v1/pages", 
                    headers=headers,
                    json={
                        "parent": {"database_id": LOCATIONS_ID},
                        "properties": {
                            "Name": {"title": [{"text": {"content": client_name}}]},
                            "Type": {"select": {"name": "Client"}},
                            "Start Date": {"date": {"start": start_date.isoformat()}},
                            "End Date": {"date": {"start": end_date.isoformat()}}
                        }
                    }
                )
                
                if response.status_code == 200:
                    new_loc_id = response.json()["id"]
                    
                    assign_success = 0
                    for did in device_ids:
                        resp = assign_device(did, new_loc_id)
                        if resp.status_code == 200:
                            assign_success += 1
                    
                    load_devices.clear()
                    load_active_client_locations.clear()
                    load_future_client_locations.clear()
                    load_pending_reception_locations.clear()
                    load_historic_client_locations.clear()
                    load_locations_map.clear()
                    q.clear()
                    preload_all_data.clear()
                    
                    show_feedback('success', f"Renovación completada: Check-in {checkin_success}/{len(devices)} | Asignados {assign_success}/{len(devices)}", duration=2)
                    time.sleep(2)
                    st.rerun()
                else:
                    show_feedback('error', f"Error al crear nuevo alquiler: {response.status_code}", duration=3)


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
    devices = load_devices()
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
        if not sd or iso_to_date(sd) <= today:
            continue
        
        try:
            name = props["Name"]["title"][0]["text"]["content"]
        except:
            name = "Sin nombre"
        
        ed = props["End Date"]["date"]["start"] if props.get("End Date") and props["End Date"]["date"] else None
        
        loc_id = p["id"]
        device_count = sum(1 for d in devices if loc_id in d["location_ids"])
        
        out.append({
            "id": loc_id,
            "name": name,
            "start": sd,
            "end": ed,
            "device_count": device_count
        })
    
    return out

@st.cache_data(ttl=300)
def load_active_client_locations():
    today = date.today()
    results = q(LOCATIONS_ID)
    devices = load_devices()
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
        ed = props["End Date"]["date"]["start"] if props.get("End Date") and props["End Date"]["date"] else None
        
        if not sd:
            continue
        
        start_date = iso_to_date(sd)
        
        if start_date > today:
            continue
        
        if ed:
            end_date = iso_to_date(ed)
            
            if end_date < today:
                continue
            
            days_since_start = (today - start_date).days
            days_until_end = (end_date - today).days
            total_days = (end_date - start_date).days
        else:
            end_date = None
            days_since_start = (today - start_date).days
            days_until_end = None
            total_days = None
        
        try:
            name = props["Name"]["title"][0]["text"]["content"]
        except:
            name = "Sin nombre"
        
        loc_id = p["id"]
        device_count = sum(1 for d in devices if loc_id in d["location_ids"])
        
        out.append({
            "id": loc_id,
            "name": name,
            "start": sd,
            "end": ed,
            "device_count": device_count,
            "start_date_obj": start_date,
            "end_date_obj": end_date,
            "days_since_start": days_since_start,
            "days_until_end": days_until_end,
            "total_days": total_days
        })
    
    out = sorted(out, key=lambda x: x["days_until_end"] if x["days_until_end"] is not None else float('inf'))
    
    return out

@st.cache_data(ttl=300)
def load_pending_reception_locations():
    today = date.today()
    results = q(LOCATIONS_ID)
    devices = load_devices()
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
        
        if end_date > today:
            continue
        
        try:
            name = props["Name"]["title"][0]["text"]["content"]
        except:
            name = "Sin nombre"
        
        sd = props["Start Date"]["date"]["start"] if props.get("Start Date") and props["Start Date"]["date"] else None
        
        loc_id = p["id"]
        
        currently_assigned = sum(1 for d in devices if loc_id in d["location_ids"])
        
        if currently_assigned == 0:
            continue
        
        out.append({
            "id": loc_id,
            "name": name,
            "start": sd,
            "end": ed,
            "device_count": currently_assigned,
            "end_date_obj": end_date
        })
    
    out = sorted(out, key=lambda x: x["end_date_obj"])
    
    return out

@st.cache_data(ttl=300)
def load_historic_client_locations():
    today = date.today()
    thirty_days_ago = today - timedelta(days=30)
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
        
        if end_date >= today or end_date < thirty_days_ago:
            continue
        
        try:
            name = props["Name"]["title"][0]["text"]["content"]
        except:
            name = "Sin nombre"
        
        sd = props["Start Date"]["date"]["start"] if props.get("Start Date") and props["Start Date"]["date"] else None
        
        loc_id = p["id"]
        
        currently_assigned = sum(1 for d in devices if loc_id in d["location_ids"])
        
        historic_count = 0
        checkin_date = None
        for entry in historic:
            hist_props = entry["properties"]
            hist_loc = hist_props.get("Location", {}).get("relation", [])
            if hist_loc and hist_loc[0]["id"] == loc_id:
                historic_count += 1
                if not checkin_date:
                    checkin_prop = hist_props.get("Check In", {}).get("date", {})
                    if checkin_prop:
                        checkin_date = checkin_prop.get("start")
        
        if currently_assigned > 0:
            continue
        
        if historic_count == 0:
            continue
        
        device_count = historic_count
        
        out.append({
            "id": loc_id,
            "name": name,
            "start": sd,
            "end": ed,
            "device_count": device_count,
            "end_date_obj": end_date,
            "checkin_date": checkin_date
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
    
    if sel_label is None or sel_label not in opciones_map:
        sel_label = opciones_display[0]
    
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
        'active_locations': load_active_client_locations(),
        'pending_locations': load_pending_reception_locations(),
        'historic_locations': load_historic_client_locations(),
        'inhouse': load_inhouse(),
        'office_id': office_id(),
        'active_incidents': load_active_incidents(),
        'past_incidents': load_past_incidents(),
        'incidence_map': load_incidence_map(),
        'all_locations': q(LOCATIONS_ID)
    }
    return data

if "expander_states" not in st.session_state:
    st.session_state.expander_states = {}

for key, default in [
    ("tab1_show", False),
    ("sel1", []),
    ("sel2", []),
    ("sel3", []),
    ("processing_action", False)
]:
    if key not in st.session_state:
        st.session_state[key] = default


with st.spinner("📄 Cargando datos desde Notion..."):
    preloaded_data = preload_all_data()

locations_map = preloaded_data['locations_map']
all_devices = preloaded_data['devices']
incidence_map = preloaded_data['incidence_map']


with st.sidebar:
    st.image("img/logo.png", use_container_width=True)
    
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
        create_menu_label("Almacén", 0),
        create_menu_label("Incidencias", num_incidencias)
    ]
    
    menu_mapping = {
        opciones_menu[0]: "Disponibles para Alquilar",
        opciones_menu[1]: "Gafas en casa",
        opciones_menu[2]: "Almacén",
        opciones_menu[3]: "Incidencias"
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
    
    c1, c2, c3 = st.columns(3)
    with c1:
        start = st.date_input("Fecha salida", date.today(), key="tab1_start_date")
    with c2:
        end = st.date_input("Fecha regreso", date.today(), key="tab1_end_date")
    with c3:
        if 'tab1_start_date' in st.session_state and 'tab1_end_date' in st.session_state:
            days_diff = (st.session_state.tab1_end_date - st.session_state.tab1_start_date).days
        else:
            days_diff = 0
        st.metric("Días totales", days_diff)
    
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
        
        if sel_count > 0:
            counter_badge(sel_count, len(avail_filtered))
            
            with st.form("form_assign_client"):
                client = st.text_input("Nombre Cliente")
                submit = st.form_submit_button("Asignar Cliente", use_container_width=True)
                
                if submit:
                    if not client or client.strip() == "":
                        show_feedback('error', "Debes escribir el nombre del cliente", duration=2)
                    else:
                        confirm_assign_client(client, sel_count, start, end, st.session_state.sel1)


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
    
    expander_personal_key = "expander_personal_devices"
    if expander_personal_key not in st.session_state.expander_states:
        st.session_state.expander_states[expander_personal_key] = True
    
    with st.expander("Personal con dispositivos en casa", expanded=st.session_state.expander_states[expander_personal_key]):
        
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
                
                person_expander_key = f"expander_person_{pid}"
                if person_expander_key not in st.session_state.expander_states:
                    st.session_state.expander_states[person_expander_key] = False
                
                with st.expander(f"{pname} ({len(devs)})", expanded=st.session_state.expander_states[person_expander_key]):
                    
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
                                confirm_return_device(d["Name"], pname, d["id"])
    
    office_devices = [
        d for d in devices
        if oid in d["location_ids"]
    ]
    
    expander_office_key = "expander_office_devices"
    if expander_office_key not in st.session_state.expander_states:
        st.session_state.expander_states[expander_office_key] = False
    
    with st.expander("Otras gafas disponibles en oficina", expanded=st.session_state.expander_states[expander_office_key]):
        
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
            counter_badge(sel_count, len(office_filtered))
            
            dest = st.selectbox("Asignar a:", [x["name"] for x in inh], key="dest_person")
            dest_id = next(x["id"] for x in inh if x["name"] == dest)
            
            if st.button("Asignar seleccionadas", use_container_width=True):
                confirm_assign_to_person(dest, sel_count, dest_id, st.session_state.sel2)


elif st.session_state.menu == "Almacén":
    st.title("📦 Almacén")
    legend_button()
    
    future_locs = preloaded_data['future_locations']
    active_locs = preloaded_data['active_locations']
    pending_locs = preloaded_data['pending_locations']
    historic_locs = preloaded_data['historic_locations']
    
    future_count = len(future_locs)
    pending_count = len(pending_locs)
    
    if 'almacen_subtab' not in st.session_state:
        st.session_state.almacen_subtab = f"🚀 Próximos ({future_count})"
    
    opciones_almacen = [
        f"🚀 Próximos ({future_count})",
        "✅ Activos",
        f"📬 Recepcionar ({pending_count})"
    ]
    
    if st.session_state.get('keep_almacen_tab'):
        if st.session_state.almacen_subtab not in opciones_almacen:
            st.session_state.almacen_subtab = opciones_almacen[2]
        st.session_state.keep_almacen_tab = False
    
    selected_almacen = st.radio(
        "Sección",
        opciones_almacen,
        index=opciones_almacen.index(st.session_state.almacen_subtab) if st.session_state.almacen_subtab in opciones_almacen else 0,
        horizontal=True,
        key="radio_almacen",
        label_visibility="collapsed"
    )
    
    st.session_state.almacen_subtab = selected_almacen
    
    st.markdown("---")
    
    if selected_almacen == opciones_almacen[0]:
        
        if len(future_locs) == 0:
            st.info("No hay envíos próximos.")
        else:
            for loc in future_locs:
                lname = loc["name"]
                loc_id = loc["id"]
                device_count = loc["device_count"]
                start_date = iso_to_date(loc["start"])
                
                relative_start = format_relative_date(start_date)
                
                status_icon = get_shipment_status_icon(loc_id)
                
                shipment_expander_key = f"expander_shipment_{loc_id}"
                if shipment_expander_key not in st.session_state.expander_states:
                    st.session_state.expander_states[shipment_expander_key] = False
                
                with st.expander(f"{status_icon} {lname} 🥽 {device_count} 📅 Sale {relative_start}", expanded=st.session_state.expander_states[shipment_expander_key]):
                    
                    devices = all_devices
                    
                    status_options = ["📋 Planificado", "📦 Empaquetado", "🚚 En camino"]
                    default_status = st.session_state.get(f"status_{loc_id}", "📋 Planificado")
                    if default_status not in status_options:
                        default_status = "📋 Planificado"
                    
                    selected_status = st.selectbox(
                        "Estado del envío:",
                        status_options,
                        index=status_options.index(default_status),
                        key=f"status_select_{loc_id}"
                    )
                    
                    st.session_state[f"status_{loc_id}"] = selected_status
                    
                    assigned = [
                        d for d in devices
                        if loc_id in d["location_ids"]
                    ]
                    
                    ls = iso_to_date(loc["start"])
                    le = iso_to_date(loc["end"])
                    
                    can_add = [
                        d for d in devices
                        if d.get("location_ids")
                        and available(d, ls, le)
                        and loc_id not in d["location_ids"]
                    ]
                    
                    expander_dates_key = f"expander_dates_{loc_id}"
                    if expander_dates_key not in st.session_state.expander_states:
                        st.session_state.expander_states[expander_dates_key] = False
                    
                    total_days_rental = (le - ls).days if ls and le else 0
                    
                    with st.expander(f"📅 Fechas [{fmt(loc['start'])} → {fmt(loc['end'])}] • {total_days_rental} días", expanded=st.session_state.expander_states[expander_dates_key]):
                        
                        with st.form(key=f"edit_dates_{loc_id}"):
                            st.subheader("Editar fechas del envío")
                            
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
                                    feedback_placeholder = st.empty()
                                    with feedback_placeholder:
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
                                                
                                                feedback_placeholder.empty()
                                                show_feedback('success', "Fechas actualizadas correctamente", duration=1.5)
                                                time.sleep(1.5)
                                                st.rerun()
                                            else:
                                                feedback_placeholder.empty()
                                                show_feedback('error', f"Error al actualizar: {update_response.status_code}", duration=3)
                    
                    expander_devices_key = f"expander_devices_{loc_id}"
                    if expander_devices_key not in st.session_state.expander_states:
                        st.session_state.expander_states[expander_devices_key] = False
                    
                    with st.expander(f"🥽 Dispositivos [{len(assigned)} asignados]", expanded=st.session_state.expander_states[expander_devices_key]):
                        
                        if len(assigned) == 0:
                            st.warning("Este envío no tiene dispositivos asignados")
                            
                            if st.button("Borrar envío", key=f"delete_loc_{loc_id}", use_container_width=True):
                                confirm_delete_shipment(lname, loc_id)
                        else:
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
                                            confirm_remove_device(d["Name"], lname, d["id"])
                        
                        expander_add_key = f"expander_add_{loc_id}"
                        if expander_add_key not in st.session_state.expander_states:
                            st.session_state.expander_states[expander_add_key] = False
                        
                        with st.expander(f"➕ Añadir más dispositivos [{len(can_add)} disponibles]", expanded=st.session_state.expander_states[expander_add_key]):
                            
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
                                cols_bottom = st.columns([7, 3])
                                
                                with cols_bottom[0]:
                                    counter_badge(sel_count, len(can_add_filtered))
                                
                                with cols_bottom[1]:
                                    if st.button("Añadir", key=f"assign_btn_{loc_id}", use_container_width=True):
                                        confirm_add_devices(lname, sel_count, loc_id, selected_ids)
                    
                    includes_headphones = st.checkbox(
                        "🎧 Incluye cascos",
                        value=st.session_state.get(f"headphones_{loc_id}", False),
                        key=f"headphones_{loc_id}"
                    )
    
    
    elif selected_almacen == opciones_almacen[1]:
        devices = all_devices
        
        active_with_end = [loc for loc in active_locs if loc.get('end')]
        active_without_end = [loc for loc in active_locs if not loc.get('end')]
        
        total_active = len(active_with_end) + len(active_without_end)
        
        if total_active == 0:
            st.info("No hay envíos activos en este momento.")
        else:
            st.write(f"**{total_active} envío(s) activo(s)**")
            
            for loc in active_with_end:
                lname = loc["name"]
                loc_id = loc["id"]
                device_count = loc["device_count"]
                days_until_end = loc["days_until_end"]
                total_days = loc["total_days"]
                start_date_obj = loc["start_date_obj"]
                end_date_obj = loc["end_date_obj"]
                
                if days_until_end < 30:
                    status_circle = "🟡"
                else:
                    status_circle = "🟢"
                
                days_text = f"Quedan {days_until_end} de {total_days} días"
                
                active_expander_key = f"expander_active_{loc_id}"
                if active_expander_key not in st.session_state.expander_states:
                    st.session_state.expander_states[active_expander_key] = False
                
                with st.expander(f"{status_circle} 📦 {lname} 🥽 {device_count} 📅 {days_text}", expanded=st.session_state.expander_states[active_expander_key]):
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.markdown(f"📅 **Inicio:** {fmt(loc['start'])}")
                    with col2:
                        st.markdown(f"📅 **Fin:** {fmt(loc['end'])}")
                    with col3:
                        st.markdown(f"⏱️ **Duración:** {total_days} días")
                    
                    st.markdown("")
                    
                    col_end, col_renew = st.columns(2)
                    
                    with col_end:
                        if st.button("Terminar alquiler hoy", key=f"end_today_{loc_id}", use_container_width=True):
                            confirm_end_shipment(lname, device_count, loc_id)
                    
                    with col_renew:
                        if st.button("🔄 Renovar alquiler", key=f"toggle_renew_{loc_id}", use_container_width=True):
                            renew_key = f"expander_renew_{loc_id}"
                            if renew_key not in st.session_state.expander_states:
                                st.session_state.expander_states[renew_key] = False
                            st.session_state.expander_states[renew_key] = not st.session_state.expander_states[renew_key]
                            st.rerun()
                    
                    renew_expander_key = f"expander_renew_{loc_id}"
                    if renew_expander_key not in st.session_state.expander_states:
                        st.session_state.expander_states[renew_expander_key] = False
                    
                    if st.session_state.expander_states[renew_expander_key]:
                        with st.container(border=True):
                            st.subheader("Renovar alquiler")
                            st.caption(f"Se hará check-in de todos los dispositivos y se creará un nuevo alquiler consecutivo")
                            
                            assigned = [
                                d for d in devices
                                if loc_id in d["location_ids"]
                            ]
                            
                            new_start_date = end_date_obj + timedelta(days=1)
                            new_end_date = new_start_date + timedelta(days=total_days)
                            year_suffix = new_start_date.year
                            default_name = f"{lname} {year_suffix}"
                            
                            renew_client_name = st.text_input(
                                "Nombre del nuevo alquiler",
                                value=default_name,
                                key=f"renew_name_{loc_id}"
                            )
                            
                            col_start, col_end = st.columns(2)
                            
                            with col_start:
                                renew_start = st.date_input(
                                    "Fecha salida",
                                    value=new_start_date,
                                    key=f"renew_start_{loc_id}"
                                )
                            
                            with col_end:
                                renew_end = st.date_input(
                                    "Fecha regreso",
                                    value=new_end_date,
                                    key=f"renew_end_{loc_id}"
                                )
                            
                            col_confirm, col_cancel = st.columns(2)
                            
                            with col_confirm:
                                if st.button("Confirmar renovación", key=f"confirm_renew_{loc_id}", use_container_width=True, type="primary"):
                                    if not renew_client_name or renew_client_name.strip() == "":
                                        show_feedback('error', "Debes escribir el nombre del alquiler", duration=2)
                                    elif renew_start > renew_end:
                                        show_feedback('error', "La fecha de salida no puede ser posterior a la de regreso", duration=3)
                                    else:
                                        device_ids = [d["id"] for d in assigned]
                                        confirm_renew_rental(renew_client_name, assigned, renew_start, renew_end, loc_id, lname, device_ids)
                            
                            with col_cancel:
                                if st.button("Cancelar", key=f"cancel_renew_{loc_id}", use_container_width=True):
                                    st.session_state.expander_states[renew_expander_key] = False
                                    st.rerun()
                    
                    st.markdown("---")
                    
                    assigned = [
                        d for d in devices
                        if loc_id in d["location_ids"]
                    ]
                    
                    if len(assigned) > 0:
                        st.caption("Dispositivos en uso:")
                        
                        assigned_filtered, _ = smart_segmented_filter(assigned, key_prefix=f"active_assigned_{loc_id}")
                        
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
                                    if st.button("Devolver", key=f"return_{loc_id}_{d['id']}", use_container_width=True):
                                        confirm_return_device(d["Name"], lname, d["id"])
            
            for loc in active_without_end:
                lname = loc["name"]
                loc_id = loc["id"]
                device_count = loc["device_count"]
                days_since_start = loc["days_since_start"]
                
                status_circle = "🔵"
                days_text = f"Llevan {days_since_start} días"
                
                active_indef_expander_key = f"expander_active_indef_{loc_id}"
                if active_indef_expander_key not in st.session_state.expander_states:
                    st.session_state.expander_states[active_indef_expander_key] = False
                
                with st.expander(f"{status_circle} 📦 {lname} 🥽 {device_count} 📅 {days_text}", expanded=st.session_state.expander_states[active_indef_expander_key]):
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f"📅 **Inicio:** {fmt(loc['start'])}")
                    with col2:
                        st.markdown(f"⏱️ **Duración:** {days_since_start} días")
                    
                    st.markdown("")
                    
                    if st.button("Terminar alquiler hoy", key=f"end_today_{loc_id}", use_container_width=True):
                        confirm_end_shipment(lname, device_count, loc_id)
                    
                    st.markdown("---")
                    
                    assigned = [
                        d for d in devices
                        if loc_id in d["location_ids"]
                    ]
                    
                    if len(assigned) > 0:
                        st.caption("Dispositivos en uso:")
                        
                        assigned_filtered, _ = smart_segmented_filter(assigned, key_prefix=f"active_assigned_indef_{loc_id}")
                        
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
                                    if st.button("Devolver", key=f"return_{loc_id}_{d['id']}", use_container_width=True):
                                        confirm_return_device(d["Name"], lname, d["id"])
    
    
    elif selected_almacen == opciones_almacen[2]:
        
        expander_pending_key = "expander_pending_reception"
        if expander_pending_key not in st.session_state.expander_states:
            st.session_state.expander_states[expander_pending_key] = True
        
        with st.expander(f"📬 Pendientes de recepcionar ({len(pending_locs)})", expanded=st.session_state.expander_states[expander_pending_key]):
            
            if len(pending_locs) == 0:
                st.info("No hay envíos pendientes de recepcionar.")
            else:
                for loc in pending_locs:
                    lname = loc["name"]
                    loc_id = loc["id"]
                    device_count = loc["device_count"]
                    end_date_obj = loc["end_date_obj"]
                    
                    relative_date = format_relative_date(end_date_obj)
                    
                    days_late = (date.today() - end_date_obj).days
                    
                    if days_late > 2:
                        status_icon = "🔴"
                    else:
                        status_icon = "⚠️"
                    
                    pending_loc_expander_key = f"expander_pending_loc_{loc_id}"
                    if pending_loc_expander_key not in st.session_state.expander_states:
                        st.session_state.expander_states[pending_loc_expander_key] = False
                    
                    with st.expander(f"{status_icon} {lname} 🥽 {device_count} 📅 Terminó {relative_date}", expanded=st.session_state.expander_states[pending_loc_expander_key]):
                        
                        devices = all_devices
                        
                        assigned = [
                            d for d in devices
                            if loc_id in d["location_ids"]
                        ]
                        
                        st.caption(f"Dispositivos pendientes de recepcionar:")
                        
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
                                        confirm_checkin(d["Name"], lname, d["id"], loc_id, d)
                        
                        st.markdown("---")
                        
                        if st.button("📦 Reasignar a nuevo proyecto", key=f"toggle_reassign_{loc_id}", use_container_width=True):
                            reassign_key = f"expander_reassign_{loc_id}"
                            if reassign_key not in st.session_state.expander_states:
                                st.session_state.expander_states[reassign_key] = False
                            st.session_state.expander_states[reassign_key] = not st.session_state.expander_states[reassign_key]
                            st.rerun()
                        
                        reassign_expander_key = f"expander_reassign_{loc_id}"
                        if reassign_expander_key not in st.session_state.expander_states:
                            st.session_state.expander_states[reassign_expander_key] = False
                        
                        if st.session_state.expander_states[reassign_expander_key]:
                            with st.container(border=True):
                                st.subheader("Reasignar dispositivos pendientes")
                                st.caption(f"Se hará check-in automático de {len(assigned)} dispositivos y se reasignarán al nuevo proyecto")
                                
                                new_client_name = st.text_input(
                                    "Nombre del nuevo cliente/proyecto",
                                    key=f"reassign_name_{loc_id}"
                                )
                                
                                col_start, col_end = st.columns(2)
                                
                                with col_start:
                                    new_start = st.date_input(
                                        "Fecha salida",
                                        value=date.today(),
                                        key=f"reassign_start_{loc_id}"
                                    )
                                
                                with col_end:
                                    new_end = st.date_input(
                                        "Fecha regreso",
                                        value=date.today() + timedelta(days=7),
                                        key=f"reassign_end_{loc_id}"
                                    )
                                
                                col_confirm, col_cancel = st.columns(2)
                                
                                with col_confirm:
                                    if st.button("Confirmar reasignación", key=f"confirm_reassign_{loc_id}", use_container_width=True, type="primary"):
                                        if not new_client_name or new_client_name.strip() == "":
                                            show_feedback('error', "Debes escribir el nombre del cliente", duration=2)
                                        elif new_start > new_end:
                                            show_feedback('error', "La fecha de salida no puede ser posterior a la de regreso", duration=3)
                                        else:
                                            device_ids = [d["id"] for d in assigned]
                                            confirm_reassign_pending(new_client_name, assigned, new_start, new_end, loc_id, lname, device_ids)
                                
                                with col_cancel:
                                    if st.button("Cancelar", key=f"cancel_reassign_{loc_id}", use_container_width=True):
                                        st.session_state.expander_states[reassign_expander_key] = False
                                        st.rerun()
        
        expander_historic_key = "expander_historic"
        if expander_historic_key not in st.session_state.expander_states:
            st.session_state.expander_states[expander_historic_key] = False
        
        with st.expander(f"📚 Histórico (últimos 30 días) ({len(historic_locs)})", expanded=st.session_state.expander_states[expander_historic_key]):
            
            if len(historic_locs) == 0:
                st.info("No hay envíos en el histórico de los últimos 30 días.")
            else:
                for loc in historic_locs:
                    lname = loc["name"]
                    device_count = loc["device_count"]
                    checkin_date = loc.get("checkin_date")
                    
                    if checkin_date:
                        checkin_fmt = fmt(checkin_date)
                        status_text = f"Recepcionado el {checkin_fmt}"
                    else:
                        status_text = "Completado"
                    
                    st.markdown(f"⚫ **{lname}** 🥽 {device_count} 📅 {status_text}")

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

    expander_incidents_key = "expander_incidents_main"
    if expander_incidents_key not in st.session_state.expander_states:
        st.session_state.expander_states[expander_incidents_key] = True
    
    with st.expander(f"Incidencias en dispositivos ({total_active} activas)", expanded=st.session_state.expander_states[expander_incidents_key]):
        
        devices_with_incidents = [
            device_map[did] for did in incidents_by_device.keys() if did in device_map
        ]

        search_query = st.text_input(
            "Buscar dispositivo...",
            placeholder="Ej: Quest 3, Quest 2, Vision Pro...",
            key="inc_dynamic_search"
        )

        if search_query:
            q_lower = search_query.lower().strip()
            devices_with_incidents = [
                d for d in devices_with_incidents 
                if q_lower in d["Name"].lower()
            ]

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

        st.markdown("---")
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
            if st.button("Confirmar", use_container_width=True, type="primary"):

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
                                if "add_new_incident_expander" in st.session_state.expander_states:
                                    st.session_state.expander_states["add_new_incident_expander"] = False
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

    add_new_expanded_key = "add_new_incident_expander"
    if add_new_expanded_key not in st.session_state.expander_states:
        st.session_state.expander_states[add_new_expanded_key] = False

    with st.expander("Añadir nueva incidencia", expanded=st.session_state.expander_states[add_new_expanded_key]):

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

                                st.session_state.expander_states[add_new_expanded_key] = False
                                st.session_state.force_incidents_tab = True
                                
                                load_active_incidents.clear()
                                load_incidence_map.clear()
                                q.clear()
                                preload_all_data.clear()

                                feedback.empty()
                                show_feedback("success", "Incidencia creada", duration=1.5)
                                time.sleep(1.5)
                                st.rerun()    
