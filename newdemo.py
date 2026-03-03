import os
import time
import statistics
import Jetson.GPIO as GPIO
import paho.mqtt.client as mqtt

MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
TOPIC = os.getenv("MQTT_TOPIC", "smartspace/distance_cm")

TRIG_BCM = int(os.getenv("TRIG_BCM", "23"))
ECHO_BCM = int(os.getenv("ECHO_BCM", "24"))

PUBLISH_HZ = float(os.getenv("PUBLISH_HZ", "10"))
SAMPLES = int(os.getenv("SAMPLES", "5"))
MAX_CM = float(os.getenv("MAX_CM", "400"))
TIMEOUT_S = float(os.getenv("TIMEOUT_S", "0.03"))

def measure_cm():
    GPIO.output(TRIG_BCM, GPIO.LOW)
    time.sleep(0.0002)

    GPIO.output(TRIG_BCM, GPIO.HIGH)
    time.sleep(0.00001)
    GPIO.output(TRIG_BCM, GPIO.LOW)

    start_wait = time.time()
    while GPIO.input(ECHO_BCM) == 0:
        if time.time() - start_wait > TIMEOUT_S:
            return None
    pulse_start = time.time()

    while GPIO.input(ECHO_BCM) == 1:
        if time.time() - pulse_start > TIMEOUT_S:
            return None
    pulse_end = time.time()

    pulse_duration = pulse_end - pulse_start
    cm = (pulse_duration * 34300.0) / 2.0
    if cm < 0:
        return None
    return min(cm, MAX_CM)

def main():
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(TRIG_BCM, GPIO.OUT, initial=GPIO.LOW)
    GPIO.setup(ECHO_BCM, GPIO.IN)

    client = mqtt.Client(client_id="jetson-distance-pub")
    client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    client.loop_start()

    period = 1.0 / max(PUBLISH_HZ, 1e-6)

    try:
        while True:
            readings = []
            for _ in range(SAMPLES):
                cm = measure_cm()
                if cm is not None:
                    readings.append(cm)
                time.sleep(0.01)

            if readings:
                cm_med = statistics.median(readings)
                payload = f"{cm_med:.1f}"
                client.publish(TOPIC, payload, qos=0, retain=False)
                print(f"Published {payload} cm")
            else:
                print("No valid reading (timeout).")

            time.sleep(period)
    except KeyboardInterrupt:
        pass
    finally:
        client.loop_stop()
        client.disconnect()
        GPIO.cleanup()

if __name__ == "__main__":
    main()
