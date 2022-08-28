"""
Very basic HTTP server that just listens on a port and responds.
"""

import base64
import hashlib
import select
import socket

TCP_IP = '127.0.0.1'
TCP_PORT = 5006
BUFFER_SIZE = 1024 * 1024
WS_ENDPOINT = '/websocket'

DEFAULT_HTTP_RESPONSE = (
    b'''<HTML><HEAD><meta http-equiv="content-type"
content="text/html;charset=utf-8">\r\n
<TITLE>200 OK</TITLE></HEAD><BODY>\r\n
<H1>200 OK</H1>\r\n
Welcome to the default.\r\n
</BODY></HTML>\r\n\r\n''')

MAGIC_WEBSOCKET_UUID_STRING = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'


def main():
    '''
    Creates the front-door TCP socket and listens for connections.
    '''

    # We can have a main socket that listens for initial connections.
    tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcp_socket.bind((TCP_IP, TCP_PORT))

    tcp_socket.listen(1)
    print('Listening on port: ', TCP_PORT)

    input_sockets = [tcp_socket]
    output_sockets = []  # Maybe use, we'll see
    xlist = []  # Not using

    ws_sockets = []

    while True:
        # Get the sockets that are ready to read (the first of the
        # three-tuple).
        readable_sockets = select.select(input_sockets,
                                         output_sockets,
                                         xlist,
                                         5)[0]

        for ready_socket in readable_sockets:
            # Make sure it's not already closed
            if (ready_socket.fileno() == -1):
                continue
            if ready_socket == tcp_socket:
                print('Handling main door socket')
                handle_new_connection(tcp_socket, input_sockets)
            elif ready_socket in ws_sockets:
                print('this is where we would handle the websocket message')
                handle_websocket_message(ready_socket, input_sockets,
                                         ws_sockets)
            else:
                print('Handling regular socket read')
                handle_request(ready_socket, input_sockets, ws_sockets)


def handle_new_connection(main_door_socket, input_sockets):
    # When we get a connection on the main socket, we want to accept a new
    # connection and add it to our input socket list. When we loop back around,
    # that socket will be ready to read from.
    client_socket, client_addr = main_door_socket.accept()
    print('New socket', client_socket.fileno(), 'from address:', client_addr)
    input_sockets.append(client_socket)


def handle_websocket_message(client_socket, input_sockets, ws_sockets):
    print('Handling WS message from client socket:', client_socket.fileno())
    message = b''
    # We can start by reading as much as we can
    while True:
        data_in_bytes = client_socket.recv(BUFFER_SIZE)
        print('received', len(data_in_bytes), 'bytes')
        # TODO: check payload length and see if we're done reading
        if len(data_in_bytes) == 0:
            close_socket(client_socket, input_sockets, ws_sockets)
            return


def handle_request(client_socket, input_sockets, ws_sockets):
    print('Handling request from client socket:', client_socket.fileno())
    message = ''
    # Very naive approach: read until we find the last blank line
    while True:
        data_in_bytes = client_socket.recv(BUFFER_SIZE)
        # Connnection on client side has closed.
        if len(data_in_bytes) == 0:
            close_socket(client_socket, input_sockets, ws_sockets)
            return
        message_segment = data_in_bytes.decode()
        message += message_segment
        if (len(message) > 4 and message_segment[-4:] == '\r\n\r\n'):
            break

    print('Received message:')
    print(message)

    (method, target, http_version, headers_map) = parse_request(message)

    print('method, target, http_version:', method, target, http_version)
    print('headers:')
    print(headers_map)

    # We will know it's a websockets request if the handshake request is
    # present.
    if target == WS_ENDPOINT:
        print('request to ws endpoint!')
        if is_valid_ws_handshake_request(method,
                                         target,
                                         http_version,
                                         headers_map):
            handle_ws_handshake_request(
                client_socket,
                ws_sockets,
                headers_map)
            return
        else:
            # Invalid WS request.
            client_socket.send(b'HTTP/1.1 400 Bad Request')
            close_socket(client_socket, input_sockets, ws_sockets)
            return

    # For now, just return a 200. Should probably return length too, eh
    client_socket.send(b'HTTP/1.1 200 OK\r\n\r\n' + DEFAULT_HTTP_RESPONSE)
    close_socket(client_socket, input_sockets, ws_sockets)


def handle_ws_handshake_request(client_socket,
                                ws_sockets,
                                headers_map):
    ws_sockets.append(client_socket)

    # To handle a WS handshake, we have to generate an accept key from the
    # sec-websocket-key and a magic string.
    sec_websocket_accept_value = generate_sec_websocket_accept(
        headers_map.get('sec-websocket-key'))

    # We can now build the response, telling the client we're switching
    # protocols while providing the key.
    websocket_response = ''
    websocket_response += 'HTTP/1.1 101 Switching Protocols\r\n'
    websocket_response += 'Upgrade: websocket\r\n'
    websocket_response += 'Connection: Upgrade\r\n'
    websocket_response += (
        'Sec-WebSocket-Accept: ' + sec_websocket_accept_value.decode() + '\r\n')
    websocket_response += '\r\n'

    print('\nresponse:\n',websocket_response)

    client_socket.send(websocket_response.encode())


def generate_sec_websocket_accept(sec_websocket_key):
    # We generate the accept key by concatenating the sec-websocket-key
    # and the magic string, Sha1 hashing it, and base64 encoding it.
    # See https://datatracker.ietf.org/doc/html/rfc6455#page-7
    combined = sec_websocket_key + MAGIC_WEBSOCKET_UUID_STRING
    hashed_combined_string = hashlib.sha1(combined.encode())
    encoded = base64.b64encode(hashed_combined_string.digest())
    return encoded


def is_valid_ws_handshake_request(method, target, http_version, headers_map):
    # There are a few things to verify to see if it's a valid WS handshake.
    # First, the method must be get.
    is_get = method == 'GET'
    # HTTP version must be >= 1.1. We can do a really naive check.
    http_version_number = float(http_version.split('/')[1])
    http_version_enough = http_version_number >= 1.1
    # Finally, we should have the right headers. This is a subset of what we'd
    # really want to check.
    headers_valid = (
        ('upgrade' in headers_map and
         headers_map.get('upgrade') == 'websocket') and
        ('connection' in headers_map and
         headers_map.get('connection') == 'Upgrade') and
        ('sec-websocket-key' in headers_map)
    )
    return (is_get and http_version_enough and headers_valid)


# Parses the first line and headers from the request.
def parse_request(request):
    headers_map = {}
    # Assume headers and body are split by '\r\n\r\n' and we always have them.
    # Also assume all headers end with'\r\n'.
    # Also assume it starts with the method.
    split_request = request.split('\r\n\r\n')[0].split('\r\n')
    [method, target, http_version] = split_request[0].split(' ')
    headers = split_request[1:]
    for header_entry in headers:
        [header_name, value] = header_entry.split(': ')
        # Headers are case insensitive, so we can just keep track in lowercase.
        # Here's a trick though: the case of the values matter. Otherwise,
        # things don't hash and encode right!
        headers_map[header_name.lower()] = value
    return (method, target, http_version, headers_map)


def close_socket(client_socket, input_sockets, ws_sockets):
    print('closing socket')
    if client_socket in ws_sockets:
        ws_sockets.remove(client_socket)
    input_sockets.remove(client_socket)
    client_socket.close()
    return


if __name__ == '__main__':
    main()
