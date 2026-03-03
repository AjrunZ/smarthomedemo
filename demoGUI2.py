import paho.mqtt.client as mqtt
import tkinter as tk

MQTT_BROKER = "localhost"
DIST_TOPIC = "smartspace/distance_cm"
CMD_TOPIC = "smartspace/cmd"

distance_value = "--"

# -------- MQTT --------
def on_message(client, userdata, msg):
    global distance_value
    distance_value = msg.payload.decode()
    update_ui()

client = mqtt.Client()
client.on_message = on_message
client.connect(MQTT_BROKER, 1883, 60)
client.subscribe(DIST_TOPIC)
client.loop_start()

# -------- GUI --------
root = tk.Tk()
root.title("Smart Space Automation")
root.geometry("500x350")

distance_label = tk.Label(root, text="Distance: -- cm", font=("Arial", 20))
distance_label.pack(pady=20)

zone_label = tk.Label(root, text="Zone: --", font=("Arial", 16))
zone_label.pack()

def update_ui():
    try:
        cm = float(distance_value)
        distance_label.config(text=f"Distance: {cm:.1f} cm")

        if cm < 30:
            zone = "NEAR"
            root.configure(bg="red")
        elif cm < 80:
            zone = "MID"
            root.configure(bg="orange")
        else:
            zone = "FAR"
            root.configure(bg="green")

        zone_label.config(text=f"Zone: {zone}")

    except:
        pass

def send_cmd(cmd):
    client.publish(CMD_TOPIC, cmd)

tk.Button(root, text="Light ON", width=15,
          command=lambda: send_cmd("LIGHT:ON")).pack(pady=5)

tk.Button(root, text="Light OFF", width=15,
          command=lambda: send_cmd("LIGHT:OFF")).pack(pady=5)

tk.Button(root, text="Fan ON", width=15,
          command=lambda: send_cmd("FAN:ON")).pack(pady=5)

tk.Button(root, text="Fan OFF", width=15,
          command=lambda: send_cmd("FAN:OFF")).pack(pady=5)

root.mainloop()
