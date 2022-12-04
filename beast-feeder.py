#!/usr/bin/env python3
# pylint: disable=C0103,C0114,C0112,C0116,W1514,W0702

""" beast-feeder.py <recv_host> <recv_port> <dest_host> <dest_port> <gps_avail> """

# LIBS ---------
import signal
import socket
import sys
import functools
import datetime
# --------------

# TITLE ---------------------------
BUILD_MAJOR = '11'
BUILD_DATE = '221204' # this is the fall-back date for versioning
BUILD_MINOR = '02'
TITLE = 'SKYSQUITTER BEAST-FEEDER'
VERSION_FILENAME = '/.VERSION.beast-feeder'
# ---------------------------------

# DEFAULTS -------------------
RECV_HOST = 'readsb'
RECV_PORT = 30005
DEST_HOST = '10.9.2.1'
DEST_PORT = 11092
GPS_AVAIL = False
# ----------------------------

# CONSTANTS ------------------
# Beast
ESCAPE_BYTE = 0x1a
MSG_TYPE_1 = 0x31
MSG_TYPE_2 = 0x32
MSG_TYPE_3 = 0x33
MSG_TYPE_4 = 0x34
TIMESTAMP_LEN = 6
TIMESTAMP_INDEX = 2
# Buffer
MSG_BUFFER_SIZE = 64
TIMESTAMP_BUFFER_SIZE = 16
# ----------------------------

# VARIABLES ---------------------
buffer = bytearray(MSG_BUFFER_SIZE)
buffer_index = 0
# Set defaults
recv_host = RECV_HOST
recv_port = RECV_PORT
dest_host = DEST_HOST
dest_port = DEST_PORT
gps_avail = GPS_AVAIL
# -------------------------------

# ensure print always flushes the buffer:
print = functools.partial(print, flush=True)    # pylint: disable=W0622
# ----------------------------

# Make Build String:
try:
    with open(VERSION_FILENAME, 'r') as f:
        EXT_BUILD_DATE = f.read()
except:
    BUILD = BUILD_MAJOR + '.' + BUILD_DATE + '.' + BUILD_MINOR
else:
    BUILD = BUILD_MAJOR + '.' + EXT_BUILD_DATE.strip() + '.' + BUILD_MINOR

# FUNCTIONS DEFS ---------------------------------------------------
def shutdown_gracefully():
    """ Shutting down gracefully by closing the network sockets prior exit """
    print('Shutdown gracefully!')
    disconnect_from_receiver()
    close_socket_to_receiver()
    close_socket_to_destination()
    sys.exit()

def sigint_handler():
    """ Handle received SIGINT """
    print('SIGINT received')
    shutdown_gracefully()

def sigterm_handler():
    """ Handle received SIGTERM """
    print('SIGTERM received')
    shutdown_gracefully()

def preamble_detected():
    """ Return True if message preamble detected """
    ## global buffer_index
    index = buffer_index - 1
    # Check message type
    try:
        if buffer[index] != MSG_TYPE_1 and buffer[index] != MSG_TYPE_2 and \
                        buffer[index] != MSG_TYPE_3 and \
                        buffer[index] != MSG_TYPE_4:
            return False
    except IndexError:
        # This error is almost always caused by losing the connection to the RECV_HOST.
        print("Beast-feeder is exiting - did we lose the connection to " \
                        + recv_host + ":" + str(recv_port) + "?")
        sys.exit()
    # Count amount of Escape bytes (has to be odd)
    index -= 1
    esc_count = 0
    while index >= 0 and buffer[index] == ESCAPE_BYTE:
        esc_count += 1
        index -= 1
    if index == 0 and buffer[index] == ESCAPE_BYTE:
        return False
    if esc_count % 2 == 0:
        return False
    return True

def msg_is_valid(message):
    """ Return True if message is to be sent; check message preamble and type;
       ESC byte at beginning required """
    if message[0] != ESCAPE_BYTE:
        return False
    # Either message tyoe 2 or 3 required
    if message[1] != MSG_TYPE_2 and message[1] != MSG_TYPE_3:
        return False
    # Message preamble and type is valid -> send to destination
    return True

def connect_to_receiver():
    """ Connect to the Receiver server via TCP"""
    print('Connect to Receiver')
    try:
        server_address = (recv_host, recv_port)
        sock_recv.connect(server_address)
    except:
        # This error is almost always caused by losing the connection to the RECV_HOST.
        print("Beast-feeder's domain name cannot be resolved - is the machine or container named " \
                    + recv_host + ":" + str(recv_port) + " running?")
        sys.exit()

def disconnect_from_receiver():
    """ Disconnect from the Receiver server """
    print('Disconnect from Receiver')
    try:
        sock_recv.shutdown(socket.SHUT_RDWR)
    except:
    	# Execption disconnecting TCP socket
        print('Exception while disconnecting from Receiver')

def close_socket_to_receiver():
    """ Close socket to the Receiver server """
    print('Close socket to Receiver')
    try:
        sock_recv.close()
    except:
    	# Execption closing TCP socket
        print('Exception while closing socket to Receiver')

def close_socket_to_destination():
    """ Close socket to the Destination server """
    print('Close socket to Destination')
    try:
        sock_dest.close()
    except:
    	# Execption closing UDP socket
        print('Exception while closing socket to Destination')

def send_to_destination(message):
    """ Send message to Destination via UDP """
    server_address = (dest_host, dest_port)
    sock_dest.sendto(message, server_address)

def process_recv_bytes(recv_bytes):
    """ Process received byte """
    global buffer_index         # pylint: disable=W0603
    # Avoid buffer overflow
    if buffer_index == MSG_BUFFER_SIZE:
        buffer_index = 0
    # Add received data chunk to buffer
    buffer[buffer_index:buffer_index + 1] = recv_bytes
    buffer_index += 1
    if buffer_index < 3:
        return
    # Look for Beast preamble
    if preamble_detected():
        # Prepare received message
        message = bytearray(buffer_index - 2)
        message = buffer[0:buffer_index - 2]
        # Send message
        if msg_is_valid(message):
            if gps_avail == False:
                message = get_new_timestamped_message(message)
            send_to_destination(message)
        # Reset buffer
        buffer[0] = buffer[buffer_index - 2]
        buffer[1] = buffer[buffer_index - 1]
        buffer_index = 2

def get_new_timestamped_message(message):
    """ Insert the system time as timestamp and return the mew message """
    timestamp_buffer = get_timestamp_buffer()
     # Find timestamp begin and end index
    index = TIMESTAMP_INDEX
    counter = 0
    while counter < TIMESTAMP_LEN:
        if message[index] == ESCAPE_BYTE:
            index += 1
        index +=1
        counter += 1
    signalIndex = index
    # Create new message
    new_message_len = 2 + len(timestamp_buffer) + len(message[signalIndex:])
    new_message = bytearray(new_message_len)
    # Preamble
    new_message.extend(message[0:2])
    # New timestamp
    new_message.extend(timestamp_buffer)
    # Remaining orginal message
    new_message.extend(message[signalIndex:])
    return new_message
        
def get_timestamp_buffer():
    """ Build and return an actual timestamp buffer """
   # Get actual time values
    now = datetime.datetime.now()
    midnight = datetime.datetime.combine(now.date(), datetime.time())
    secs_of_day = (now - midnight).seconds
    nanos_of_sec = now.microsecond * 1000
    # Build timestamp
    byte_counter = 0
    timestamp_buffer = bytearray(TIMESTAMP_BUFFER_SIZE)
    # Secs
    timestamp_buffer.append(secs_of_day >> 10)
    byte_counter += 1
    if timestamp_buffer[len(timestamp_buffer) - 1] == ESCAPE_BYTE:
        timestamp_buffer.append(ESCAPE_BYTE)
        byte_counter += 1
    secs_of_day = secs_of_day - (timestamp_buffer[len(timestamp_buffer) - 1] << 10)
    timestamp_buffer.append(secs_of_day >> 2)
    byte_counter += 1
    if timestamp_buffer[len(timestamp_buffer) - 1] == ESCAPE_BYTE:
        timestamp_buffer.append(ESCAPE_BYTE)
        byte_counter += 1
    secs_of_day = secs_of_day - (timestamp_buffer[len(timestamp_buffer) - 1]  << 2)
    byte2= secs_of_day << 6
    # Nanos
    timestamp_buffer.append(byte2 + (nanos_of_sec >> 24))
    byte_counter += 1
    if timestamp_buffer[len(timestamp_buffer) - 1] == ESCAPE_BYTE:
        timestamp_buffer.append(ESCAPE_BYTE)
        byte_counter += 1
    nanos_of_sec = nanos_of_sec - ((timestamp_buffer[len(timestamp_buffer) - 1] & 0x3f) << 24)
    timestamp_buffer.append(nanos_of_sec >> 16)
    byte_counter += 1
    if timestamp_buffer[len(timestamp_buffer) - 1] == ESCAPE_BYTE:
        timestamp_buffer.append(ESCAPE_BYTE)
        byte_counter += 1
    nanos_of_sec = nanos_of_sec - (timestamp_buffer[len(timestamp_buffer) - 1] << 16)
    timestamp_buffer.append(nanos_of_sec >> 8)
    byte_counter += 1
    if timestamp_buffer[len(timestamp_buffer) - 1] == ESCAPE_BYTE:
        timestamp_buffer.append(ESCAPE_BYTE)
        byte_counter += 1
    nanos_of_sec = nanos_of_sec - (timestamp_buffer[len(timestamp_buffer) - 1] << 8)
    timestamp_buffer.append(nanos_of_sec)
    byte_counter += 1
    if timestamp_buffer[len(timestamp_buffer) - 1] == ESCAPE_BYTE:
        timestamp_buffer.append(ESCAPE_BYTE)
        byte_counter += 1
    return timestamp_buffer[0:byte_counter]
    
def listen_to_receiver():
    """ Listen for incoming bytes from the Receiver """
    print('Start listening...')
    while 1:
        recv_bytes = bytearray(1)
        recv_bytes = sock_recv.recv(1)
        process_recv_bytes(recv_bytes)

def process_args():
    # pylint: disable=W0603
    """ Parse start arguments """
    print('Configuration:')
    global recv_host
    global recv_port
    global dest_host
    global dest_port
    global gps_avail
    # Get number of arguments
    args_len = len(sys.argv)
    # Set RECEIVER host
    if args_len > 1:
        recv_host = sys.argv[1]
    # Set RECEIVER port
    if args_len > 2:
        recv_port = int(sys.argv[2])
    # Set DESTINATION host
    if args_len > 3:
        dest_host = sys.argv[3]
    # Set DESTINATION port
    if args_len > 4:
        dest_port = int(sys.argv[4])
    # Set GPS available
    if args_len > 5:
        gps_avail = strIsTrue(sys.argv[5])
    print('Recv host: ' + recv_host)
    print('Recv port: ' + str(recv_port))
    print('Dest host: ' + dest_host)
    print('Dest port: ' + str(dest_port))
    print('GPS avail: ' + str(gps_avail))
    print()
    
def strIsTrue(str):
    return str.lower() in ('true', '1', 'yes', 'y')
# ------------------------------------------------------------------

# EXECUTE ----------------------------------------------------------
# Title
print()
print(TITLE)
print('build ' + BUILD)
print()

# Process start arguments
process_args()

# Create network endpoints
# RECEIVER socket (TCP)
print('Init TCP connection to Receiver')
sock_recv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
# DESTINATION socket (UDP)
print('Init UDP connection to Destination')
sock_dest = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
print()

# Arm SIGNAL handlers
signal.signal(signal.SIGINT, sigint_handler)
signal.signal(signal.SIGTERM, sigterm_handler)

# Connect to Receiver
connect_to_receiver()

# Start worker, listening to Receiver server
listen_to_receiver()
# ------------------------------------------------------------------
