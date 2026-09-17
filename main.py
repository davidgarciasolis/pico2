import network
import ntptime
import machine
import time
import urequests
import socket
import os
from secrets import *

# Añade OTA_PASSWORD a secrets.py antes de usar la actualización web.
# No se guarda en main.py ni se expone en la página.
try:
    OTA_PASSWORD
except NameError:
    OTA_PASSWORD = None

# Sensor temperatura TMP36 (GP28)
sensor_temp = machine.ADC(28)

# Sensor capacitivo de humedad del suelo (AOUT conectado a GP26 / ADC0).
# Debe alimentarse a 3V3 para que su salida no supere los 3,3 V.
sensor_humedad = machine.ADC(26)

# Ajusta estos valores después de calibrar el sensor: al aire/tierra seca y
# en tierra bien húmeda. En este sensor, una lectura menor indica más humedad.
LECTURA_SECO = 50000
LECTURA_HUMEDO = 20000

# LED integrado Pico 2W
led = machine.Pin("LED", machine.Pin.OUT)

# Configuración de red fija, obtenida de la concesión DHCP mostrada en consola.
IP_FIJA = "192.168.0.5"
MASCARA_RED = "255.255.254.0"
PUERTA_ENLACE = "192.168.0.1"
DNS = "100.100.1.1"

# Direcciones IP de servidores NTP públicos. Usar IP evita que un fallo de
# resolución DNS impida ajustar el reloj.
SERVIDORES_NTP = (
    "162.159.200.1",     # time.cloudflare.com
    "216.239.32.15",     # time.google.com
)

# Última lectura disponible para la página local.
ultima_medicion = {
    "temperatura": None,
    "humedad": None,
    "fecha": None,
}
servidor = None
MAX_TAMANO_MAIN = 32 * 1024
MAX_LOGS = 40
logs = []


def registrar(*valores):
    """Muestra el mensaje por consola y conserva las últimas líneas web."""
    mensaje = " ".join(str(valor) for valor in valores)
    print(mensaje)
    logs.append(mensaje)
    if len(logs) > MAX_LOGS:
        logs.pop(0)


def escapar_html(texto):
    return str(texto).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def conectar_wifi():
    """Conecta al WiFi con la configuración de red fija."""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    try:
        wlan.ifconfig((IP_FIJA, MASCARA_RED, PUERTA_ENLACE, DNS))
    except Exception as e:
        registrar("No se pudo configurar la IP fija:", e)
        return False

    if wlan.isconnected():
        registrar("WiFi conectado")
        registrar(wlan.ifconfig())
        return True

    try:
        # La IP ya está configurada; solo falta asociarse al punto de acceso.
        wlan.connect(WIFI_SSID, WIFI_PASS)
    except Exception as e:
        registrar("No se pudo iniciar la conexión WiFi:", e)
        led.off()
        return False

    for _ in range(20):
        if wlan.isconnected():
            led.on()
            registrar("WiFi conectado")
            registrar(wlan.ifconfig())
            return True

        led.toggle()
        registrar("Conectando WiFi...")
        time.sleep(0.5)

    registrar("No se pudo conectar al WiFi.")
    led.off()
    return False


def iniciar_servidor_web():
    """Inicia una página HTTP local no bloqueante en el puerto 80."""
    global servidor

    if servidor is not None:
        return

    direccion = socket.getaddrinfo("0.0.0.0", 80)[0][-1]
    servidor = socket.socket()
    servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    servidor.bind(direccion)
    servidor.listen(1)
    servidor.settimeout(0)
    ip = network.WLAN(network.STA_IF).ifconfig()[0]
    registrar("Servidor web disponible en http://{}/".format(ip))


def pagina_web():
    """Genera la página con la última lectura realizada por la Pico."""
    temperatura = ultima_medicion["temperatura"]
    humedad = ultima_medicion["humedad"]
    fecha = ultima_medicion["fecha"]

    temperatura_txt = "--" if temperatura is None else "{} &deg;C".format(temperatura)
    humedad_txt = "--" if humedad is None else "{} %".format(humedad)
    fecha_txt = "Aún no hay mediciones" if fecha is None else fecha
    logs_txt = "\n".join([escapar_html(linea) for linea in logs]) or "Aún no hay logs."

    return """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sensor ambiental</title>
<style>body{margin:0;font-family:system-ui,sans-serif;background:#f1f5f9;color:#0f172a}.contenedor{max-width:680px;margin:8vh auto;padding:24px}h1{margin-bottom:8px}.fecha{color:#64748b}.medidas{display:flex;gap:16px;flex-wrap:wrap;margin-top:24px}.medida{flex:1;min-width:220px;padding:24px;border-radius:16px;background:#fff;box-shadow:0 8px 22px #0f172a18}.etiqueta{color:#64748b;font-size:.9rem;text-transform:uppercase;letter-spacing:.08em}.valor{font-size:2.4rem;font-weight:700;margin-top:8px}button{margin-top:24px;padding:12px 18px;border:0;border-radius:10px;background:#ea580c;color:#fff;font:inherit;font-weight:700;cursor:pointer}button:active{transform:scale(.98)}pre{max-height:280px;overflow:auto;padding:14px;border-radius:10px;background:#0f172a;color:#d1fae5;font:12px/1.5 monospace;white-space:pre-wrap}</style>
</head><body><main class="contenedor"><h1>Sensor ambiental</h1><p class="fecha">Última lectura: __FECHA__</p><section class="medidas"><article class="medida"><div class="etiqueta">Temperatura</div><div class="valor">__TEMPERATURA__</div></article><article class="medida"><div class="etiqueta">Humedad del suelo</div><div class="valor">__HUMEDAD__</div></article></section><form action="/medir" method="get"><button type="submit">Medir ahora</button></form><hr><h2>Logs de ejecución</h2><form action="/" method="get"><button type="submit">Actualizar logs</button></form><pre>__LOGS__</pre><hr><h2>Actualizar programa</h2><form action="/actualizar" method="post" enctype="multipart/form-data"><label>Archivo main.py <input name="archivo" type="file" accept=".py" required></label><label>Contraseña <input name="password" type="password" required></label><button type="submit">Subir y aplicar</button></form><p class="fecha">Se conserva una copia como main.py.bak. Reinicia la Pico tras una actualización correcta.</p></main></body></html>""".replace("__FECHA__", fecha_txt).replace("__TEMPERATURA__", temperatura_txt).replace("__HUMEDAD__", humedad_txt).replace("__LOGS__", logs_txt)


def medir_desde_web():
    """Actualiza la lectura bajo demanda, sin enviarla a la API remota."""
    ultima_medicion["temperatura"] = leer_temperatura()
    ultima_medicion["humedad"] = leer_humedad()
    ultima_medicion["fecha"] = fecha_iso()
    registrar("Medición solicitada desde la web:", ultima_medicion)


def responder(cliente, estado, cuerpo, tipo="text/html; charset=utf-8"):
    cabecera = "HTTP/1.1 {}\r\nContent-Type: {}\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n".format(estado, tipo)
    cliente.send(cabecera + cuerpo)


def recibir_peticion(cliente):
    """Recibe la petición completa, con un límite seguro para la Pico."""
    datos = b""
    while b"\r\n\r\n" not in datos and len(datos) <= 2048:
        bloque = cliente.recv(512)
        if not bloque:
            break
        datos += bloque

    cabecera, cuerpo = datos.split(b"\r\n\r\n", 1)
    texto_cabecera = cabecera.decode("utf-8")
    tamano = 0
    for linea in texto_cabecera.split("\r\n"):
        if linea.lower().startswith("content-length:"):
            tamano = int(linea.split(":", 1)[1].strip())
            break

    if tamano > MAX_TAMANO_MAIN + 1024:
        raise ValueError("El archivo supera el máximo de 32 KB")

    while len(cuerpo) < tamano:
        bloque = cliente.recv(min(1024, tamano - len(cuerpo)))
        if not bloque:
            raise ValueError("Carga incompleta")
        cuerpo += bloque

    return texto_cabecera, cuerpo


def extraer_archivo_multipart(cabecera, cuerpo):
    """Obtiene la contraseña y el contenido de main.py de un formulario."""
    limite = "boundary="
    posicion = cabecera.lower().find(limite)
    if posicion == -1:
        raise ValueError("Formulario de carga inválido")

    boundary = cabecera[posicion + len(limite):].split("\r\n", 1)[0].encode()
    password = None
    archivo = None

    for parte in cuerpo.split(b"--" + boundary):
        if b"\r\n\r\n" not in parte:
            continue
        info, contenido = parte.split(b"\r\n\r\n", 1)
        contenido = contenido.rstrip(b"\r\n")
        if b'name="password"' in info:
            password = contenido.decode("utf-8")
        elif b'name="archivo"' in info:
            archivo = contenido

    if password != OTA_PASSWORD:
        raise ValueError("Contraseña de actualización incorrecta")
    if not archivo:
        raise ValueError("No se recibió el archivo main.py")
    if len(archivo) > MAX_TAMANO_MAIN:
        raise ValueError("main.py supera el máximo de 32 KB")

    return archivo.decode("utf-8")


def actualizar_main(codigo):
    """Valida y sustituye main.py conservando la versión anterior."""
    compile(codigo, "main.py", "exec")

    with open("main.py.tmp", "w") as fichero:
        fichero.write(codigo)

    try:
        os.remove("main.py.bak")
    except OSError:
        pass
    os.rename("main.py", "main.py.bak")
    os.rename("main.py.tmp", "main.py")


def atender_web():
    """Atiende como máximo una petición para que las mediciones continúen."""
    if servidor is None:
        return

    try:
        cliente, _ = servidor.accept()
    except OSError:
        return

    try:
        cliente.settimeout(1)
        cabecera, cuerpo = recibir_peticion(cliente)
        linea = cabecera.split("\r\n", 1)[0]

        if linea.startswith("GET /medir"):
            medir_desde_web()
            respuesta = "HTTP/1.1 303 See Other\r\nLocation: /\r\nConnection: close\r\n\r\n"
            cliente.send(respuesta)
            return

        if linea.startswith("POST /actualizar"):
            try:
                codigo = extraer_archivo_multipart(cabecera, cuerpo)
                actualizar_main(codigo)
                responder(cliente, "200 OK", "<h1>Actualización aplicada</h1><p>main.py se ha guardado y la versión anterior está en main.py.bak.</p><p>Reinicia ahora la Pico para ejecutar el nuevo programa.</p>")
                registrar("main.py actualizado desde la web")
            except Exception as e:
                registrar("Error actualizando main.py:", e)
                responder(cliente, "400 Bad Request", "<h1>No se aplicó la actualización</h1><p>{}</p><p><a href=\"/\">Volver</a></p>".format(e))
            return

        cuerpo = pagina_web()
        responder(cliente, "200 OK", cuerpo)
    except Exception as e:
        registrar("Error atendiendo la web:", e)
    finally:
        cliente.close()


def esperar_con_web(segundos):
    """Espera sin dejar de responder peticiones HTTP."""
    fin = time.time() + segundos
    while time.time() < fin:
        atender_web()
        time.sleep(0.1)


def sincronizar_hora():
    """Sincroniza el reloj sin depender de la resolución DNS."""
    ultimo_error = None

    for servidor_ntp in SERVIDORES_NTP:
        try:
            ntptime.host = servidor_ntp
            ntptime.settime()
            registrar("Hora sincronizada con", servidor_ntp)
            return
        except Exception as e:
            ultimo_error = e
            registrar("No se pudo sincronizar con", servidor_ntp + ":", e)

    raise ultimo_error


def leer_temperatura():
    lectura = sensor_temp.read_u16()
    voltaje = lectura * (3.3 / 65535)

    temperatura = (voltaje - 0.5) * 100

    return round(temperatura, 2)


def leer_humedad():
    lectura = sensor_humedad.read_u16()
    humedad = (LECTURA_SECO - lectura) * 100 / (LECTURA_SECO - LECTURA_HUMEDO)

    # Evita valores fuera del rango por variaciones del sensor.
    return round(max(0, min(100, humedad)), 1)


def login_api():
    url = API_URL + "/auth/login"

    datos = {
        "email": API_USER,
        "password": API_PASS
    }

    r = urequests.post(url, json=datos)

    respuesta = r.json()

    r.close()

    return respuesta["data"]["access_token"]


def obtener_hora_madrid():
    t = time.localtime()
    # t[1] es mes, t[2] es mday, t[3] es hora, t[6] es weekday (0=lunes, 6=domingo)
    
    offset = 1 # Invierno
    
    if 3 < t[1] < 10:
        offset = 2
    elif t[1] == 3 and t[2] >= 25:
        domingo = t[2] + (6 - t[6])
        if domingo > 31:
            domingo -= 7
        if t[2] > domingo or (t[2] == domingo and t[3] >= 1):
            offset = 2
    elif t[1] == 10:
        if t[2] < 25:
            offset = 2
        else:
            domingo = t[2] + (6 - t[6])
            if domingo > 31:
                domingo -= 7
            if t[2] < domingo or (t[2] == domingo and t[3] < 1):
                offset = 2
                
    return time.localtime(time.time() + (offset * 3600))


def fecha_iso():
    t = obtener_hora_madrid()

    return "{:04d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}".format(
        t[0], t[1], t[2],
        t[3], t[4], t[5]
    )


def enviar_datos(token, temperatura, humedad):

    url = API_URL + "/items/temperaturas"

    payload = {
        "temperatura": temperatura,
        "humedad": humedad,
        "fecha": fecha_iso()
    }

    headers = {
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json"
    }

    r = urequests.post(
        url,
        json=payload,
        headers=headers
    )

    registrar("Respuesta API:", r.text)

    r.close()


def esperar_hasta_siguiente_hora():
    """Alinea cada ciclo de medición con el comienzo de la próxima hora."""
    ahora = time.localtime()
    segundos_actuales = ahora[4] * 60 + ahora[5]
    segundos_espera = 3600 - segundos_actuales

    registrar("Esperando", segundos_espera, "segundos para iniciar la medición")
    esperar_con_web(segundos_espera)


while not conectar_wifi():
    registrar("Reintentando WiFi dentro de 30 segundos...")
    time.sleep(30)

iniciar_servidor_web()
try:
    sincronizar_hora()
except Exception as e:
    registrar("No se pudo sincronizar la hora:", e)

# Ofrece un valor desde el arranque; los ciclos posteriores publican la
# media de 60 segundos tanto en esta página como en la API.
try:
    ultima_medicion["temperatura"] = leer_temperatura()
    ultima_medicion["humedad"] = leer_humedad()
    ultima_medicion["fecha"] = fecha_iso()
except Exception as e:
    registrar("No se pudo obtener la lectura inicial:", e)

while True:

    esperar_hasta_siguiente_hora()

    try:

        # Si el router estaba apagado al arrancar, aquí se reintenta cada hora.
        if not conectar_wifi():
            continue

        iniciar_servidor_web()

        try:
            sincronizar_hora()
        except Exception as e:
            # La falta de NTP no debe impedir el envío si la API está disponible.
            registrar("No se pudo sincronizar la hora:", e)

        registrar("Iniciando medición de temperatura y humedad (60 segundos)...")
        suma_temperaturas = 0
        suma_humedades = 0
        
        for _ in range(60):
            led.toggle()
            suma_temperaturas += leer_temperatura()
            suma_humedades += leer_humedad()
            # La página sigue respondiendo mientras se calcula la media.
            esperar_con_web(1)
            
        temperatura_media = round(suma_temperaturas / 60, 2)
        humedad_media = round(suma_humedades / 60, 1)

        registrar("Temperatura media:", temperatura_media, "°C")
        registrar("Humedad media:", humedad_media, "%")
        registrar("Fecha:", fecha_iso())

        ultima_medicion["temperatura"] = temperatura_media
        ultima_medicion["humedad"] = humedad_media
        ultima_medicion["fecha"] = fecha_iso()

        token = login_api()

        enviar_datos(
            token,
            temperatura_media,
            humedad_media
        )

        led.on()

    except Exception as e:

        registrar("ERROR:", e)

        led.off()
