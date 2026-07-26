import socket
import threading
import os

BUFFER_SIZE = 4096


def receive_file_handler(client_socket, log=print):
    try:
        # 1. Read metadata (Filename)
        metadata = client_socket.recv(BUFFER_SIZE).decode('utf-8').strip()
        if not metadata:
            return

        filename = os.path.basename(metadata)
        log(f"[Receiving] Getting file: {filename}...")

        # 2. Write incoming byte streams to disk
        with open(filename, 'wb') as f:
            while True:
                bytes_read = client_socket.recv(BUFFER_SIZE)
                if not bytes_read:
                    break  # File transfer complete
                f.write(bytes_read)

        log(f"[Success] File saved as '{filename}'")
    except Exception as e:
        log(f"[Error] Failed to receive file: {e}")
    finally:
        client_socket.close()


def start_listening_server(port, log=print):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(('0.0.0.0', port))
    server.listen(5)
    log(f"[*] Node is active and listening on port {port}...")
    while True:
        client_socket, addr = server.accept()
        thread = threading.Thread(target=receive_file_handler, args=(client_socket, log))
        thread.daemon = True
        thread.start()


def start_listener_thread(port, log=print):
    thread = threading.Thread(target=start_listening_server, args=(port, log), daemon=True)
    thread.start()
    return thread


def send_file(peer_ip, peer_port, file_path, log=print):
    if not os.path.exists(file_path):
        log("[Error] File does not exist locally.")
        return
    try:
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect((peer_ip, peer_port))

        # 1. Send the file name as metadata first (padded to fit buffer safely)
        filename = os.path.basename(file_path)
        client.sendall(filename.ljust(BUFFER_SIZE).encode('utf-8'))

        # 2. Stream the file data in chunks
        log(f"[Sending] Streaming {filename} to {peer_ip}:{peer_port}...")
        with open(file_path, 'rb') as f:
            while True:
                bytes_read = f.read(BUFFER_SIZE)
                if not bytes_read:
                    break
                client.sendall(bytes_read)

        log("[Success] File sent completely.")
    except Exception as e:
        log(f"[Error] Failed to connect or send: {e}")
    finally:
        client.close()


def send_file_async(peer_ip, peer_port, file_path, log=print):
    thread = threading.Thread(
        target=send_file, args=(peer_ip, peer_port, file_path, log), daemon=True
    )
    thread.start()
    return thread