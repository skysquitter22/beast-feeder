#!/usr/bin/env python3
# pylint: disable=C0103,C0114,C0112,C0116,W1514,W0702,W0622

""" beast-feeder.py <recv_host> <recv_port> <dest_host> <dest_port> <set_timestamp> """

# LIBS ---------
import sys
import signal
import functools
import time
import datetime
import socket
import subprocess
# --------------

# TITLE ---------------------------
BUILD_MAJOR = '15'
BUILD_DATE = '221211' # this is the fall-back date for versioning
BUILD_MINOR = '01'
TITLE = 'SKYSQUITTER BEAST-FEEDER'
VERSION_FILENAME = '/.VERSION.beast-feeder'
# ---------------------------------

# DEFAULTS -------------------
RECV_HOST = 'readsb'
RECV_PORT = 30005
DEST_HOST = '10.9.2.1'
DEST_PORT = 11092
SET_TIMESTAMP = False
# ----------------------------

# CONSTANTS ------------------
# Beast
ESCAPE_BYTE = 0x1a
MSG_TYPE_1 = 0x31
MSG_TYPE_2 = 0x32
MSG_TYPE_3 = 0x33
MSG_TYPE_4 = 0x34
PREAMBLE_LEN = 2
TIMESTAMP_LEN = 6
SIGNAL_LEN = 1
MODE_AC_LEN = 2
MODE_S_SHORT = 7
MODE_S_LONG = 14
TIMING_LEN = 1
META_LEN = PREAMBLE_LEN + TIMESTAMP_LEN + SIGNAL_LEN
MSG_TYPE_1_LEN = META_LEN + MODE_AC_LEN
MSG_TYPE_2_LEN = META_LEN + MODE_S_SHORT
MSG_TYPE_3_LEN = META_LEN + MODE_S_LONG
MSG_TYPE_4_LEN = META_LEN + TIMING_LEN
MSG_NO_TYPE_LEN = 1 # If no preamble detected, then poll _1_ byte
TIMESTAMP_INDEX = 2
# Polling
RECV_BYTES_SIZE = 1 # Byte per Byte required
BUFFER_MIN_SIZE_REQUIRED = 9 # Save, because: Preamble + Timestamp + Signal/Unused
# Clock check
CLOCK_DIFF_LIMIT = 50 # [msec] Maximum allowed clock difference
CLOCK_DIFF_UPDATE_INTERVAL = 300 # [s] Clock diff update interval
CLOCK_DIFF_MIN_UPDATE_INTERVAL = 5 # [s] Clock diff minimum update interval
CLOCK_DIFF_VALID_PERIOD = 30 # [mins] Clock diff value is valid for this given period
CLOCK_DIFF_NA = 99999
CLOCK_DIFF_CMD = 'check_clockdiff'
CLOCK_DIFF_RESULT_SPLIT_STR = ','
# ----------------------------

# VARIABLES ---------------------
buffer = bytearray()
# Set defaults
recv_host = RECV_HOST
recv_port = RECV_PORT
dest_host = DEST_HOST
dest_port = DEST_PORT
set_timestamp = SET_TIMESTAMP
# Clock check
clock_diff_last_update = 0
clock_diff_timestamp = 0
clock_diff = CLOCK_DIFF_NA
# Init so as to cause output on error
clock_diff_was_valid = True
clock_diff_is_valid = False
clock_diff_too_old = False
clock_diff_too_bad = False
clock_diff_error = ''
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
def process_args():
    # pylint: disable=W0603
    """ Parse start arguments """
    print('Configuration:')
    global recv_host
    global recv_port
    global dest_host
    global dest_port
    global set_timestamp
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
        set_timestamp = str_is_true(sys.argv[5])
    print('Recv host: ' + recv_host)
    print('Recv port: ' + str(recv_port))
    print('Dest host: ' + dest_host)
    print('Dest port: ' + str(dest_port))
    print('Set Timestamp: ' + str(set_timestamp))
    print()

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

def listen_to_receiver():
    """ Listen for incoming bytes from the Receiver """
    print('Start listening...')
    poll_len = MSG_NO_TYPE_LEN # Init size to poll at beginning
    while True:
        recv_bytes = bytearray(sock_recv.recv(poll_len))
        poll_len = process_recv_bytes(recv_bytes)
        if poll_len > MSG_NO_TYPE_LEN:
            poll_len = poll_len - PREAMBLE_LEN

def process_recv_bytes(recv_bytes):
    """ Process received bytes, return byte array len to be received next dependent on detected message preamble type """
    global clock_diff_is_valid
    global clock_diff_was_valid
    # Add received data chunk to buffer
    buffer.extend(recv_bytes)
    # Look for Beast preamble
    msg_len = preamble_detected()
    if msg_len > MSG_NO_TYPE_LEN:
        # Prepare received message
        message =  bytearray(buffer[0:len(buffer) - PREAMBLE_LEN])
        # Send message
        if msg_is_valid(message):
            # NTP system timestamp is to be set, check clock diff
            if set_timestamp:
                # Check latest clock diff
                clock_diff_is_valid = check_clock_diff()
                # Check for clock diff status change
                if clock_diff_is_valid and not clock_diff_was_valid:
                    print('Clock diff is valid.')
                elif not clock_diff_is_valid and clock_diff_was_valid:
                    print('Clock diff not valid!') 
                if clock_diff_is_valid:
                    message = get_new_timestamped_message(message)
                    send_to_destination(message)
                # Reset status change
                clock_diff_was_valid = clock_diff_is_valid
            # Timestamp stays untouched, clock doesn't matter
            else:
                send_to_destination(message)
        # Reset buffer and set preamble in new message buffer
        preamble = [buffer[len(buffer) - PREAMBLE_LEN], buffer[len(buffer) - PREAMBLE_LEN + 1]]
        buffer.clear()
        buffer.extend(preamble)
        return msg_len

def preamble_detected():
    """ Return message len dependent on type if message preamble is detected, otherwise return 0 """
    # Minimum buffer length required
    if len(buffer) < BUFFER_MIN_SIZE_REQUIRED:
        return 0
    index = len(buffer) - 1
    # Check message type and length
    msg_len = MSG_NO_TYPE_LEN
    if buffer[index] == MSG_TYPE_1:
        msg_len = MSG_TYPE_1_LEN
    elif buffer[index] == MSG_TYPE_2:
        msg_len = MSG_TYPE_2_LEN
    elif buffer[index] == MSG_TYPE_3:
        msg_len = MSG_TYPE_3_LEN
    elif buffer[index] == MSG_TYPE_4:
        msg_len = MSG_TYPE_4_LEN
    else:
        return 0
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
    return msg_len

def send_to_destination(message):
    """ Send message to Destination via UDP """
    server_address = (dest_host, dest_port)
    sock_dest.sendto(message, server_address)

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
    new_message = bytearray()
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
    timestamp_buffer = bytearray()
    # Secs
    timestamp_buffer.append(secs_of_day >> 10)
    if timestamp_buffer[len(timestamp_buffer) - 1] == ESCAPE_BYTE:
        timestamp_buffer.append(ESCAPE_BYTE)
    secs_of_day = secs_of_day - (timestamp_buffer[len(timestamp_buffer) - 1] << 10)
    timestamp_buffer.append(secs_of_day >> 2)
    if timestamp_buffer[len(timestamp_buffer) - 1] == ESCAPE_BYTE:
        timestamp_buffer.append(ESCAPE_BYTE)
    secs_of_day = secs_of_day - (timestamp_buffer[len(timestamp_buffer) - 1]  << 2)
    byte2= secs_of_day << 6
    # Nanos
    timestamp_buffer.append(byte2 + (nanos_of_sec >> 24))
    if timestamp_buffer[len(timestamp_buffer) - 1] == ESCAPE_BYTE:
        timestamp_buffer.append(ESCAPE_BYTE)
    nanos_of_sec = nanos_of_sec - ((timestamp_buffer[len(timestamp_buffer) - 1] & 0x3f) << 24)
    timestamp_buffer.append(nanos_of_sec >> 16)
    if timestamp_buffer[len(timestamp_buffer) - 1] == ESCAPE_BYTE:
        timestamp_buffer.append(ESCAPE_BYTE)
    nanos_of_sec = nanos_of_sec - (timestamp_buffer[len(timestamp_buffer) - 1] << 16)
    timestamp_buffer.append(nanos_of_sec >> 8)
    if timestamp_buffer[len(timestamp_buffer) - 1] == ESCAPE_BYTE:
        timestamp_buffer.append(ESCAPE_BYTE)
    nanos_of_sec = nanos_of_sec - (timestamp_buffer[len(timestamp_buffer) - 1] << 8)
    timestamp_buffer.append(nanos_of_sec)
    if timestamp_buffer[len(timestamp_buffer) - 1] == ESCAPE_BYTE:
        timestamp_buffer.append(ESCAPE_BYTE)
    return timestamp_buffer

def check_clock_diff():
    """ Return True if clock difference to NTP server is within the limits """
    global clock_diff_last_update
    global clock_diff_timestamp
    global clock_diff_too_old
    global clock_diff_too_bad
    now = round(time.time() * 1000.0)
    age_last_update = now - clock_diff_last_update
    age_clock_diff = now - clock_diff_timestamp
    # Update clock diff values shall be updated
    if (clock_diff_timestamp == 0 and age_last_update > CLOCK_DIFF_MIN_UPDATE_INTERVAL * 1000) or age_clock_diff > CLOCK_DIFF_UPDATE_INTERVAL * 1000:
        update_clock_diff()
        clock_diff_last_update = now
        age_clock_diff = now - clock_diff_timestamp
    # Check that values are within the limits
    # Check age
    if age_clock_diff > CLOCK_DIFF_VALID_PERIOD * 60000:
        if not clock_diff_too_old:
            print('Clock diff is too old!')
            clock_diff_too_old = True
        return False
    clock_diff_too_old = False
    # Check clock difference
    if clock_diff > CLOCK_DIFF_LIMIT:
        if not clock_diff_too_bad:
            print('Clock diff is too bad!')
            clock_diff_too_bad = True
        return False
    clock_diff_too_bad = False
    return True

def update_clock_diff():
    """ Update the clock diff values by running the CLI check script """
    global clock_diff_timestamp
    global clock_diff
    global clock_diff_error
    result = subprocess.run([CLOCK_DIFF_CMD], stdout = subprocess.PIPE, text = True)
    res_str = result.stdout
    res_chunks = res_str.split(CLOCK_DIFF_RESULT_SPLIT_STR)
    tstmp = int(res_chunks[0].strip())
    diff1 = int(res_chunks[1].strip())
    diff2 = int(res_chunks[2].strip())
    err = res_chunks[3].replace('"', '').strip()
    if (diff1 == CLOCK_DIFF_NA and diff2 == CLOCK_DIFF_NA) or len(err) > 0:
        if err != clock_diff_error:
            print(err)
        clock_diff_error = str(err)
        return
    clock_diff_error = ''
    clock_diff_timestamp = tstmp
    clock_diff = max(abs(diff1), abs(diff2))

def str_is_true(str):
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
