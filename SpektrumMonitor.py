#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import threading
import queue
import time
import datetime
import sys
import re               # for input mode

import numpy as np
import serial
import serial.tools.list_ports

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

import lib_audio as ali

# global timing values
gScanInterval_ms = None                 # interval of power integration for avg (multiple sweeps)
gSweepTime_ms = None                    # duration of one scan over all selected freq's

# Flags für Anzeige / Audio etc.
audio_enabled = False
debug_enabled = False

# input mode for cmd "x <val1> <val2>" via Matplotlib-Window
input_mode = False         # True, wenn wir gerade eine Zeile tippen
input_buffer = ""          # aktueller Eingabetext

# -------------------------------------------------------------
# Konfiguration
# -------------------------------------------------------------
APPNAME = " Spectrum Monitor GUI: "
APPDESCRIPTION = " displays serial json-data from 'Power Scanner 2G4'-device, connected via USB "
APPVERSION = " 0.9.3"
APPCMD = " CMDs: '!'/'.'/'1'/'2'/'5'/'0'=scan-period, 'x <freq1> <freq2>'=set freq.range, 'h'=reset MaxH, 'a'=toggle audio, 's'=trigger single scan, 'p'=toggle periodic, '?'=help, ..."

# Logging of raw JSON scan lines
LOG_FILE_PATH = "scan_json.log"
log_file = None
log_lock = threading.Lock()
log_enabled = False                         # so far cannot be enabled during runtime, only on start

last_scan      = None

# ggf. leer lassen und automatisch erkennen
SERIAL_PORT = "/dev/ttyACM0"
BAUDRATE    = 115200

# Fester dBm-Bereich für Spektrum & Wasserfall
DBM_MAX_PHY = 0
DBM_MIN_PHY = -110

DBM_MAX = -20
DBM_MIN = -110

DBM_MAX_WF = -40
DBM_MIN_WF = -90

# Wasserfall: Anzahl Zeilen (History)
WF_ROWS = 200

# Audio init
ali.DBM_MAX = DBM_MAX
ali.DBM_MIN = DBM_MIN

# -------------------------------------------------------------
# Reply json from file -Thread
# -------------------------------------------------------------
def replay_reader_thread():
    """Replay JSON scan lines from a file instead of reading from serial."""
    global running
    if INFILE_PATH is None:
        print("Replay mode requested but no infile path set.", file=sys.stderr)
        return
    try:
        with open(INFILE_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if not running:
                    break
                line_str = line.strip()
                if not line_str:
                    continue
                scan = parse_scan_json(line_str)
                if scan is not None:
                    scan_queue.put(scan)
                    # optional: respect interval from data
                    interval_ms = scan.get("interval_ms", 0)
                    if interval_ms > 0:
                        time.sleep(interval_ms / 1000.0)
                    else:
                        time.sleep(0.2)
    except Exception as e:
        print(f"Replay reader error: {e}", file=sys.stderr)



# -------------------------------------------------------------
# Serial-Reader-Thread
# -------------------------------------------------------------
scan_queue    = queue.Queue()
console_queue = queue.Queue(maxsize=300)
running = True

def serial_reader_thread():
    """Liest Zeilen von der seriellen Schnittstelle und parst JSON-Scans."""
    global running
    global log_enabled
    buf = b""

    while running:
        try:
            with ser_lock:
                data = ser.read(1024)
            if not data:
                time.sleep(0.01)
                continue

            buf += data
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line_str = line.decode("utf-8", errors="ignore").strip()
                if not line_str:
                    continue
            
                # Scan-JSON
                #my_print(timestamp(0), "Debug: serial_reader_thread: new linestr: %s" % (line_str[0:5]))
                scan = parse_scan_json(line_str)
                if scan is not None:
                    # enqueue parsed scan
                    scan_queue.put(scan)
                    # log raw JSON line
                    if log_enabled:
                        log_json_line(line_str)
                else:
                    # Normale Konsolenzeile
                    if console_queue.full():
                        console_queue.get_nowait()
                    console_queue.put(line_str)

        except Exception as e:
            print("Serial reader error:", e, file=sys.stderr)
            time.sleep(0.5)

# -------------------------------------------------------------
# JSON-Parser für Scanner-Zeilen
# Erwartetes Format (Beispiel):
# {"scan":2000,"h":["freq","avg","min","max","hold"],
#  "c":[[2400,-97,-100,-94,-91],[2401,-97,-102,-78,-78],...]}
# -------------------------------------------------------------
def parse_scan_json(line: str):
    global gScanInterval_ms, gSweepTime_ms
    
    line = line.strip()
    if not line:
        return None
    
    if "freq" not in line:
        return None

    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None

    # check for channel parameter present
    if "c" not in obj:
        return None

    #my_print(timestamp(0), "Debug: parse_scan_json: new data")

    gScanInterval_ms = int(obj["scanint_ms"])
    gSweepTime_ms = int(obj["sweep_ms"])

    channels = obj["c"]
    if not isinstance(channels, list) or len(channels) == 0:
        return None

    freqs = []
    avg   = []
    mn    = []
    mx    = []
    hold  = []

    for entry in channels:
        # Erwartet: [freq, avg, min, max, hold]
        if not isinstance(entry, list) or len(entry) < 5:
            continue
        try:
            f  = int(entry[0])
            a  = int(entry[1])
            mi = int(entry[2])
            ma = int(entry[3])
            h  = int(entry[4])
        except (ValueError, TypeError):
            continue

        freqs.append(f)
        avg.append(a)
        mn.append(mi)
        mx.append(ma)
        hold.append(h)

    if not freqs:
        return None

    #my_print(timestamp(0), "Debug: parse_scan_json: new data appended")
    return {
        "freqs": np.array(freqs, dtype=np.int32),
        "avg":   np.array(avg,   dtype=np.int16),
        "min":   np.array(mn,    dtype=np.int16),
        "max":   np.array(mx,    dtype=np.int16),
        "hold":  np.array(hold,  dtype=np.int16),
        "interval_ms": int(obj.get("scan", 0)),
    }

def log_json_line(line: str):
    """Append a single JSON line to the log file (if enabled)."""
    global log_file
    if log_file is None:
        return
    # ensure single-line
    if not line.endswith("\n"):
        line = line + "\n"
    with log_lock:
        try:
            log_file.write(line)
            log_file.flush()
        except Exception as e:
            # Logging errors should not kill the reader
            print(f"Log write error: {e}", file=sys.stderr)


# -------------------------------------------------------------
# Serielle Schnittstelle
# -------------------------------------------------------------
def auto_detect_port():
    """Wenn SERIAL_PORT = '', versuche automatisch einen nRF-Port zu finden."""
    if SERIAL_PORT:
        return SERIAL_PORT
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        raise RuntimeError("No serial ports found")
    # Nimm einfach den ersten – ggf. anpassen
    return ports[0].device

ser = None
ser_lock = threading.Lock()

def open_serial():
    """Öffnet die serielle Schnittstelle."""
    global ser
    port = auto_detect_port()
    print(f"Opening serial port {port} @ {BAUDRATE}...")
    ser = serial.Serial(port, BAUDRATE, timeout=0.1, rtscts=True, dsrdtr=False)

def send_command(ch: str):
    """Ein einzelnes Zeichen an den Scanner schicken."""
    global ser
    if ser is None or not ser.is_open:
        return
    with ser_lock:
        ser.write(ch.encode('ascii', errors='ignore'))
        ser.flush()


# -------------------------------------------------------------
# Matplotlib GUI
# -------------------------------------------------------------
plt.style.use("ggplot")
fig = plt.figure(figsize=(12, 7))
mpl.rcParams['keymap.yscale'].remove('l')                   # no toggle of logaritmic scale

# Hinweis-Texte in Fenster-Koordinaten (0..1)
fig.text(
    0.01, 0.05,                                             # x, y (Fenster-Koordinaten)
    APPNAME + ' ' + APPCMD,                                 # Text
    ha="left", va="top",
    fontsize=10, color="white",
    bbox=dict(facecolor="black", alpha=0.3, pad=3)
)
status_text = fig.text(0.99, 0.98, "Sweep duration: waiting", ha="right", va="top")

# Layout:
#  - obere Hälfte: Spektrum
#  - mittlere Hälfte: Wasserfall
#  - unterer Streifen: Console (ein-/ausblendbar)
gs = fig.add_gridspec(3, 1, height_ratios=[5, 5, 2])
gs.update(hspace=0.4)

ax_spec    = fig.add_subplot(gs[0])
ax_wf      = fig.add_subplot(gs[1])
ax_console = fig.add_subplot(gs[2])

console_visible = True

# Placeholder-Objekte
spec_scatter_hold = ax_spec.scatter([], [], s=30, c="blue", marker="^", label="HoldM")
spec_line_max,  = ax_spec.plot([], [], label="MAX")
spec_line_avg,  = ax_spec.plot([], [], label="AVG")
spec_line_min,  = ax_spec.plot([], [], label="MIN")

# spectrum part
ax_spec.set_ylabel("RSSI [dBm]")
ax_spec.set_xlabel("Frequency [MHz]")
ax_spec.set_ylim(DBM_MIN, DBM_MAX)
ax_spec.legend(loc="upper right")
ax_spec.grid(True)
ax_spec.grid(True, which="minor")
ax_spec.minorticks_on()

# waterfall part
wf_im = ax_wf.imshow(
    np.zeros((WF_ROWS, 10)),   # placeholder, wird später korrekt dimensioniert
    aspect="auto",
    origin="lower",
    extent=[0, 10, 0, WF_ROWS],
    vmin=DBM_MIN_WF,
    vmax=DBM_MAX_WF,
    cmap="viridis",
)
ax_wf.set_ylabel("Time (older → up)")
ax_wf.set_xlabel("Frequency [MHz]")
ax_wf.minorticks_on()
ax_wf.grid(True, color="white", alpha=0.5, linewidth=0.3)

# console part
console_text = ax_console.text(
    0.0, 1.0, "",
    va="top", ha="left",
    fontsize=8,
    family="monospace",
    transform=ax_console.transAxes,
)
ax_console.set_axis_off()

# Fenster-Titel
fig.canvas.manager.set_window_title(
    APPNAME + 'ver'+ APPVERSION + ': ' + APPDESCRIPTION
)

# -------------------------------------------------------------
# Debug-Konsole aktualisieren
# -------------------------------------------------------------
def update_console_ax():
    """
    Aktualisiert die Debug-Konsole (max. 5 Zeilen sichtbar).
    Nutzt die Einträge aus console_queue (FIFO).
    """
    if not console_visible:
        ax_console.set_axis_off()
        return

    ax_console.set_axis_on()
    ax_console.set_xticks([])
    ax_console.set_yticks([])

    # Letzte max. 5 Zeilen aus dem FIFO-Puffer anzeigen
    lines = list(console_queue.queue)
    visible_lines = lines[-5:]

    txt = "\n".join(visible_lines)
    console_text.set_text(txt)


# -------------------------------------------------
# Channel definitions for 2.4 GHz
# -------------------------------------------------
# WiFi 2.4 GHz, Kanäle 1–13, Center: 2412 + 5*(n-1) MHz
WIFI_CHANNELS = {ch: 2412 + 5 * (ch - 1) for ch in range(1, 14)}

# BLE Advertising-Kanäle (37, 38, 39)
BLE_CHANNELS = {
    37: 2402,
    38: 2426,
    39: 2480,
}

# ZigBee (IEEE 802.15.4) Kanäle 11–26, Center: 2405 + 5*(n-11) MHz
ZIGBEE_CHANNELS = {ch: 2405 + 5 * (ch - 11) for ch in range(11, 27)}

HOYMILES_CHANNELS = {"H2G4": 2403, "H2G4": 2423, "H2G4": 2440, "H2G4": 2461, "H2G4": 2475}

# 5G NR bands (subset visible in 2.4 GHz scan)
FIVEG_BANDS = [
    {"start": 2300.0, "width": 100.0, "label": "n40"},
    {"start": 2496.0, "width": 94.0,  "label": "n41"},
]



def draw_channel_markers(ax):
    """
    Zeichnet Kanalmarkierungen (WiFi, BLE, ZigBee) auf ax (Spektrum).
    Nutzt die aktuellen x-/y-Limits des Axes.
    """
    x_min, x_max = ax.get_xlim()
    y_min, y_max = ax.get_ylim()

    # etwas Platz über dem Plot für Textlabels
    text_y = y_max + 1.0

    # WiFi: dünne graue Linien + 'Wxx'
    for ch, f in WIFI_CHANNELS.items():
        if f < x_min or f > x_max:
            continue
        ax.axvline(f, color="lightgray", linestyle=":", linewidth=0.8)
        ax.text(
            f, text_y,
            f"W{ch:02d}",
            rotation=90,
            fontsize=8,
            ha="center",
            va="bottom",
            color="gray",
        )

    # BLE: orange Linien + 'B37' etc.
    for ch, f in BLE_CHANNELS.items():
        if f < x_min or f > x_max:
            continue
        ax.axvline(f, color="blue", linestyle="--", linewidth=1.0)
        ax.text(
            f, text_y,
            f"    B{ch}",
            rotation=90,
            fontsize=8,
            ha="center",
            va="bottom",
            color="blue",
        )

    # ZigBee: grüne Linien + 'Z11' etc.
    for ch, f in ZIGBEE_CHANNELS.items():
        if f < x_min or f > x_max:
            continue
        ax.axvline(f, color="green", linestyle=":", linewidth=1.2)
        ax.text(
            f, text_y,
            f"        Z{ch:02d}",
            rotation=90,
            fontsize=8,
            ha="center",
            va="bottom",
            color="green",
        )


def draw_5g_bands(ax, fmin, fmax):
    """
    Zeichnet n40/n41 als farbige Balken im Spektrum.
    - fmin, fmax: aktueller X-Bereich (z.B. freqs_global[0], freqs_global[-1])
    """
    ymin, ymax = ax.get_ylim()

    # Wir zeichnen im "Achsen-Transform", damit sich die Höhe relativ zur Achse verhält
    trans = ax.get_xaxis_transform()  # x in Daten, y in Achsen-Fraction (0..1)

    for b in FIVEG_BANDS:
        f0 = b["start"]
        f1 = b["start"] + b["width"]

        # Bereich auf aktuellen X-Bereich beschränken
        if f1 < fmin or f0 > fmax:
            continue

        xs = max(f0, fmin)
        xe = min(f1, fmax)

        # schmaler Balken unten im Plot (z.B. 0.00..0.07 der Achsenhöhe)
        ax.axvspan(
            xs, xe,
            ymin=0.00, ymax=0.08,
            transform=trans,
            alpha=0.5,
            color="tab:red",
            linewidth=0.1,
        )

        # Label in die Mitte des sichtbaren Teils
        xc = 0.5 * (xs + xe)
        ax.text(
            xc, 0.035,              # Mitte der kleinen Leiste
            b["label"],
            ha="center", va="center",
            fontsize=8,
            color="black",
            transform=trans,
        )




# -------------------------------------------------------------
# Input Key-Handler
# -------------------------------------------------------------
def on_key(event):
    global console_visible, audio_enabled
    global input_mode, input_buffer

    if event.key is None:
        return
    k = event.key
    # ----------------------------
    # Handle entries in input mode
    # ----------------------------
    if input_mode:
        # ENTER -> prüfen & senden
        if k in ("enter", "return"):
            handle_x_command_from_buffer()
            return

        # Backspace -> letztes Zeichen löschen
        if k == "backspace":
            if input_buffer:
                input_buffer = input_buffer[:-1]
            # aktuellen Eingabestatus in Konsole anzeigen
            if not console_queue.full():
                console_queue.put(f">> {input_buffer}_")
            return

        # ESC -> Eingabe abbrechen
        if k == "escape":
            input_mode = False
            input_buffer = ""
            if not console_queue.full():
                console_queue.put(">> x input canceled")
            return

        # Normale Zeichen (nur Ziffern, Leerzeichen, Minus)
        if len(k) == 1 and (k.isdigit() or k == " " or k == "-"):
            input_buffer += k
            if not console_queue.full():
                console_queue.put(f">> {input_buffer}_")
            return

        # alles andere ignorieren
        return

    # Handle commands and decide whether to go in input mode for x-parameter or do single char action
    # 'x' will start input-mode für "x <val1> <val2>"
    if k == 'x':
        input_mode = True
        input_buffer = "x "
        if not console_queue.full():
            console_queue.put(">> x input: x <int> <int>  (finish with ENTER, ESC cancels)")
        return

    # else single char commands for external scanner nice!nano_v2
    if k == 's':
        send_command('s')
        console_queue.put(">> s (single scan)")
    elif k == 'p':
        send_command('p')
        console_queue.put(f">> p (toggle periodic scan)")
    elif k == 'h':
        send_command('h')
        console_queue.put(">> h (reset max hold)")
    elif k == 'j':
        send_command('j')
        console_queue.put(">> j (toggle json)")
    elif k == 'n':
        send_command('n')
        console_queue.put(">> n (reset freq.range default)")
    elif k == 'l':
        send_command('l')
        console_queue.put(">> l (set freq.range to low)")
    elif k in ['!', '.', '1', '2', '5', '0']:
        send_command(k)
        console_queue.put(f">> sets scan interval {k}")
    elif k == '?':
        send_command('?')

    # local commands for gui
    elif k == 'a':
        audio_enabled = not audio_enabled
        console_queue.put(f">> a (audio={audio_enabled})")
    elif k == 'd':
        console_visible = not console_visible
        console_queue.put(f">> d (console_visible={console_visible})")

    else:
        # andere Keys ignorieren oder ggf. direkt senden
        pass
    
fig.canvas.mpl_connect("key_press_event", on_key)



# parsing of values in x-input mode (frequency setting)
def handle_x_command_from_buffer():
    """
    Prüft input_buffer auf Format: x <int> <int>
    und sendet den Befehl über die serielle Schnittstelle.
    """
    global input_buffer, input_mode

    s = input_buffer.strip()
    # pattern: x <zahl> <zahl>, z.B. "x 10 20" oder "x -5 100"
    m = re.fullmatch(r"x\s+(-?\d+)\s+(-?\d+)", s)
    if not m:
        # ungültig
        msg = f"!! invalid x command: '{s}' (use: x <int> <int>)"
        if not console_queue.full():
            console_queue.put(msg)
        # Eingabe abbrechen
        input_mode = False
        input_buffer = ""
        return

    v1, v2 = m.group(1), m.group(2)
    # send command via UART
    send_command(s+'\n')                            # sendet inklusive '\n'
    #my_print(timestamp(0), "Debug: x-cmd send")
    if not console_queue.full():
        console_queue.put(f">> send cmd:> {s}")

    # Reset
    input_mode = False
    input_buffer = ""


# -------------------------------------------------------------
# Wasserfall-Datenpuffer
# -------------------------------------------------------------
wf_data = None          # 2D: WF_ROWS x num_channels
wf_lock = threading.Lock()

def init_waterfall(num_channels: int):
    """Initialisiert den Wasserfall-Puffer mit num_channels Spalten."""
    global wf_data
    wf_data = np.full((WF_ROWS, num_channels), DBM_MIN_WF, dtype=np.float32)

def add_scan_to_waterfall(values: np.ndarray):
    """Schiebt eine neue Zeile in den Wasserfall (unterste Zeile = neueste)."""
    global wf_data
    if wf_data is None:
        return
    with wf_lock:
        wf_data[:-1, :] = wf_data[1:, :]
        wf_data[-1, :]  = values


# -------------------------------------------------------------
# Init-Funktion für FuncAnimation
# -------------------------------------------------------------
def init_animation():
    global freq0_last
    """Initialisiert Linien, Scatter und Wasserfall für die Animation."""
    spec_line_avg.set_data([], [])
    spec_line_min.set_data([], [])
    spec_line_max.set_data([], [])
    spec_scatter_hold.set_offsets(np.zeros((0, 2)))
    wf_im.set_data(np.zeros((WF_ROWS, 10)))
    freq0_last = None
    return spec_line_avg, spec_line_min, spec_line_max, spec_scatter_hold, wf_im, console_text


# -------------------------------------------------------------
# Update-Funktion für FuncAnimation
# -------------------------------------------------------------
def animate(frame):
    """Wird periodisch von FuncAnimation aufgerufen, um das GUI zu aktualisieren."""
    global last_scan, freq0_last, freq_range_last

    # Neuen Scan aus Queue ziehen (wenn vorhanden; letzter gewinnt)
    new_data = False
    try:
        while True:
            scan = scan_queue.get_nowait()
            last_scan = scan
            new_data = True
    except queue.Empty:
        scan = None

    if new_data:
        s = last_scan
        freqs = s["freqs"]
        avg   = s["avg"].astype(np.float32)
        mn    = s["min"].astype(np.float32)
        mx    = s["max"].astype(np.float32)
        hold  = s["hold"].astype(np.float32)

        # adapt x-range of diagrams
        if freqs.size > 0 and (freq0_last == None or freq_range_last != freqs.size or freq0_last != freqs[0]):
            # first scan → spectrum/waterfall init
            #freqs_global = freqs.copy()
            ax_spec.set_xlim(freqs[0], freqs[-1])
            init_waterfall(len(freqs))
            wf_im.set_extent([freqs[0], freqs[-1], 0, WF_ROWS])
            # save current values as last
            freq0_last = freqs[0]
            freq_range_last = freqs.size;
            status_text.set_text(f"Sweep duration: {gSweepTime_ms} ms")
            draw_channel_markers(ax_spec)
            draw_5g_bands(ax_spec, freqs[0], freqs[-1])

        # Spektrum aktualisieren (fester dBm-Bereich)
        ax_spec.set_ylim(DBM_MIN, DBM_MAX)
        spec_line_avg.set_data(freqs, avg)
        spec_line_min.set_data(freqs, mn)
        spec_line_max.set_data(freqs, mx)
        spec_scatter_hold.set_offsets(np.column_stack((freqs, hold)))

        # Wasserfall aktualisieren (mit MAX-Werten)
        if wf_data is not None:
            add_scan_to_waterfall(mx)
            with wf_lock:
                wf_im.set_data(wf_data)
            wf_im.set_clim(DBM_MIN_WF, DBM_MAX_WF)
        
        # Audio
        if audio_enabled and ali.HAVE_AUDIO:
            ali.play_audio(mx)


    # Console aktualisieren
    update_console_ax()
    return spec_line_avg, spec_line_min, spec_line_max, spec_scatter_hold, wf_im, console_text


def parse_stdin_cmdline():
    global REPLAY_MODE, INFILE_PATH, LOGFILE_PATH, log_enabled
    parser = argparse.ArgumentParser(description="nRF52840 Power Scanner JSON monitor")
    # todo parameter for serial-if and gui config
    parser.add_argument("--infile", help="Replay JSON log file instead of reading from serial port, e.g. '--infile json_in.log'")
    parser.add_argument("--logfile", help="Replay JSON log file instead of reading from serial port, e.g. '--logfile json_out.log'")
    args = parser.parse_args()
    
    REPLAY_MODE = False
    if args.infile:
        REPLAY_MODE = True
        INFILE_PATH = args.infile
    elif args.logfile:
        log_enabled = True
        LOGFILE_PATH = args.logfile


def timestamp(format):
    if(format==0):
        return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f: ')[:-5]
    elif format==1:
        return str(time.time()) + ": "
    elif format==2:
        #for file name extention
        return datetime.datetime.now().strftime("%Y-%m-%d_%H%M_")
    else:
        #for file name extention with seconds
       return datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S_")


def my_print(ts, out):
    #global lck
    #global log_sum
    print('\n%s %s' % (ts, out), end='', flush=True)
    #with lck: log_sum += out

# -------------------------------------------------------------
# Main
# -------------------------------------------------------------
def main():
    global running, log_enabled, LOGFILE_PATH, log_file
    global REPLAY_MODE, INFILE_PATH
    global gScanInterval_ms, gSweepTime_ms                  # from json stream
    
    # read and evalue stdin command-line parameter
    parse_stdin_cmdline()
    
    # Reader-Thread starten: Serial oder Replay
    if REPLAY_MODE:
        t = threading.Thread(target=replay_reader_thread, daemon=True)
        console_queue.put(f">> playback file: %s, no command action to device possible, only audio ON/OFF via character 'a', Exit with 'q'" % (INFILE_PATH))
    else:
        open_serial()
        send_command('JP.')                      # switch nrf to json und aktivate periodical output with scan interval 0.5sec
        t = threading.Thread(target=serial_reader_thread, daemon=True)
        # open JSON log file (append mode)
        if log_enabled:
            try:
                log_file = open(LOG_FILE_PATH, "a", encoding="utf-8")
            except Exception as e:
                print(f"Could not open log file {LOG_FILE_PATH}: {e}", file=sys.stderr)
                log_file = None
    t.start()

    ani = FuncAnimation(
        fig,
        animate,
        init_func=init_animation,
        interval=200,  # ms
        blit=False,
        cache_frame_data=False,                     # <-- WICHTIG: Frame-Caching abschalten
    )

    try:
        plt.show()
    finally:
        running = False
        time.sleep(0.1)
        if ser is not None and ser.is_open:
            ser.close()
        # close logfile
        if log_enabled and log_file is not None:
            try:
                log_file.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
