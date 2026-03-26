import time
import threading
import serial

from pyModbusTCP.server import ModbusServer, DataBank

# ================== CONFIG ==================
SERIAL_PORT = "COM7"
SERIAL_BAUD = 115200
MODBUS_HOST = "127.0.0.1"
MODBUS_PORT = 15020
# ===========================================

ser = serial.Serial(SERIAL_PORT, SERIAL_BAUD, timeout=1)

# Create a real DataBank instance
db = DataBank(
    coils_size=100,
    h_regs_size=100,
    i_regs_size=100
)

# Pass that databank into the Modbus TCP server
server = ModbusServer(
    host=MODBUS_HOST,
    port=MODBUS_PORT,
    no_block=True,
    data_bank=db
)

last_coils = [False] * 8


def parse_line(line: str) -> dict:
    data = {}
    for part in line.split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            try:
                data[k.strip()] = int(v.strip())
            except ValueError:
                pass
    return data


def write_registers(vals):
    # Holding registers 0..12
    db.set_holding_registers(0, vals)

    # Mirror into input registers too if you want future FC4 support
    db.set_input_registers(0, vals)

    # Coil 0 mirrors alarm state
    db.set_coils(0, [bool(vals[3])])


def read_coil(index: int) -> bool:
    vals = db.get_coils(index, 1)
    if vals is None:
        return False
    return bool(vals[0])


def clear_coil(index: int):
    db.set_coils(index, [False])


def serial_reader():
    while True:
        try:
            line = ser.readline().decode(errors="ignore").strip()
            if not line:
                continue

            data = parse_line(line)

            vals = [
                data.get("PV", 0),     # 0
                data.get("DIFF", 0),   # 1
                data.get("STATE", 0),  # 2
                data.get("ALARM", 0),  # 3
                data.get("SRC", 0),    # 4
                data.get("P1", 0),     # 5
                data.get("P2", 0),     # 6
                data.get("VL1", 0),    # 7
                data.get("VL2", 0),    # 8
                data.get("VL3", 0),    # 9
                data.get("VR1", 0),    # 10
                data.get("VR2", 0),    # 11
                data.get("VR3", 0),    # 12
            ]

            write_registers(vals)
            print(f"Arduino -> Modbus: {line}")

        except Exception as e:
            print(f"[SERIAL_READER_ERROR] {e}")
            time.sleep(0.2)


def command_writer():
    global last_coils

    labels = {
        1: b"CMD=CONTRACT\n",
        2: b"CMD=EXPAND\n",
        3: b"CMD=STOP\n",
        4: b"CMD=VENT\n",
        5: b"CMD=BLOW\n",
        6: b"CMD=SUCK\n",
        7: b"CMD=CLOSE\n",
    }

    while True:
        try:
            for i in range(1, 8):
                current = read_coil(i)

                if current and not last_coils[i]:
                    ser.write(labels[i])
                    print(f"Modbus -> Arduino: {labels[i].decode().strip()}")
                    clear_coil(i)

                last_coils[i] = current

            time.sleep(0.1)

        except Exception as e:
            print(f"[COMMAND_WRITER_ERROR] {e}")
            time.sleep(0.2)


if __name__ == "__main__":
    print(f"Starting pyModbusTCP server on {MODBUS_HOST}:{MODBUS_PORT}")
    print("Make sure Arduino is plugged in and Serial Monitor is closed.")

    server.start()

    threading.Thread(target=serial_reader, daemon=True).start()
    threading.Thread(target=command_writer, daemon=True).start()

    print("Gateway running. Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping server...")
        server.stop()