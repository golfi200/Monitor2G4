# Monitor2G4
Grafical user interface (GUI) in python to show the spectrum data received via JSON stream from HW with embedded SW "Power Scanner 2.4 GHz".
The "Power Scanner 2.4GHz" can detect RSSI in two frequency ranges:
* low: 2360...2460 MHz
* normal: 2400...2500 MHz

Each range can be limited to a smaller frequency span to reduce the overall sweep interval. Frequency span limiting is only possible within the corresponding range (low or normal).
So it is possible to set 2370...2450MHz (low range), but not 2390...2480MHz because it is partly low and normal range. 

## System setup
SuperMini NRF52840 board with Embedded SW "Power Scanner 2.4 GHz" connected to serial port of PC/smartphone with "PowerMonitor.py" as display (GUI).
<p align="center"><img width="500" height="300" alt="darstellung_PC_smartphone_mit_spektrum" src="https://github.com/user-attachments/assets/8ba628fc-8f85-424a-9504-83197e10c959" />

## Howto start GUI from Linux/Windows Terminal

### install python3 and all imported libs
--> See internet howtos

### Set Serial port in 'FrequencyMonitor.py'
```
SERIAL_PORT = "/dev/ttyACM0"                                        # keep empty for auto-detection
```
  
### Open Terminal and enter command

```
1. option:
python FrequencyMonitor.py                               # GUI starts and awaits on defined serial port to get connected and receiving json-data

2. option: 
python FrequencyMonitor.py --infile scan_json.log        # if no HW connected, read json-stream from --infile

3. option:

python FrequencyMonitor.py --logfile out.log             # received json-date from serial port are written to --logfile
```

If it works, GUI starts:

<p align="center"><img width="500" height="300" alt="Screenshot from 2025-12-04 09-04-00" src="https://github.com/user-attachments/assets/7aeb7155-b657-47ac-abd4-86fa3ebde1e2" />

### Commands that are supported by the python GUI:
* 'a' : toggle audio output at PC (frequency spectrum mapped to audio in range 440 ... 4400KHz)
* 'q' : quit python GUI
* 'l'/'n' : set low or normal frequency range
* 'x <freq1> <freq2>' : sets the frequency span
* Commands for Scan interval timing see cmds of embedded SW "Power Scanner 2.4 GHz"
* '?' : help


### Commands to control the SuperMini embedded SW "Power Scanner 2.4 GHz":
Commands (via Serial):

Mode switch:
* 'J' : set JSON output mode (resets implicity MaxHold and switches to priodic scan)
* 'j' : toggles between JSON and default ASCII Spectrum mode (ASCII waterfall is disabled)
* 'w' : toggles between ASCII waterfall mode and ASCII Spectrum mode (JSON is disabled)

Scan interval timing:
* '!' : scan duration = 0.25 s
* '.' : scan duration = 0.5 s (default for JSON)
* '1' : scan duration = 1 s (startup default)
* '2' : scan duration = 2 s
* '5' : scan duration = 5 s
* '0' : scan duration = 10 s
* 'P' : sets periodic scan
* 'p' : toggles periodic scan on/off
* 's' : trigger one scan (used in non-periodic mode to trigger single scan)

Control:
* 'l' : set low frequency range (2360 ... 2460 MHz)
* 'n' : set normal frequency range (2400 ... 2500 MHz)
* 'x <freq1> <freq2>\n' : set sweep freqency span and selects range (<freq1> <freq2> in MHz must be subset of one freq.range)
* 'y <rssi1> <rssi2>\n' : set y-axis in dBm in ASCII modes (range possible -110...0dBm)
* 'h' : reset MaxHold

Help and info:
* 'i' : print freq. info about WLAN, BLEadv, Zigbee, Hoymiles, 3GPP 5G channels
* '?' : print version and command help

## Alternatively the SuperMini embeded-SW offers its own ASCII-GUI 
Open the serial port in a serial terminal like 'cuteCom', 'gtkterm' or Arduino-'Serial Monitor'. The baudrate is not relevant since device uses USB serial profile cdc_acm.

<p align="center"><img width="500" height="300" alt="Screenshot from 2025-11-29 10-07-36" src="https://github.com/user-attachments/assets/664b77b2-e808-4de6-b348-fd5a3ffd18f4" />








