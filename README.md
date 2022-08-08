# beast-feeder

Script file: beast-feeder.py

Connect to a TCP BEAST server and forward each message via UDP.

CLI usage: python3 beast-feeder.py [receiver host] [receiver port] [destination host] [destination port]

Defaults:
  
receiver host: `readsb` # Receiver host/ip depends on your setup

receiver port: `30005` # Receiver BEAST port streaming ALL Mode S Downlink Formats CRC checked

destination host: `10.9.2.1` # Privided by our technical support, if other

destination port: `11092` # Privided by our technical support, if other

VPN keys are required! For more information please visit www.skysquitter.com
