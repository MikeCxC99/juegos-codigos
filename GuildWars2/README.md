# Guild Wars 2 — EsclavoTrade

Monitor automático del **Black Lion Trading Post** de Guild Wars 2. Supervisa tus órdenes de venta y compra en tiempo real y te avisa por Discord cuando se completan, para que no tengas que quedarte mirando la pantalla.

---

## Tabla de contenidos

- [¿Qué hace?](#qué-hace)
- [Capacidades](#capacidades)
- [Requisitos](#requisitos)
- [Instalación y configuración](#instalación-y-configuración)
- [Uso](#uso)
- [Variables de entorno](#variables-de-entorno)
- [Formato de moneda](#formato-de-moneda)
- [Cómo funciona internamente](#cómo-funciona-internamente)
- [Archivo de estado](#archivo-de-estado)

---

## ¿Qué hace?

`EsclavoTrade.py` es un script que se conecta a la API oficial de Guild Wars 2 y comprueba cada 5 minutos si tienes ventas o compras completadas en el Mercado del León Negro. Cuando detecta un cambio, muestra un resumen en la terminal y (opcionalmente) envía un mensaje enriquecido a un canal de Discord.

---

## Capacidades

| Capacidad | Descripción |
|-----------|-------------|
| 📤 **Monitor de ventas** | Detecta cuando todas tus publicaciones activas se han vendido y calcula la ganancia neta (después del 15 % de impuesto del mercado). |
| 📥 **Monitor de órdenes de compra** | Detecta qué parte de cada orden de compra se ha llenado desde la última comprobación. |
| 📬 **Bandeja de entregas** | Informa del oro y los ítems que tienes pendientes de recoger en la bandeja del mercado. |
| 💰 **Estado de cuenta** | Muestra el nombre de tu cuenta y el oro disponible en la cartera al iniciarse y en cada ciclo. |
| 🔔 **Notificaciones Discord** | Envía embeds ricos a Discord al iniciar el script, al cerrar ventas y al llenarse órdenes de compra. Soporta mención de usuario con `DISCORD_USER_ID`. |
| 🏷️ **Resolución de nombres de ítems** | Consulta la API de ítems de GW2 para mostrar nombres reales en lugar de IDs numéricos, con caché en memoria. |
| 💾 **Estado persistente** | Guarda el snapshot del estado en `esclavo_trade_state.json` para sobrevivir reinicios sin generar alertas duplicadas. |
| 🖥️ **Modo solo terminal** | Funciona completamente sin Discord: todos los reportes se muestran en la consola. |

---

## Requisitos

- Python 3.8 o superior
- Una cuenta de Guild Wars 2 con acceso al Trading Post
- Una API Key de GW2 con los permisos **`tradingpost`** y **`account`** (y **`wallet`** si quieres ver el oro de la cuenta)
- (Opcional) Un webhook de Discord

---

## Instalación y configuración

```bash
# 1. Clona el repositorio (si no lo tienes ya)
git clone https://github.com/MikeCxC99/juegos-codigos.git
cd juegos-codigos/GuildWars2

# 2. Instala las dependencias
pip install -r requirements.txt

# 3. Crea tu archivo de entorno
cp .env.example .env
```

Edita el archivo `.env` y completa los valores:

```env
GW2_API_KEY=TU_API_KEY_AQUI
DISCORD_HABILITADO=True          # False si no quieres Discord
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
DISCORD_USER_ID=123456789012345678   # tu ID de usuario Discord (opcional)
```

---

## Uso

```bash
python EsclavoTrade.py
```

El script arranca, muestra el estado actual en terminal y en Discord (si está habilitado), y luego entra en un bucle que comprueba el mercado cada **5 minutos**.

**Salida de ejemplo en terminal:**

```
Iniciando vigía del León Negro con módulo financiero...
[12:00:00] ═══════════════════════════════════
[12:00:00] 📋 ESTADO DE CUENTA
[12:00:00] ═══════════════════════════════════
[12:00:00] 👤 Personaje: MiCuenta.1234
[12:00:00] 💰 Oro disponible: 42 🥇 | 17 🥈 | 05 🥉
[12:00:00] ═══════════════════════════════════
[12:00:00] 📤 PENDIENTE PARA LA VENTA
[12:00:00]   • Orichalcum Ore x250 = 12g 50s 00c
[12:00:00]   • Ganancia estimada neta: 10 🥇 | 37 🥈 | 30 🥉
[12:00:00] ═══════════════════════════════════
[12:00:00] 📬 PENDIENTE PARA RECOGER
[12:00:00]   • Oro en bandeja: 5 🥇 | 00 🥈 | 00 🥉
[12:00:00]   • Nada para recoger
[12:00:00] ═══════════════════════════════════
```

Para detener el script usa `Ctrl + C`.

---

## Variables de entorno

| Variable | Obligatoria | Descripción |
|----------|-------------|-------------|
| `GW2_API_KEY` | ✅ Sí | API Key de Guild Wars 2 con permisos `tradingpost`, `account` y `wallet`. |
| `DISCORD_HABILITADO` | No | `True` para activar notificaciones Discord. Por defecto `False`. |
| `DISCORD_WEBHOOK_URL` | Si Discord activo | URL completa del webhook de Discord. |
| `DISCORD_USER_ID` | No | ID numérico de tu usuario en Discord para que los mensajes te mencionen. |

El script carga `.env` automáticamente si existe en el directorio de trabajo. Las variables de entorno del sistema tienen prioridad sobre el archivo `.env`.

---

## Formato de moneda

Guild Wars 2 expresa todos los valores en **cobre**. El script convierte automáticamente:

| Unidad | Equivalencia |
|--------|-------------|
| 🥉 Cobre (c) | 1 c |
| 🥈 Plata (s) | 100 c |
| 🥇 Oro (g) | 100 s = 10 000 c |

Ejemplo: `152 314 c` → `15g 23s 14c`.

---

## Cómo funciona internamente

1. **Arranque**: carga `.env`, valida configuración, toma snapshot inicial y envía mensaje de inicio a Discord.
2. **Bucle (cada 5 min)**:
   - `check_trading_post`: compara el número de ventas activas con el ciclo anterior. Si pasó de "tenía ventas" a "cero ventas", calcula el delta de monedas/ítems en la bandeja y envía alerta.
   - `check_buy_orders`: compara las órdenes de compra actuales con el snapshot guardado. Cualquier orden desaparecida o con cantidad reducida se reporta como llenada.
   - `reportar_pendientes`: imprime en terminal el estado completo (cuenta, ventas activas, bandeja, compras pendientes).
3. **Persistencia**: cada cambio se guarda en `esclavo_trade_state.json` para evitar alertas duplicadas al reiniciar.

---

## Archivo de estado

`esclavo_trade_state.json` se crea automáticamente en el directorio de trabajo. Contiene:

```json
{
  "coins": 150000,
  "items": 3,
  "habia_ventas_activas": true,
  "buy_orders": {
    "12345678": {"item_id": 19700, "quantity": 250, "price": 50}
  }
}
```

Puedes borrarlo de forma segura; el script generará un nuevo snapshot en el siguiente inicio (sin enviar alertas falsas).
