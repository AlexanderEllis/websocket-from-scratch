"""
Very basic HTTP server that just listens on a port and responds.
"""

import socket
import select

TCP_IP = '127.0.0.1'
TCP_PORT = 5006
BUFFER_SIZE = 1024 * 1024


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
            else:
                print('Handling regular socket read')
                handle_request(ready_socket, input_sockets)


def handle_new_connection(main_door_socket, input_sockets):
    # When we get a connection on the main socket, we want to accept a new
    # connection and add it to our input socket list. When we loop back around,
    # that socket will be ready to read from.
    client_socket, client_addr = main_door_socket.accept()
    print('New socket', client_socket.fileno(), 'from address:', client_addr)
    input_sockets.append(client_socket)


def handle_request(client_socket, input_sockets):
    print('Handling request from client socket:', client_socket.fileno())
    message = ''
    # Very naive approach: read until we find the last blank line
    while True:
        data_in_bytes = client_socket.recv(BUFFER_SIZE)
        # Connnection on client side has closed.
        if len(data_in_bytes) == 0:
            close_socket(client_socket, input_sockets)
            input_sockets.remove(client_socket)
            client_socket.close()
            return
        message_segment = data_in_bytes.decode()
        message += message_segment
        if (len(message) > 4 and message_segment[-4:] == '\r\n\r\n'):
            break

    print('Received message:')
    print(message)

    # For now, just return a 404
    client_socket.send(b'HTTP/1.1 404 Not Found\r\n\r\n')
    close_socket(client_socket, input_sockets)


def close_socket(client_socket, input_sockets):
    input_sockets.remove(client_socket)
    client_socket.close()
    return



if __name__ == '__main__':
    main()

