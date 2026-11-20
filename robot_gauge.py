import tkinter as tk
import serial
import threading
import json
import math
import socket
import time

# --------------------------------------------------
# Configuration
# --------------------------------------------------

# Set CONAS for selected mode - see below
# CONAS = #USB,  #TCP, #TEST

# For USB
#CONAS = "USB"  #TCP, #TEST
BAUDRATE = 115200
SERIAL_PORT = "COM3"  # Windows -- check devices to determine the port id
# SERIAL_PORT = "/dev/ttyUSB0"   # Linux

# For Docker or mutlpi proc use TCP
CONAS = "TCP"  #USB, #TEST
HOST_NAME = "127.0.0.1"
TCP_PORT = 5004

#from robot_ssl.config import AppConfig
#config = AppConfig()
#config.validate()

#HOST_NAME = config.robot_host
#TCP_PORT = config.robot_port

# TEST
#CONAS = "TEST"  #TCP, #USB

heading = 0.0


# Message Handling
def process_message(line: str | bytes, source: str) -> None:
    global heading

    try:
        data = json.loads(line)
        if isinstance(data, dict):
            if "turnby" in data:
                turnby = float(data["turnby"])
                
                if not math.isfinite(turnby):
                    raise ValueError("turnby must be finite")
                
                heading = (heading + turnby) % 360
                print("Heading =", heading)
                
                root.after(0, draw_gauge)
        else:
            print(f"Ignoring non-object {source} message")
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        print(f"Ignoring invalid {source} message: {exc}")
    
    return


# Serial Monitor
def serial_thread():
    is_connected: bool | None = None

    while True:
        try:
            with serial.Serial(SERIAL_PORT, BAUDRATE, timeout=1) as ser:
                if not is_connected:
                    print(f"Connected to serial port {SERIAL_PORT}")
                is_connected = True
                
                while True:
                    line = ser.readline()
                    if line:
                        process_message(line, "serial")
        except (serial.SerialException, OSError) as exc:
            if is_connected is None:
                print(f"Serial port {SERIAL_PORT} unavailable: {exc}")
            elif is_connected:
                print(f"Disconnected from serial port {SERIAL_PORT}: {exc}")
            is_connected = False
            
            time.sleep(1)
    
    return


def socket_thread():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST_NAME, TCP_PORT))
        server.listen()
        print(f"Listening for connections on {HOST_NAME}:{TCP_PORT}")

        while True:
            try:
                conn, addr = server.accept()
            except OSError as exc:
                print(f"Socket listener stopped: {exc}")
                return
            
            # NOTE: This design of connecting to the socket as a file is safer than processing x number of bytes at a time - 
            # it can, however, only process 1 sender at a time.  If you need the listener to process more than one at a time and are happy to risk sacrificing data integrity, see the commented out code below.
            print(f"Connected: {addr}")
            with conn:
                try:
                    with conn.makefile("r", encoding="utf-8") as conn_file:
                        for line in conn_file:
                            process_message(line, "socket")
                except OSError as exc:
                    print(f"Connection {addr} ended with an error: {exc}")
            print(f"Disconnected: {addr}; waiting for another client")
    
    ## Listener code without using file connection
    # try:
    #     while True:
    #         try:
    #             line = conn.recv(1024)

    #             if not line:
    #                 continue

    #             data = json.loads(line)

    #             if "turnby" in data:

    #                 heading = float(data["turnby"]) # temporary set to relative direction instead of absolute
    #                 heading %= 360
    #                 print("Heading =", heading)

    #                 root.after(0, draw_gauge)

    #         except Exception as e:
    #             print(e)
    #             if isinstance(e, KeyboardInterrupt):
    #                 raise
    # except KeyboardInterrupt:
    #     pass
    # finally:
    #     ser.close()
    
    return


# Gauge Drawing
def draw_gauge():
    canvas.delete("all")

    cx = 200
    cy = 200
    r = 150

    # compass circle
    canvas.create_oval(
        cx-r, cy-r,
        cx+r, cy+r,
        width=2
    )

    canvas.create_text(cx, cy-r-15, text="N")
    canvas.create_text(cx+r+15, cy, text="E")
    canvas.create_text(cx, cy+r+15, text="S")
    canvas.create_text(cx-r-15, cy, text="W")

    angle = math.radians(heading - 90)

    x = cx - r * 0.8 * math.cos(angle)
    y = cy + r * 0.8 * math.sin(angle)

    canvas.create_line(
        cx, cy,
        x, y,
        width=4,
        fill="red"
    )

    canvas.create_text(
        cx,
        cy+178,
        text=f"{heading:.1f}°"
    )

# Internal Gauge draw test
def test():
    global heading

    heading += 30
    heading %= 360

    draw_gauge()

    root.after(1000, test)


# Tkinter UI
root = tk.Tk()

root.title("Robot Direction Gauge")

canvas = tk.Canvas(
    root,
    width=400,
    height=400
)

canvas.pack()

draw_gauge()

root.update_idletasks()

if CONAS == "USB":
    threading.Thread(
        target=serial_thread,
        daemon=True
    ).start()
elif CONAS == "TCP":
    threading.Thread(
        target=socket_thread,
        daemon=True
    ).start()
else:
    # TEST
    root.after(1000, test)

try:
    root.mainloop()
except KeyboardInterrupt:
    print("Keyboard interrupt detected - program ending naturally.")
else:
    print("Program closed safely.")