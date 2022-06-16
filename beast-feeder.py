#!/usr/bin/env python3
# pylint: disable=C0103,C0114,C0112,C0116,W1514

""" beast-feeder.py <recv_host> <recv_port> <dest_host> <dest_port> """

# LIBS ---------
import socket
import sys
import functools

# --------------

# TITLE ---------------------------
BUILD_MAJOR = '10'
BUILD_DATE = '220616' # this is the fall-back date for versioning
BUILD_MINOR = '01'
TITLE = 'SKYSQUITTER BEAST-FEEDER'
VERSION_FILENAME = '/.VERSION.beast-feeder'
# ---------------------------------

# DEFAULTS -------------------
RECV_HOST = 'readsb'
RECV_PORT = 30005
DEST_HOST = '10.9.2.1'
DEST_PORT = 11092
# ----------------------------

# CONSTANTS ------------------
# Beast
ESCAPE_BYTE = 0x1a
MSG_TYPE_1 = 0x31
MSG_TYPE_2 = 0x32
MSG_TYPE_3 = 0x33
MSG_TYPE_4 = 0x34
# Buffer
BUFFER_SIZE = 64
# ----------------------------

# VARIABLES ---------------------
buffer = bytearray(BUFFER_SIZE)
buffer_index = 0
# Set defaults
recv_host = RECV_HOST
recv_port = RECV_PORT
dest_host = DEST_HOST
dest_port = DEST_PORT
# -------------------------------

# ensure print always flushes the buffer:
print = functools.partial(print, flush=True)    # pylint: disable=W0622
# ----------------------------

# Make Build String:
try:
    with open(VERSION_FILENAME, 'r') as f:
        EXT_BUILD_DATE = f.read()
except: # pylint: disable=W0702
    BUILD = BUILD_MAJOR + '.' + BUILD_DATE + '.' + BUILD_MINOR
else:
    BUILD = BUILD_MAJOR + '.' + EXT_BUILD_DATE.strip() + '.' + BUILD_MINOR

# FUNCTIONS DEFS ---------------------------------------------------
def preamble_detected():
    """Return 1 if message preamble detected"""
    ## global buffer_index
    index = buffer_index - 1
    # Check message type
    try:
        if buffer[index] != MSG_TYPE_1 and buffer[index] != MSG_TYPE_2 and \
                        buffer[index] != MSG_TYPE_3 and \
                        buffer[index] != MSG_TYPE_4:
            return 0
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
        return 0
    if esc_count % 2 == 0:
        return 0
    return 1

def msg_is_valid(message):
    """Return 1 if message is to be sent; check message preamble and type;
       ESC byte at beginning required"""
    if message[0] != ESCAPE_BYTE:
        return 0
    # Either message tyoe 2 or 3 required
    if message[1] != MSG_TYPE_2 and message[1] != MSG_TYPE_3:
        return 0
    # Message preamble and type is valid -> send to destination
    return 1

# Connect to the Receiver server via UDP
def connect_to_receiver():
    """ """
    print('Connect to Receiver')
    ## global recv_host
    ## global recv_port
    server_address = (recv_host, recv_port)
    sock_recv.connect(server_address)

# Send message to Destination via UDP
def send_to_destination(message):
    ## global dest_host
    ## global dest_port
    server_address = (dest_host, dest_port)
    sock_dest.sendto(message, server_address)

# Process received byte
def process_recv_bytes(recv_bytes):
    global buffer_index         # pylint: disable=W0603
    # Avoid buffer overflow
    if buffer_index == BUFFER_SIZE:
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
            send_to_destination(message)
        # Reset buffer
        buffer[0] = buffer[buffer_index - 2]
        buffer[1] = buffer[buffer_index - 1]
        buffer_index = 2

# Listen for incoming bytes from the Receiver
def listen_to_receiver():
    print('Start listening...')
    while 1:
        recv_bytes = bytearray(1)
        recv_bytes = sock_recv.recv(1)
        process_recv_bytes(recv_bytes)

# Parse start arguments
def process_args():
    # pylint: disable=W0603
    print('Configuration:')
    global recv_host
    global recv_port
    global dest_host
    global dest_port
    # Get number of arguments
    args_len = len(sys.argv) - 1
    # Set RECEIVER host
    if args_len >= 1:
        recv_host = sys.argv[1]
    # Set RECEIVER port
    if args_len >= 2:
        recv_port = int(sys.argv[2])
    # Set DESTINATION host
    if args_len >= 3:
        dest_host = sys.argv[3]
    # Set DESTINATION port
    if args_len >= 4:
        dest_port = int(sys.argv[4])
    print('Recv host: ' + recv_host)
    print('Recv port: ' + str(recv_port))
    print('Dest host: ' + dest_host)
    print('Dest port: ' + str(dest_port))
    print()
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

# Connect to Receiver
connect_to_receiver()

# Start worker, listening to Receiver server
listen_to_receiver()
# ------------------------------------------------------------------
