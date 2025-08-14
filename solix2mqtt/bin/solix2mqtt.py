import asyncio
from datetime import datetime
import json
import logging
import os
import random
import sys
import time
from aiohttp import ClientSession
from api import api
from paho.mqtt import client as mqtt
from paho.mqtt import enums
from urllib.parse import urlparse

_LOGGER: logging.Logger = logging.getLogger(__name__)
_LOGGER.addHandler(logging.StreamHandler(sys.stdout))
CONSOLE: logging.Logger = logging.getLogger("console")
CONSOLE.addHandler(logging.StreamHandler(sys.stdout))
CONSOLE.setLevel(logging.INFO)

S2M_USER = os.getenv( "S2M_USER" )
S2M_PASSWORD = os.getenv( "S2M_PASSWORD" )
S2M_COUNTRY = os.getenv( "S2M_COUNTRY" )
S2M_MQTT_URI = os.getenv( "S2M_MQTT_URI" )
S2M_MQTT_USERNAME = os.getenv( "S2M_MQTT_USERNAME" )
S2M_MQTT_PASSWORD = os.getenv( "S2M_MQTT_PASSWORD" )
S2M_MQTT_TOPIC = os.getenv( "S2M_MQTT_TOPIC" )
S2M_POLL_INTERVAL = int(os.getenv("S2M_POLL_INTERVAL"))
MQTT_HOST = urlparse(S2M_MQTT_URI).hostname
MQTT_PORT = urlparse(S2M_MQTT_URI).port or 1883
CLIENT_ID = f'python-mqtt-{random.randint(0, 1000)}'
FIRST_RECONNECT_DELAY = 1
RECONNECT_RATE = 2
MAX_RECONNECT_COUNT = 12
MAX_RECONNECT_DELAY = 60

def print_env():
    print(f"S2M_USER: {S2M_USER}")
    print(f"S2M_PASSWORD: {S2M_PASSWORD}")
    print(f"S2M_COUNTRY: {S2M_COUNTRY}")
    print(f"S2M_MQTT_URI: {S2M_MQTT_URI}")
    print(f"S2M_MQTT_USERNAME: {S2M_MQTT_USERNAME}")
    print(f"S2M_MQTT_PASSWORD: {S2M_MQTT_PASSWORD}")
    print(f"S2M_MQTT_TOPIC: {S2M_MQTT_TOPIC}")
    print(f"S2M_POLL_INTERVAL: {S2M_POLL_INTERVAL}")
    print(f"MQTT_HOST: {MQTT_HOST}")
    print(f"MQTT_PORT: {MQTT_PORT}")
    print(f"CLIENT_ID: {CLIENT_ID}")
    print(f"FIRST_RECONNECT_DELAY: {FIRST_RECONNECT_DELAY}")
    print(f"RECONNECT_RATE: {RECONNECT_RATE}")
    print(f"MAX_RECONNECT_COUNT: {MAX_RECONNECT_COUNT}")
    print(f"MAX_RECONNECT_DELAY: {MAX_RECONNECT_DELAY}")

def connect_mqtt():
    client = mqtt.Client(enums.CallbackAPIVersion.VERSION2)
    client.username_pw_set(S2M_MQTT_USERNAME, S2M_MQTT_PASSWORD)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.connect(MQTT_HOST, MQTT_PORT)
    return client

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("Connected to MQTT Broker!")
    else:
        print("Failed to connect, return code %d\n", reason_code)

def on_disconnect(client, userdata, flags, reason_code, properties):
    logging.info("Disconnected with result code: %s", reason_code)
    reconnect_count, reconnect_delay = 0, FIRST_RECONNECT_DELAY
    while reconnect_count < MAX_RECONNECT_COUNT:
        logging.info("Reconnecting in %d seconds...", reconnect_delay)
        time.sleep(reconnect_delay)
        try:
            client.reconnect()
            logging.info("Reconnected successfully!")
            return
        except Exception as err:
            logging.error("%s. Reconnect failed. Retrying...", err)
        reconnect_delay *= RECONNECT_RATE
        reconnect_delay = min(reconnect_delay, MAX_RECONNECT_DELAY)
        reconnect_count += 1
    logging.info("Reconnect failed after %s attempts. Exiting...", reconnect_count)

def announce_sensor( client: mqtt.Client, topic: str, name: str, unique_id: str, state_topic: str, value_template: str, device_class = None, state_class = None, unit_of_measurement = None, json_attributes_topic = None ):
    msg = {
        "name": name,
        "state_topic": state_topic,
        "value_template": value_template,
        "state_class": state_class,
        "unique_id": unique_id
    }
    if device_class != None: msg["device_class"] = device_class
    if unit_of_measurement != None: msg["unit_of_measurement"] = unit_of_measurement
    if json_attributes_topic != None: msg["json_attributes_topic"] = json_attributes_topic
    CONSOLE.info(f"Announcing sensor: {msg}")
    CONSOLE.info("")
    return msg
    #client.publish( topic, json.dumps( msg ) )

def announce_sensors(client, device_list):
    client.loop_start()
    for device in device_list.get("solarbank_list"):
        part_num = device["device_pn"]
        device_name = device["device_name"]
        announce_sensors_for_site(client, part_num, device_name)
    client.loop_stop()

def announce_sensors_for_site(client: mqtt.Client, part_num: str, device_name: str):
    py_name = device_name.lower().replace(" ", "_")
    sensor_list = []
    sensor_list.append( announce_sensor(
        client,
        f"homeassistant/sensor/{part_num}/battery_level/config",
        f"{device_name} Battery Level",
        f"{py_name}_battery_level",
        f"{S2M_MQTT_TOPIC}/{part_num}/device_param",
        "{{ ( value_json.battery_power | float ) * 100 }}",
        "battery",
        "%"
    ))

    # Publish photovoltaic power sensor
    sensor_list.append( announce_sensor(
        client,
        f"homeassistant/sensor/{part_num}/photovoltaic_power/config",
        f"{device_name} Photovoltaic Power",
        f"{py_name}_photovoltaic_power",
        f"{S2M_MQTT_TOPIC}/{part_num}/device_param",
        "{{ value_json.photovoltaic_power | float }}",
        "power",
        "measurement",
        "W"
    ))

    # Publish output power sensor
    sensor_list.append( announce_sensor(
        client,
        f"homeassistant/sensor/{part_num}/output_power/config",
        f"{device_name} Output Power",
        f"{py_name}_output_power",
        f"{S2M_MQTT_TOPIC}/{part_num}/device_param",
        "{{ value_json.output_power | float }}",
        "power",
        "measurement",
        "W"
    ))

    # Publish charging power sensor
    sensor_list.append( announce_sensor(
        client,
        f"homeassistant/sensor/{part_num}/charging_power/config",
        f"{device_name} Charging Power",
        f"{py_name}_charging_power",
        f"{S2M_MQTT_TOPIC}/{part_num}/device_param",
        "{{ value_json.charging_power | float }}",
        "power",
        "W"
    ))

    # Publish charging status
    sensor_list.append( announce_sensor(
        client,
        f"homeassistant/sensor/{part_num}/charging_status/config",
        f"{device_name} Charging Status",
        f"{py_name}_charging_status",
        f"{S2M_MQTT_TOPIC}/{part_num}/device_param",
        "{{ value_json.charging_status }}"
    ))

def get_site_id(site_list, site_name):
    for site in site_list:
        if site["site_name"] == site_name:
            return site["site_id"]
    return None

async def fetch_and_publish_sites(solix: api.AnkerSolixApi, client: mqtt.Client, device_list):
    client.loop_start()
    for device in device_list.get("solarbank_list"):
        part_num = device["device_pn"]
        device_name = device["device_name"]

        dev_payload = {
            "dev": {
                "ids": device["device_sn"],
                "name": device_name,
                "mf": "Anker Solix",
                "mdl": part_num,
                "sw": device["main_version"],
                "sn": device["device_sn"],
                "hw": device["wireless_type"]
            },
            "o": {
                "name": "solix2mqtt",
                "sw": "1.0",
                "url": "https://github.com/ShadowKitty42/homeassistant-addons"
            },
            "cmps": { },
            "state_topic": f"{part_num}/state"
        }
        dev_payload["cmp"] = announce_sensors_for_site(client, part_num, device_name)
        
        device_param_json = json.dumps( dev_payload )
        CONSOLE.info(f"Device Param: {device_param_json}")
        client.publish(f"{S2M_MQTT_TOPIC}/device/{part_num}/config", device_param_json)

    client.loop_stop()

async def main() -> None:
    try:
        async with ClientSession() as websession:
            print("Connecting to Anker")
            solix = api.AnkerSolixApi(
                S2M_USER, S2M_PASSWORD, S2M_COUNTRY, websession, _LOGGER
            )
            print("Connecting to MQTT")
            client = connect_mqtt()
            print("Fetching devices")
            device_list = await solix.get_user_devices();
            #announce_sensors(client, device_list)
            while True:
                await fetch_and_publish_sites(solix, client, device_list)
                time.sleep(S2M_POLL_INTERVAL)

    except Exception as exception:
        CONSOLE.info(f"{type(exception)}: {exception}")

# run async main
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as err:
        CONSOLE.info(f"{type(err)}: {err}")
