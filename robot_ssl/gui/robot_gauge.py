import tkinter as tk
import serial
import threading
import json
import math
import socket

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
TCP_PORT = 5001

# TEST
#CONAS = "TEST"  #TCP, #USB

heading = 0.0


# Serial Monitor
def serial_thread():

    global heading

    ser = serial.Serial(
        SERIAL_PORT,
        BAUDRATE,
        timeout=1
    )

    while True:

        try:
            line = ser.readline().decode().strip()

            if not line:
                continue

            data = json.loads(line)

            if "turnby" in data:

                heading += float(data["turnby"])

                heading %= 360

                print("Heading =", heading)

                root.after(0, draw_gauge)

        except Exception as e:
            print(e)


def socket_thread():

    global heading

    ser = socket.socket()
    ser.bind(("127.0.0.1", TCP_PORT))
    ser.listen(1)

    conn, addr = ser.accept()
    
    try:
        while True:

            try:
                line = conn.recv(1024)

                if not line:
                    continue

                data = json.loads(line)

                if "turnby" in data:

                    heading += float(data["turnby"])

                    heading %= 360

                    print("Heading =", heading)

                    root.after(0, draw_gauge)

            except Exception as e:
                print(e)
                if isinstance(e, KeyboardInterrupt):
                    raise
    except KeyboardInterrupt:
        pass
    finally:
        ser.close()


# --------------------------------------------------
# Gauge Drawing
# --------------------------------------------------

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

    x = cx + r * 0.8 * math.cos(angle)
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

root.mainloop()