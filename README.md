# beast-feeder

Script file: beast-feeder.py

Connect to a TCP BEAST server and forward each message via UDP.

CLI usage: python3 beast-feeder.py [receiver host] [receiver port] [destination host] [destination port] [set timestamp] [clock diff limit] [df_filter]

Defaults:
  
receiver host: `readsb` # Receiver host/ip depends on your setup

receiver port: `30005` # Receiver BEAST port streaming ALL Mode S Downlink Formats CRC checked

destination host: `10.9.2.1` # Privided by our technical support, if other

destination port: `11092` # Privided by our technical support, if other

set timestamp: `true` # Insert system clock based timestamp in messages

clock diff limit: `200` # [ms] If `set timestamp` enabled, this defines the validation limit of the system clock diff in reference to NTP

df_filter: `17,20,21` # List of Mode S downlink formats which are allowed to pass the filter

VPN keys are required! For more information please visit www.skysquitter.com
