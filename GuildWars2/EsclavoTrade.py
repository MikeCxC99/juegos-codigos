import requests
import time
import os
from pathlib import Path
import json

# --- CONFIGURACION ---
GW2_API_KEY = ""
DISCORD_HABILITADO = False  # Se activa con variables de entorno
DISCORD_WEBHOOK_URL = ""
DISCORD_USER_ID = ""
TIEMPO_ESPERA = 300  # 5 minutos
TIMEOUT = 15
STATE_FILE = Path("esclavo_trade_state.json")
ENV_FILE = Path(".env")
ITEM_NAME_CACHE = {}
# --------------------


def cargar_env_local():
    if not ENV_FILE.exists():
        return
    try:
        for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            clave, valor = line.split("=", 1)
            clave = clave.strip()
            valor = valor.strip().strip('"').strip("'")
            if clave and clave not in os.environ:
                os.environ[clave] = valor
    except Exception as exc:
        print(f"No se pudo leer .env: {exc}")


def cargar_configuracion():
    global GW2_API_KEY, DISCORD_WEBHOOK_URL, DISCORD_USER_ID, DISCORD_HABILITADO
    GW2_API_KEY = os.getenv("GW2_API_KEY", GW2_API_KEY)
    DISCORD_HABILITADO = os.getenv("DISCORD_HABILITADO", "False").lower() in ("true", "1", "yes")
    DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", DISCORD_WEBHOOK_URL)
    DISCORD_USER_ID = os.getenv("DISCORD_USER_ID", DISCORD_USER_ID)


def validar_configuracion():
    if not GW2_API_KEY:
        raise ValueError("Falta GW2_API_KEY en variables de entorno.")
    if DISCORD_HABILITADO:
        if not DISCORD_WEBHOOK_URL:
            raise ValueError("Falta DISCORD_WEBHOOK_URL en variables de entorno.")
    else:
        print("[CONFIG] Discord deshabilitado - se usará solo modo terminal")


def estado_por_defecto():
    return {
        "coins": 0,
        "items": 0,
        "habia_ventas_activas": False,
        "buy_orders": {},
    }


def normalizar_ordenes_compras(ordenes):
    normalizadas = {}
    for orden in ordenes:
        order_id = orden.get("id")
        if order_id is None:
            continue
        normalizadas[str(order_id)] = {
            "item_id": int(orden.get("item_id", 0) or 0),
            "quantity": int(orden.get("quantity", 0) or 0),
            "price": int(orden.get("price", 0) or 0),
        }
    return normalizadas


def normalizar_estado(estado):
    base = estado_por_defecto()
    if not isinstance(estado, dict):
        return base
    base["coins"] = int(estado.get("coins", 0) or 0)
    base["items"] = int(estado.get("items", 0) or 0)
    base["habia_ventas_activas"] = bool(estado.get("habia_ventas_activas", False))
    buy_orders = estado.get("buy_orders", {})
    if isinstance(buy_orders, dict):
        cleaned = {}
        for order_id, order in buy_orders.items():
            if not isinstance(order, dict):
                continue
            cleaned[str(order_id)] = {
                "item_id": int(order.get("item_id", 0) or 0),
                "quantity": int(order.get("quantity", 0) or 0),
                "price": int(order.get("price", 0) or 0),
            }
        base["buy_orders"] = cleaned
    return base


def formato_oro(cobre_total):
    oro = cobre_total // 10000
    plata = (cobre_total % 10000) // 100
    cobre = cobre_total % 100
    return f"{oro} 🥇 | {plata} 🥈 | {cobre} 🥉"


def formatear_cantidad_total(cobre_total):
    oro = cobre_total // 10000
    plata = (cobre_total % 10000) // 100
    cobre = cobre_total % 100
    return f"{oro}g {plata}s {cobre}c"


def cargar_estado_previo():
    if not STATE_FILE.exists():
        return estado_por_defecto()
    try:
        with STATE_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return normalizar_estado(data)
    except Exception:
        return estado_por_defecto()


def guardar_estado(estado):
    data = normalizar_estado(estado)
    with STATE_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f)


def obtener_nombres_items(item_ids):
    ids_pendientes = [str(item_id) for item_id in item_ids if str(item_id) not in ITEM_NAME_CACHE]
    if ids_pendientes:
        url = "https://api.guildwars2.com/v2/items"
        try:
            for inicio in range(0, len(ids_pendientes), 200):
                chunk = ids_pendientes[inicio:inicio + 200]
                response = requests.get(url, params={"ids": ",".join(chunk)}, timeout=TIMEOUT)
                response.raise_for_status()
                for item in response.json():
                    ITEM_NAME_CACHE[str(item.get("id"))] = item.get("name", f"Item {item.get('id')}")
        except Exception as e:
            print(f"Error consultando nombres de items: {e}")
    return {str(item_id): ITEM_NAME_CACHE.get(str(item_id), f"Item {item_id}") for item_id in item_ids}


def revisar_entregas():
    url = "https://api.guildwars2.com/v2/commerce/delivery"
    headers = {"Authorization": f"Bearer {GW2_API_KEY}"}
    try:
        response = requests.get(url, headers=headers, timeout=TIMEOUT)
        response.raise_for_status()
        datos = response.json()
        return datos.get("coins", 0), len(datos.get("items", []))
    except Exception as e:
        print(f"Error consultando entregas: {e}")
    return 0, 0

def obtener_entregas_pendientes():
    url = "https://api.guildwars2.com/v2/commerce/delivery"
    headers = {"Authorization": f"Bearer {GW2_API_KEY}"}
    try:
        response = requests.get(url, headers=headers, timeout=TIMEOUT)
        response.raise_for_status()
        datos = response.json()
        return {
            "coins": int(datos.get("coins", 0) or 0),
            "items": datos.get("items", []),
        }
    except Exception as e:
        print(f"Error consultando entregas pendientes: {e}")
        return {"coins": 0, "items": []}


def formatear_items_entrega(items, limite=None):
    if not items:
        return ["Nada para recoger"]

    item_ids = set()
    for item in items:
        item_id = item.get("id")
        if item_id is not None:
            item_ids.add(int(item_id))

    nombres = obtener_nombres_items(item_ids)
    lineas = []

    subset = items[:limite] if limite else items
    for item in subset:
        item_id = int(item.get("id", 0) or 0)
        cantidad = int(item.get("count", 0) or 0)
        lineas.append(f"• {nombres.get(str(item_id), f'Item {item_id}')} x{cantidad}")

    if limite and len(items) > limite:
        lineas.append(f"• +{len(items) - limite} más")

    return lineas


def obtener_ventas_pendientes_detalladas(ventas=None):
    if ventas is None:
        url = "https://api.guildwars2.com/v2/commerce/transactions/current/sells"
        headers = {"Authorization": f"Bearer {GW2_API_KEY}"}
        try:
            response = requests.get(url, headers=headers, timeout=TIMEOUT)
            response.raise_for_status()
            ventas = response.json()
        except Exception as e:
            print(f"Error consultando ventas pendientes detalladas: {e}")
            return [], 0

    item_ids = set()
    for venta in ventas:
        item_id = venta.get("item_id")
        if item_id is not None:
            item_ids.add(int(item_id))

    nombres = obtener_nombres_items(item_ids)
    ventas_detalladas = []
    ganancia_bruta = 0

    for venta in ventas:
        item_id = int(venta.get("item_id", 0) or 0)
        cantidad = int(venta.get("quantity", 0) or 0)
        precio = int(venta.get("price", 0) or 0)
        total_bruto = precio * cantidad
        ganancia_bruta += total_bruto
        ventas_detalladas.append({
            "item_name": nombres.get(str(item_id), f"Item {item_id}"),
            "quantity": cantidad,
            "unit_price": precio,
            "total_bruto": total_bruto,
        })

    ganancia_neta = int(ganancia_bruta * 0.85)
    return ventas_detalladas, ganancia_neta


def enviar_discord_embed(ganancia_cobre, items_esperando):
    if not DISCORD_HABILITADO:
        return
    
    oro_formateado = formato_oro(ganancia_cobre)
    ping = f"<@{DISCORD_USER_ID}> " if DISCORD_USER_ID else ""
    data = {
        "username": "Esclavo de bajos recursos",
        "avatar_url": "https://wiki.guildwars2.com/images/d/df/Black_Lion_Trading_Company_trading_post_icon.png",
        "content": f"{ping}✅ Venta cerrada: {oro_formateado}",
        "embeds": [
            {
                "title": "📈 Mercado Limpio",
                "description": "Sin publicaciones activas. Hay retiro disponible.",
                "color": 16766720,
                "fields": [
                    {"name": "💰 Ganancia", "value": oro_formateado, "inline": False},
                    {"name": "📦 Bandeja", "value": f"{items_esperando} item(s)", "inline": True},
                ],
                "footer": {
                    "text": "Black Lion Alert",
                    "icon_url": "https://wiki.guildwars2.com/images/thumb/7/7b/Gold_coin.png/20px-Gold_coin.png",
                },
            }
        ],
    }
    response = requests.post(DISCORD_WEBHOOK_URL, json=data, timeout=TIMEOUT)
    response.raise_for_status()


def enviar_discord_compra_embed(eventos):
    if not DISCORD_HABILITADO:
        return
    
    total_cobre = sum(evento["total_cobre"] for evento in eventos)
    ping = f"<@{DISCORD_USER_ID}> " if DISCORD_USER_ID else ""
    detalle_lineas = []
    for evento in eventos[:3]:
        detalle_lineas.append(
            f"• {evento['item_name']} x{evento['quantity']} · {formatear_cantidad_total(evento['total_cobre'])}"
        )
    if len(eventos) > 3:
        detalle_lineas.append(f"• +{len(eventos) - 3} más")
    data = {
        "username": "Esclavo de bajos recursos",
        "avatar_url": "https://wiki.guildwars2.com/images/d/df/Black_Lion_Trading_Company_trading_post_icon.png",
        "content": f"{ping}🛒 Compra completada: {formatear_cantidad_total(total_cobre)}",
        "embeds": [
            {
                "title": "🛒 Orden llenada",
                "description": (
                    "Se completó una orden programada."
                    if len(eventos) == 1
                    else f"Se completaron {len(eventos)} órdenes programadas."
                ),
                "color": 3447003,
                "fields": [
                    {"name": "💸 Gasto total", "value": formatear_cantidad_total(total_cobre), "inline": False},
                    {
                        "name": "📦 Detalle",
                        "value": "\n".join(detalle_lineas) if detalle_lineas else f"{sum(e['quantity'] for e in eventos)} item(s)",
                        "inline": False,
                    },
                ],
                "footer": {
                    "text": "Espia de Mercado",
                    "icon_url": "https://wiki.guildwars2.com/images/thumb/7/7b/Gold_coin.png/20px-Gold_coin.png",
                },
            }
        ],
    }
    response = requests.post(DISCORD_WEBHOOK_URL, json=data, timeout=TIMEOUT)
    response.raise_for_status()


def enviar_discord_inicializacion():
    """Envía un mensaje de inicialización a Discord con el estado actual."""
    if not DISCORD_HABILITADO:
        return
    
    headers = {"Authorization": f"Bearer {GW2_API_KEY}"}
    nombre_personaje = "Desconocido"
    oro_cuenta = 0
    
    try:
        # Obtener nombre de cuenta
        response = requests.get("https://api.guildwars2.com/v2/account", headers=headers, timeout=TIMEOUT)
        response.raise_for_status()
        account_data = response.json()
        nombre_personaje = account_data.get("name", "Desconocido")
    except Exception as e:
        print(f"Error consultando cuenta para inicialización: {e}")
    
    try:
        # Obtener oro de la cuenta
        response = requests.get("https://api.guildwars2.com/v2/account/wallet", headers=headers, timeout=TIMEOUT)
        response.raise_for_status()
        wallet = response.json()
        for moneda in wallet:
            if moneda.get("id") == 1:
                oro_cuenta = moneda.get("value", 0)
                break
    except Exception as e:
        print(f"Error consultando oro para inicialización: {e}")

    entregas = obtener_entregas_pendientes()
    coins_pendientes = entregas["coins"]
    items_pendientes = entregas["items"]
    items_pendientes_lineas = formatear_items_entrega(items_pendientes)
    
    # Obtener órdenes pendientes
    ventas_pendientes = 0
    compras_pendientes = 0
    ventas_detalladas = []
    ganancia_estimada = 0
    
    ventas_actuales = []
    try:
        response = requests.get("https://api.guildwars2.com/v2/commerce/transactions/current/sells", 
                              headers=headers, timeout=TIMEOUT)
        response.raise_for_status()
        ventas_actuales = response.json()
        ventas_pendientes = len(ventas_actuales)
    except Exception as e:
        print(f"Error consultando ventas para inicialización: {e}")

    ventas_detalladas, ganancia_estimada = obtener_ventas_pendientes_detalladas(ventas_actuales)
    
    try:
        response = requests.get("https://api.guildwars2.com/v2/commerce/transactions/current/buys", 
                              headers=headers, timeout=TIMEOUT)
        response.raise_for_status()
        compras_pendientes = len(response.json())
    except Exception as e:
        print(f"Error consultando compras para inicialización: {e}")
    
    oro_formateado = formato_oro(oro_cuenta)
    ping = f"<@{DISCORD_USER_ID}> " if DISCORD_USER_ID else ""
    ventas_lineas = [
        f"• {venta['item_name']} x{venta['quantity']}"
        for venta in ventas_detalladas[:5]
    ]
    if len(ventas_detalladas) > 5:
        ventas_lineas.append(f"• +{len(ventas_detalladas) - 5} más")
    if not ventas_lineas:
        ventas_lineas = ["Nada en venta"]
    
    data = {
        "username": "Esclavo de bajos recursos",
        "avatar_url": "https://wiki.guildwars2.com/images/d/df/Black_Lion_Trading_Company_trading_post_icon.png",
        "content": f"{ping}🚀 Sistema iniciado",
        "embeds": [
            {
                "title": "🚀 Vigía del León Negro - Iniciado",
                "description": "El sistema de monitoreo está activo y listo.",
                "color": 16763904,
                "fields": [
                    {
                        "name": "👤 Estado de cuenta",
                        "value": f"**Personaje:** {nombre_personaje}\n**Oro disponible:** {oro_formateado}",
                        "inline": False,
                    },
                    {
                        "name": "📤 Pendiente para la venta",
                        "value": "\n".join(ventas_lineas) + f"\n**Ganancia estimada neta:** {formato_oro(ganancia_estimada)}",
                        "inline": False,
                    },
                    {
                        "name": "📬 Pendiente para recoger",
                        "value": f"**Oro en bandeja:** {formato_oro(coins_pendientes)}\n" + "\n".join(items_pendientes_lineas),
                        "inline": False,
                    },
                ],
                "footer": {
                    "text": "Espia de Mercado",
                    "icon_url": "https://wiki.guildwars2.com/images/thumb/7/7b/Gold_coin.png/20px-Gold_coin.png",
                },
            }
        ],
    }
    
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=data, timeout=TIMEOUT)
        response.raise_for_status()
        print(f"[{time.strftime('%H:%M:%S')}] Mensaje de inicialización enviado a Discord ✅")
    except Exception as e:
        print(f"Error enviando mensaje de inicialización a Discord: {e}")


def check_trading_post(estado_previo):
    url = "https://api.guildwars2.com/v2/commerce/transactions/current/sells"
    headers = {"Authorization": f"Bearer {GW2_API_KEY}"}

    try:
        response = requests.get(url, headers=headers, timeout=TIMEOUT)
        response.raise_for_status()
        ventas_actuales = response.json()
        cantidad = len(ventas_actuales)

        if cantidad == 0 and estado_previo.get("habia_ventas_activas", False):
            coins_actuales, items_actuales = revisar_entregas()
            delta_coins = max(0, coins_actuales - estado_previo.get("coins", 0))
            delta_items = max(0, items_actuales - estado_previo.get("items", 0))

            if delta_coins > 0 or delta_items > 0:
                enviar_discord_embed(delta_coins, delta_items)
                estado_previo["coins"] = coins_actuales
                estado_previo["items"] = items_actuales
                # FIX: actualizar el flag ANTES de guardar
                estado_previo["habia_ventas_activas"] = False
                guardar_estado(estado_previo)
                return True

            print(f"[{time.strftime('%H:%M:%S')}] Sin ganancia nueva en bandeja; no se envía ping.")
            estado_previo["coins"] = coins_actuales
            estado_previo["items"] = items_actuales
            # FIX: también bajar el flag aquí antes de guardar
            estado_previo["habia_ventas_activas"] = False
            guardar_estado(estado_previo)
            return False

        if cantidad > 0:
            estado_previo["habia_ventas_activas"] = True
            # FIX: persistir el flag de ventas activas inmediatamente
            guardar_estado(estado_previo)
            print(f"[{time.strftime('%H:%M:%S')}] Aún tienes {cantidad} publicación(es) activa(s).")
        else:
            print(f"[{time.strftime('%H:%M:%S')}] Sin publicaciones activas (esperando transición real de venta).")

    except Exception as e:
        print(f"Error de conexión: {e}")

    return False


def check_buy_orders(estado_previo):
    url = "https://api.guildwars2.com/v2/commerce/transactions/current/buys"
    headers = {"Authorization": f"Bearer {GW2_API_KEY}"}

    try:
        response = requests.get(url, headers=headers, timeout=TIMEOUT)
        response.raise_for_status()
        compras_actuales = response.json()
        compras_actuales_map = normalizar_ordenes_compras(compras_actuales)
        compras_previas = estado_previo.get("buy_orders", {})

        if not compras_previas:
            estado_previo["buy_orders"] = compras_actuales_map
            guardar_estado(estado_previo)
            print(f"[{time.strftime('%H:%M:%S')}] Snapshot inicial de compras guardado ({len(compras_actuales_map)} orden(es)).")
            return False

        eventos = []
        item_ids = set()

        for order_id, orden_previa in compras_previas.items():
            orden_actual = compras_actuales_map.get(order_id)

            if orden_actual is None:
                # Orden desapareció completamente → llenada al 100%
                filled_qty = int(orden_previa.get("quantity", 0) or 0)
            else:
                filled_qty = int(orden_previa.get("quantity", 0) or 0) - int(orden_actual.get("quantity", 0) or 0)

            if filled_qty <= 0:
                continue

            unit_price = int(orden_previa.get("price", 0) or 0)
            item_id = int(orden_previa.get("item_id", 0) or 0)
            item_ids.add(item_id)
            eventos.append({
                "order_id": order_id,
                "item_id": item_id,
                "quantity": filled_qty,
                "unit_price": unit_price,
                "total_cobre": unit_price * filled_qty,
                "item_name": f"Item {item_id}",
            })

        if eventos:
            nombres = obtener_nombres_items(item_ids)
            for evento in eventos:
                evento["item_name"] = nombres.get(str(evento["item_id"]), evento["item_name"])
            enviar_discord_compra_embed(eventos)

        estado_previo["buy_orders"] = compras_actuales_map
        guardar_estado(estado_previo)

        if eventos:
            print(f"[{time.strftime('%H:%M:%S')}] Se completaron {len(eventos)} compra(s) programada(s).")

        return bool(eventos)

    except Exception as e:
        print(f"Error consultando compras: {e}")
        return False


def reportar_pendientes():
    """Muestra en terminal las órdenes de venta y compra pendientes (sin enviar a Discord)."""
    # Obtener información de la cuenta
    headers = {"Authorization": f"Bearer {GW2_API_KEY}"}
    nombre_personaje = "Desconocido"
    oro_cuenta = 0
    
    try:
        # Obtener nombre de cuenta
        response = requests.get("https://api.guildwars2.com/v2/account", headers=headers, timeout=TIMEOUT)
        response.raise_for_status()
        account_data = response.json()
        nombre_personaje = account_data.get("name", "Desconocido")
    except Exception as e:
        print(f"Error consultando cuenta: {e}")
    
    try:
        # Obtener oro de la cuenta (wallet)
        response = requests.get("https://api.guildwars2.com/v2/account/wallet", headers=headers, timeout=TIMEOUT)
        response.raise_for_status()
        wallet = response.json()
        # El oro es la moneda con currency_id 1
        for moneda in wallet:
            if moneda.get("id") == 1:
                oro_cuenta = moneda.get("value", 0)
                break
    except Exception as e:
        print(f"Error consultando oro: {e}")
    
    # Órdenes de venta pendientes
    url_ventas = "https://api.guildwars2.com/v2/commerce/transactions/current/sells"
    
    ventas_pendientes = []
    compras_pendientes = []
    
    ventas_actuales = []
    try:
        response = requests.get(url_ventas, headers=headers, timeout=TIMEOUT)
        response.raise_for_status()
        ventas_actuales = response.json()
        if ventas_actuales:
            item_ids = {int(v.get("item_id", 0)) for v in ventas_actuales}
            nombres = obtener_nombres_items(item_ids)
            for venta in ventas_actuales:
                item_id = int(venta.get("item_id", 0))
                item_name = nombres.get(str(item_id), f"Item {item_id}")
                cantidad = int(venta.get("quantity", 0) or 0)
                precio = int(venta.get("price", 0) or 0)
                ventas_pendientes.append({
                    "item_name": item_name,
                    "quantity": cantidad,
                    "price": precio,
                    "total": precio * cantidad,
                })
    except Exception as e:
        print(f"Error consultando ventas pendientes: {e}")

    ventas_detalladas, ganancia_estimada = obtener_ventas_pendientes_detalladas(ventas_actuales)
    
    # Órdenes de compra pendientes
    url_compras = "https://api.guildwars2.com/v2/commerce/transactions/current/buys"
    try:
        response = requests.get(url_compras, headers=headers, timeout=TIMEOUT)
        response.raise_for_status()
        compras = response.json()
        if compras:
            item_ids = {int(c.get("item_id", 0)) for c in compras}
            nombres = obtener_nombres_items(item_ids)
            for compra in compras:
                item_id = int(compra.get("item_id", 0))
                item_name = nombres.get(str(item_id), f"Item {item_id}")
                cantidad = int(compra.get("quantity", 0) or 0)
                precio = int(compra.get("price", 0) or 0)
                compras_pendientes.append({
                    "item_name": item_name,
                    "quantity": cantidad,
                    "price": precio,
                    "total": precio * cantidad,
                })
    except Exception as e:
        print(f"Error consultando compras pendientes: {e}")
    
    # Mostrar resumen en terminal
    oro_formateado = formato_oro(oro_cuenta)
    entregas = obtener_entregas_pendientes()
    oro_pendiente = entregas["coins"]
    items_pendientes = entregas["items"]
    items_pendientes_lineas = formatear_items_entrega(items_pendientes)
    print(f"\n[{time.strftime('%H:%M:%S')}] ═══════════════════════════════════")
    print(f"[{time.strftime('%H:%M:%S')}] 📋 ESTADO DE CUENTA")
    print(f"[{time.strftime('%H:%M:%S')}] ═══════════════════════════════════")
    print(f"[{time.strftime('%H:%M:%S')}] 👤 Personaje: {nombre_personaje}")
    print(f"[{time.strftime('%H:%M:%S')}] 💰 Oro disponible: {oro_formateado}")
    print(f"[{time.strftime('%H:%M:%S')}] ═══════════════════════════════════")
    print(f"[{time.strftime('%H:%M:%S')}] 📤 PENDIENTE PARA LA VENTA")
    if ventas_detalladas:
        for venta in ventas_detalladas[:5]:
            print(f"[{time.strftime('%H:%M:%S')}]   • {venta['item_name']} x{venta['quantity']} = {formatear_cantidad_total(venta['total_bruto'])}")
        if len(ventas_detalladas) > 5:
            print(f"[{time.strftime('%H:%M:%S')}]   • +{len(ventas_detalladas) - 5} más")
        print(f"[{time.strftime('%H:%M:%S')}]   • Ganancia estimada neta: {formato_oro(ganancia_estimada)}")
    else:
        print(f"[{time.strftime('%H:%M:%S')}]   • Nada en venta")
    print(f"[{time.strftime('%H:%M:%S')}] ═══════════════════════════════════")
    print(f"[{time.strftime('%H:%M:%S')}] 📬 PENDIENTE PARA RECOGER")
    print(f"[{time.strftime('%H:%M:%S')}]   • Oro en bandeja: {formato_oro(oro_pendiente)}")
    for linea in items_pendientes_lineas:
        print(f"[{time.strftime('%H:%M:%S')}]   {linea}")
    print(f"[{time.strftime('%H:%M:%S')}] ═══════════════════════════════════")
    
    if ventas_pendientes:
        print(f"[{time.strftime('%H:%M:%S')}] 📤 VENTAS PENDIENTES ({len(ventas_pendientes)}):")
        for venta in ventas_pendientes:
            total_formateado = formatear_cantidad_total(venta["total"])
            print(f"[{time.strftime('%H:%M:%S')}]   • {venta['item_name']} x{venta['quantity']} @ {formatear_cantidad_total(venta['price'])} = {total_formateado}")
    else:
        print(f"[{time.strftime('%H:%M:%S')}] 📤 VENTAS PENDIENTES: Ninguna")
    
    if compras_pendientes:
        print(f"[{time.strftime('%H:%M:%S')}] 📥 COMPRAS PENDIENTES ({len(compras_pendientes)}):")
        for compra in compras_pendientes:
            total_formateado = formatear_cantidad_total(compra["total"])
            print(f"[{time.strftime('%H:%M:%S')}]   • {compra['item_name']} x{compra['quantity']} @ {formatear_cantidad_total(compra['price'])} = {total_formateado}")
    else:
        print(f"[{time.strftime('%H:%M:%S')}] 📥 COMPRAS PENDIENTES: Ninguna")
    
    print(f"[{time.strftime('%H:%M:%S')}] ═══════════════════════════════════\n")


# --- BUCLE PRINCIPAL ---
print("Iniciando vigía del León Negro con módulo financiero...")
cargar_env_local()
cargar_configuracion()
validar_configuracion()

coins_prev, items_prev = revisar_entregas()
estado = cargar_estado_previo()

# Toma el valor más alto conocido para evitar restar contra un snapshot viejo.
estado["coins"] = max(estado.get("coins", 0), coins_prev)
estado["items"] = max(estado.get("items", 0), items_prev)

# FIX: NO resetear habia_ventas_activas al reiniciar.
# Si el estado guardado ya tenía ventas activas, se respeta para no perder la transición.
if "habia_ventas_activas" not in estado:
    estado["habia_ventas_activas"] = False

guardar_estado(estado)

enviar_discord_inicializacion()

while True:
    todo_vendido = check_trading_post(estado)
    compras_completadas = check_buy_orders(estado)

    if todo_vendido:
        print("¡Reporte financiero enviado a Discord!")

    if compras_completadas:
        print("¡Reporte de compras enviado a Discord!")
    
    # Mostrar resumen de pendientes en terminal (solo local, no en Discord)
    reportar_pendientes()

    time.sleep(TIEMPO_ESPERA)
