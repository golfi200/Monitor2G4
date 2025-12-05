# Monitor2G4

see Wiki for description, It will be an arduino project with python GUI for json data.


## System setup with HW connected to serial port of PC/smartphone as display (GUI)
:<img width="500" height="300" alt="darstellung_PC_smartphone_mit_spektrum" src="https://github.com/user-attachments/assets/8ba628fc-8f85-424a-9504-83197e10c959" />

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

If it works GUI starts:

<img width="500" height="300" alt="Screenshot from 2025-12-04 09-04-00" src="https://github.com/user-attachments/assets/7aeb7155-b657-47ac-abd4-86fa3ebde1e2" />


## Alternatively the SuperMini embeded-SW offers its own ASCII-GUI 
Open the serial port in a serial terminal like 'cuteCom', 'gtkterm' or Arduino-'Serial Monitor'. The baudrate is not relevant since device uses USB serial profile cdc_acm.

<img width="500" height="300" alt="Screenshot from 2025-11-29 10-07-36" src="https://github.com/user-attachments/assets/664b77b2-e808-4de6-b348-fd5a3ffd18f4" />

## Commands to control the SuperMini






