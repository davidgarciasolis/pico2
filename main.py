import network
import ntptime
import machine
import time
import urequests
import socket
from secrets import *

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

# Red local del dispositivo. La máscara /23 equivale a 255.255.254.0.
IP_FIJA = "192.168.0.5"
MASCARA_RED = "255.255.254.0"
PUERTA_ENLACE = "192.168.0.1"
DNS = PUERTA_ENLACE

# Última lectura disponible para la página local.
ultima_medicion = {
    "temperatura": None,
    "humedad": None,
    "fecha": None,
}
servidor = None


def conectar_wifi():
    """Intenta conectarse durante 10 segundos sin bloquear el programa."""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    # Debe hacerse antes de connect(). Reserva esta IP en el router o verifica
    # que ningún otro equipo la esté usando para evitar un conflicto de IP.
    try:
        wlan.ifconfig((IP_FIJA, MASCARA_RED, PUERTA_ENLACE, DNS))
    except Exception as e:
        print("No se pudo configurar la IP fija:", e)
        return False

    if wlan.isconnected():
        print("WiFi conectado")
        return True

    try:
        wlan.connect(WIFI_SSID, WIFI_PASS)
    except Exception as e:
        print("No se pudo iniciar la conexión WiFi:", e)
        led.off()
        return False

    for _ in range(20):
        if wlan.isconnected():
            led.on()
            print("WiFi conectado")
            print(wlan.ifconfig())
            return True

        led.toggle()
        print("Conectando WiFi...")
        time.sleep(0.5)

    print("No se pudo conectar al WiFi. Se reintentará dentro de una hora.")
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
    print("Servidor web disponible en http://{}/".format(IP_FIJA))


def pagina_web():
    """Genera la página con la última lectura realizada por la Pico."""
    temperatura = ultima_medicion["temperatura"]
    humedad = ultima_medicion["humedad"]
    fecha = ultima_medicion["fecha"]

    temperatura_txt = "--" if temperatura is None else "{} &deg;C".format(temperatura)
    humedad_txt = "--" if humedad is None else "{} %".format(humedad)
    fecha_txt = "Aún no hay mediciones" if fecha is None else fecha

    return """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sensor ambiental</title>
<style>body{margin:0;font-family:system-ui,sans-serif;background:#f1f5f9;color:#0f172a}.contenedor{max-width:680px;margin:8vh auto;padding:24px}h1{margin-bottom:8px}.fecha{color:#64748b}.medidas{display:flex;gap:16px;flex-wrap:wrap;margin-top:24px}.medida{flex:1;min-width:220px;padding:24px;border-radius:16px;background:#fff;box-shadow:0 8px 22px #0f172a18}.etiqueta{color:#64748b;font-size:.9rem;text-transform:uppercase;letter-spacing:.08em}.valor{font-size:2.4rem;font-weight:700;margin-top:8px}button{margin-top:24px;padding:12px 18px;border:0;border-radius:10px;background:#ea580c;color:#fff;font:inherit;font-weight:700;cursor:pointer}button:active{transform:scale(.98)}</style>
</head><body><main class="contenedor"><h1>Sensor ambiental</h1><p class="fecha">Última lectura: {}</p><section class="medidas"><article class="medida"><div class="etiqueta">Temperatura</div><div class="valor">{}</div></article><article class="medida"><div class="etiqueta">Humedad del suelo</div><div class="valor">{}</div></article></section><form action="/medir" method="get"><button type="submit">Medir ahora</button></form></main></body></html>""".format(fecha_txt, temperatura_txt, humedad_txt)


def medir_desde_web():
    """Actualiza la lectura bajo demanda, sin enviarla a la API remota."""
    ultima_medicion["temperatura"] = leer_temperatura()
    ultima_medicion["humedad"] = leer_humedad()
    ultima_medicion["fecha"] = fecha_iso()
    print("Medición solicitada desde la web:", ultima_medicion)


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
        peticion = cliente.recv(512).decode("utf-8")
        linea = peticion.split("\r\n", 1)[0]

        if linea.startswith("GET /medir"):
            medir_desde_web()
            respuesta = "HTTP/1.1 303 See Other\r\nLocation: /\r\nConnection: close\r\n\r\n"
            cliente.send(respuesta)
            return

        cuerpo = pagina_web()
        respuesta = "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n" + cuerpo
        cliente.send(respuesta)
    except Exception as e:
        print("Error atendiendo la web:", e)
    finally:
        cliente.close()


def esperar_con_web(segundos):
    """Espera sin dejar de responder peticiones HTTP."""
    fin = time.time() + segundos
    while time.time() < fin:
        atender_web()
        time.sleep(0.1)


def sincronizar_hora():
    ntptime.settime()
    print("Hora sincronizada")


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

    print("Respuesta API:", r.text)

    r.close()


def esperar_hasta_siguiente_hora():
    """Alinea cada ciclo de medición con el comienzo de la próxima hora."""
    ahora = time.localtime()
    segundos_actuales = ahora[4] * 60 + ahora[5]
    segundos_espera = 3600 - segundos_actuales

    print("Esperando", segundos_espera, "segundos para iniciar la medición")
    esperar_con_web(segundos_espera)


if conectar_wifi():
    iniciar_servidor_web()
    try:
        sincronizar_hora()
    except Exception as e:
        print("No se pudo sincronizar la hora:", e)

    # Ofrece un valor desde el arranque; los ciclos posteriores publican la
    # media de 60 segundos tanto en esta página como en la API.
    try:
        ultima_medicion["temperatura"] = leer_temperatura()
        ultima_medicion["humedad"] = leer_humedad()
        ultima_medicion["fecha"] = fecha_iso()
    except Exception as e:
        print("No se pudo obtener la lectura inicial:", e)

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
            print("No se pudo sincronizar la hora:", e)

        print("Iniciando medición de temperatura y humedad (60 segundos)...")
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

        print("Temperatura media:", temperatura_media, "°C")
        print("Humedad media:", humedad_media, "%")
        print("Fecha:", fecha_iso())

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

        print("ERROR:", e)

        led.off()
