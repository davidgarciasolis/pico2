import network
import ntptime
import machine
import time
import urequests
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


def conectar_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if not wlan.isconnected():
        wlan.connect(WIFI_SSID, WIFI_PASS)

        while not wlan.isconnected():
            led.toggle()
            print("Conectando WiFi...")
            time.sleep(0.5)

    led.on()

    print("WiFi conectado")
    print(wlan.ifconfig())


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


def esperar_hasta_siguiente_minuto():
    """Alinea cada ciclo de medición con el siguiente minuto."""
    segundos_actuales = time.localtime()[5]
    segundos_espera = 60 - segundos_actuales

    print("Esperando", segundos_espera, "segundos para iniciar la medición")
    time.sleep(segundos_espera)


conectar_wifi()
sincronizar_hora()

while True:

    esperar_hasta_siguiente_minuto()

    try:

        print("Iniciando medición de temperatura y humedad (60 segundos)...")
        suma_temperaturas = 0
        suma_humedades = 0
        
        for _ in range(60):
            led.toggle()
            suma_temperaturas += leer_temperatura()
            suma_humedades += leer_humedad()
            time.sleep(1)
            
        temperatura_media = round(suma_temperaturas / 60, 2)
        humedad_media = round(suma_humedades / 60, 1)

        print("Temperatura media:", temperatura_media, "°C")
        print("Humedad media:", humedad_media, "%")
        print("Fecha:", fecha_iso())

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
