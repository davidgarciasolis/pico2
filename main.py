import network
import ntptime
import machine
import time
import urequests
from secrets import *

# Sensor temperatura interno
sensor_temp = machine.ADC(4)

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

    temperatura = 27 - ((voltaje - 0.706) / 0.001721)

    return round(temperatura, 2)


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


def enviar_datos(token, temperatura):

    url = API_URL + "/items/temperaturas"

    payload = {
        "temperatura": temperatura,
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


def esperar_siguiente_hora():

    ahora = time.localtime()

    minutos_restantes = 59 - ahora[4]
    segundos_restantes = 60 - ahora[5]
    
    total_segundos = (minutos_restantes * 60) + segundos_restantes

    print("Esperando", total_segundos, "segundos para la próxima hora")

    time.sleep(total_segundos)


conectar_wifi()
sincronizar_hora()

while True:

    try:

        led.toggle()

        temperatura = leer_temperatura()

        print("Temperatura:", temperatura)
        print("Fecha:", fecha_iso())

        token = login_api()

        enviar_datos(
            token,
            temperatura
        )

        led.on()

    except Exception as e:

        print("ERROR:", e)

        led.off()

    esperar_siguiente_hora()