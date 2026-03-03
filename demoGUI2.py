import os
import time
import statistics
import threading
import tkinter as tk
from tkinter import ttk

import Jetson.GPIO as GPIO
import paho.mqtt.client as mqtt

# ---------------- MQTT CONFIG ----------------
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
DIST_TOPIC = os.getenv("MQTT_DIST_TOPIC", "smartspace/distance_cm")
CMD_TOPIC = os.getenv("MQTT_CMD_TOPIC", "smartspace/cmd")

# ---------------- GPIO CONFIG ----------------
TRIG_BCM = int(os.getenv("TRIG_BCM", "23"))  # physical pin 16
ECHO_BCM = int(os.getenv("ECHO_BCM", "24"))  # physical pin 18 (via divider)

# -------------- SENSOR SETTINGS --------------
PUBLISH_HZ = float(os.getenv("PUBLISH_HZ", "10"))  # measurements per sec
SAMPLES = int(os.getenv("SAMPLES", "5"))          # median filter
MAX_CM = float(os.getenv("MAX_CM", "400"))
TIMEOUT_S = float(os.getenv("TIMEOUT_S", "0.03"))  # 30ms timeout

# -------------- AUTOMATION DEFAULTS ----------
near_th = int(os.getenv("NEAR_TH", "30"))
mid_th = int(os.getenv("MID_TH", "80"))

# Shared data (sensor -> GUI)
latest_cm = None
latest_zone = "NO_SIGNAL"
data_lock = threading.Lock()

def measure_cm():
    """Measure distance from HC-SR04. Returns float cm or None on timeout."""
    GPIO.output(TRIG_BCM, GPIO.LOW)
    time.sleep(0.0002)

    # 10us pulse
    GPIO.output(TRIG_BCM, GPIO.HIGH)
    time.sleep(0.00001)
    GPIO.output(TRIG_BCM, GPIO.LOW)

    # wait for ECHO high
    start_wait = time.time()
    while GPIO.input(ECHO_BCM) == 0:
        if time.time() - start_wait > TIMEOUT_S:
            return None
    pulse_start = time.time()

    # wait for ECHO low
    while GPIO.input(ECHO_BCM) == 1:
        if time.time() - pulse_start > TIMEOUT_S:
            return None
    pulse_end = time.time()

    pulse_duration = pulse_end - pulse_start
    cm = (pulse_duration * 34300.0) / 2.0
    if cm < 0:
        return None
    return min(cm, MAX_CM)

def get_zone(cm, near_val, mid_val):
    if cm is None:
        return "NO_SIGNAL"
    if cm < near_val:
        return "NEAR"
    if cm < mid_val:
        return "MID"
    return "FAR"

def main():
    global near_th, mid_th, latest_cm, latest_zone

    # ---- GPIO init ----
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(TRIG_BCM, GPIO.OUT, initial=GPIO.LOW)
    GPIO.setup(ECHO_BCM, GPIO.IN)

    # ---- MQTT init ----
    client = mqtt.Client(client_id="jetson-smartspace-gui-pub")
    client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    client.loop_start()

    def publish_cmd(payload: str):
        client.publish(CMD_TOPIC, payload, qos=0, retain=False)
        print(f"[CMD] {payload}")

    # ---- Tkinter GUI ----
    root = tk.Tk()
    root.title("Smart Space – Jetson Nano (HC-SR04 + MQTT + Tkinter)")
    root.geometry("520x420")
    root.configure(bg="#222222")

    style = ttk.Style()
    style.theme_use("default")
    style.configure("TLabel", background="#222222", foreground="white")
    style.configure("TButton", padding=6)

    title = ttk.Label(root, text="Smart Space Dashboard", font=("Arial", 18, "bold"))
    title.pack(pady=10)

    dist_var = tk.StringVar(value="Distance: --.- cm")
    zone_var = tk.StringVar(value="Zone: NO_SIGNAL")
    mqtt_var = tk.StringVar(value=f"MQTT: {MQTT_BROKER}:{MQTT_PORT}")

    dist_label = ttk.Label(root, textvariable=dist_var, font=("Arial", 16))
    dist_label.pack(pady=10)

    zone_label = ttk.Label(root, textvariable=zone_var, font=("Arial", 14))
    zone_label.pack(pady=5)

    ttk.Label(root, textvariable=mqtt_var, font=("Arial", 10)).pack(pady=2)

    # Threshold controls
    thresh_frame = tk.Frame(root, bg="#222222")
    thresh_frame.pack(pady=10)

    near_var = tk.IntVar(value=near_th)
    mid_var = tk.IntVar(value=mid_th)

    def enforce_thresholds(*_):
        # keep near < mid
        n = near_var.get()
        m = mid_var.get()
        if n >= m:
            mid_var.set(n + 5)

    near_var.trace_add("write", enforce_thresholds)
    mid_var.trace_add("write", enforce_thresholds)

    ttk.Label(thresh_frame, text="NEAR threshold (cm):").grid(row=0, column=0, sticky="w", padx=5, pady=5)
    near_spin = ttk.Spinbox(thresh_frame, from_=5, to=200, increment=5, textvariable=near_var, width=8)
    near_spin.grid(row=0, column=1, padx=5)

    ttk.Label(thresh_frame, text="MID threshold (cm):").grid(row=1, column=0, sticky="w", padx=5, pady=5)
    mid_spin = ttk.Spinbox(thresh_frame, from_=10, to=400, increment=5, textvariable=mid_var, width=8)
    mid_spin.grid(row=1, column=1, padx=5)

    # Automation mode
    auto_mode = tk.BooleanVar(value=True)
    ttk.Checkbutton(root, text="AUTO mode (send LIGHT/FAN based on zone)", variable=auto_mode).pack(pady=10)

    # Manual buttons
    btn_frame = tk.Frame(root, bg="#222222")
    btn_frame.pack(pady=5)

    ttk.Button(btn_frame, text="LIGHT ON", command=lambda: publish_cmd("LIGHT:ON")).grid(row=0, column=0, padx=6, pady=6)
    ttk.Button(btn_frame, text="LIGHT OFF", command=lambda: publish_cmd("LIGHT:OFF")).grid(row=0, column=1, padx=6, pady=6)
    ttk.Button(btn_frame, text="FAN ON", command=lambda: publish_cmd("FAN:ON")).grid(row=1, column=0, padx=6, pady=6)
    ttk.Button(btn_frame, text="FAN OFF", command=lambda: publish_cmd("FAN:OFF")).grid(row=1, column=1, padx=6, pady=6)

    # Status footer
    footer_var = tk.StringVar(value=f"DIST TOPIC: {DIST_TOPIC} | CMD TOPIC: {CMD_TOPIC}")
    ttk.Label(root, textvariable=footer_var, font=("Arial", 9)).pack(pady=12)

    # AUTO anti-spam state
    last_sent = {"light": None, "fan": None}
    last_auto_time = 0.0
    AUTO_COOLDOWN_S = 1.0

    # ---- Background worker: sensor read + mqtt publish ----
    stop_event = threading.Event()

    def worker():
        nonlocal last_auto_time
        period = 1.0 / max(PUBLISH_HZ, 1e-6)

        while not stop_event.is_set():
            # take multiple samples and median filter
            readings = []
            for _ in range(SAMPLES):
                cm = measure_cm()
                if cm is not None:
                    readings.append(cm)
                time.sleep(0.01)

            cm_med = None
            if readings:
                cm_med = statistics.median(readings)

            # publish distance
            if cm_med is not None:
                payload = f"{cm_med:.1f}"
                client.publish(DIST_TOPIC, payload, qos=0, retain=False)
                print(f"[DIST] {payload} cm")
            else:
                print("[DIST] No valid reading (timeout).")

            # update shared state for GUI
            z = get_zone(cm_med, near_var.get(), mid_var.get())
            with data_lock:
                latest_cm = cm_med
                latest_zone = z

            # AUTO rules (optional)
            now = time.time()
            if auto_mode.get() and z != "NO_SIGNAL" and (now - last_auto_time) > AUTO_COOLDOWN_S:
                if z == "NEAR":
                    desired = {"light": "ON", "fan": "ON"}
                elif z == "MID":
                    desired = {"light": "ON", "fan": "OFF"}
                else:
                    desired = {"light": "OFF", "fan": "OFF"}

                if desired["light"] != last_sent["light"]:
                    publish_cmd(f"LIGHT:{desired['light']}")
                    last_sent["light"] = desired["light"]
                    last_auto_time = now

                if desired["fan"] != last_sent["fan"]:
                    publish_cmd(f"FAN:{desired['fan']}")
                    last_sent["fan"] = desired["fan"]
                    last_auto_time = now

            time.sleep(period)

    t = threading.Thread(target=worker, daemon=True)
    t.start()

    # ---- GUI updater ----
    def refresh_ui():
        # read shared state
        with data_lock:
            cm = latest_cm
            z = latest_zone

        if cm is None:
            dist_var.set("Distance: --.- cm")
        else:
            dist_var.set(f"Distance: {cm:.1f} cm")
        zone_var.set(f"Zone: {z}")

        # change background color by zone
        if z == "NEAR":
            root.configure(bg="#7a0000")
        elif z == "MID":
            root.configure(bg="#7a5a00")
        elif z == "FAR":
            root.configure(bg="#005a00")
        else:
            root.configure(bg="#222222")

        # keep ttk labels background in sync
        style.configure("TLabel", background=root["bg"], foreground="white")

        root.after(150, refresh_ui)

    refresh_ui()

    def on_close():
        stop_event.set()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)

    try:
        root.mainloop()
    finally:
        # cleanup
        stop_event.set()
        client.loop_stop()
        client.disconnect()
        GPIO.cleanup()

if __name__ == "__main__":
    main()
