import time
import math
import threading
from dataclasses import dataclass

import pygame
import paho.mqtt.client as mqtt

# ================= CONFIG =================
MQTT_HOST = "127.0.0.1"     # If broker runs on Jetson
MQTT_PORT = 1883

MQTT_TOPIC_DISTANCE = "smartspace/distance_cm"
MQTT_TOPIC_FLAME = "smartspace/flame"

FLAME_ACTIVE_LOW = True   # Change to False if flame logic reversed

WINDOW_W = 1000
WINDOW_H = 600
FULLSCREEN = False
# ==========================================


@dataclass
class SharedState:
    distance_cm: float = float("inf")
    flame_detected: bool = False
    last_distance_ts: float = 0.0


state = SharedState()


def classify_zone(cm: float) -> str:
    if cm < 60:
        return "VERY_NEAR"
    if cm < 120:
        return "NEAR"
    if cm < 200:
        return "PRESENCE"
    return "IDLE"


def on_connect(client, userdata, flags, rc):
    client.subscribe(MQTT_TOPIC_DISTANCE)
    client.subscribe(MQTT_TOPIC_FLAME)


def on_message(client, userdata, msg):
    topic = msg.topic
    payload = msg.payload.decode("utf-8").strip()

    if topic == MQTT_TOPIC_DISTANCE:
        try:
            state.distance_cm = float(payload)
            state.last_distance_ts = time.time()
        except:
            pass

    elif topic == MQTT_TOPIC_FLAME:
        try:
            raw = int(payload)
            state.flame_detected = (raw == 0) if FLAME_ACTIVE_LOW else (raw == 1)
        except:
            pass


def mqtt_thread():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.loop_forever()


def main():
    threading.Thread(target=mqtt_thread, daemon=True).start()

    pygame.init()
    flags = pygame.FULLSCREEN if FULLSCREEN else 0
    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H), flags)
    pygame.display.set_caption("Smart Space Display")

    clock = pygame.time.Clock()
    font = pygame.font.SysFont("Arial", 28)

    t0 = time.time()

    running = True
    while running:
        dt = clock.tick(60) / 1000.0
        t = time.time() - t0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        cm = state.distance_cm

        zone = classify_zone(cm) if (time.time() - state.last_distance_ts <= 3.0) else "IDLE"

        if state.flame_detected:
            zone = "ALERT"

        # Background animation
        breath = (math.sin(t * 0.8) + 1.0) * 0.5
        base = int(20 + 40 * breath)

        if zone == "IDLE":
            bg = (base, base + 10, base + 25)
        elif zone == "PRESENCE":
            bg = (base, base + 30, base + 30)
        elif zone == "NEAR":
            bg = (base + 35, base + 20, base)
        elif zone == "VERY_NEAR":
            bg = (base + 55, base, base + 25)
        else:
            flash = (math.sin(t * 8.0) + 1.0) * 0.5
            bg = (int(60 + 180 * flash), 0, 0)

        screen.fill(bg)

        cx, cy = WINDOW_W // 2, WINDOW_H // 2
        speed_map = {
            "IDLE": 0.8,
            "PRESENCE": 1.6,
            "NEAR": 2.8,
            "VERY_NEAR": 4.5,
            "ALERT": 7.0,
        }

        pulse = (math.sin(t * speed_map[zone]) + 1.0) * 0.5
        max_r = int(min(WINDOW_W, WINDOW_H) * 0.4)

        for i in range(4):
            r = int(pulse * max_r * (i + 1) / 4)
            pygame.draw.circle(screen, (255, 255, 255), (cx, cy), r, 2)

        hud = font.render(
            f"Distance: {cm:.1f} cm | Zone: {zone} | Flame: {'YES' if state.flame_detected else 'NO'}",
            True,
            (255, 255, 255),
        )
        screen.blit(hud, (20, 20))

        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()