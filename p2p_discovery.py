import json
import socket
import threading
import time

DISCOVERY_PORT = 51234
APP_TAG = "P2P_TRANSFER_APP_V1"
REQUEST_TYPE = "discover"
RESPONSE_TYPE = "here"


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def _make_request():
    return json.dumps({"tag": APP_TAG, "type": REQUEST_TYPE}).encode("utf-8")


def _make_response(name, tcp_port):
    return json.dumps({
        "tag": APP_TAG,
        "type": RESPONSE_TYPE,
        "name": name,
        "port": tcp_port,
    }).encode("utf-8")


def start_discovery_responder(tcp_port, device_name=None, log=print):
    device_name = device_name or socket.gethostname()

    def _run():
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("0.0.0.0", DISCOVERY_PORT))
        except OSError as e:
            log(f"[Error] Découverte indisponible sur le port UDP {DISCOVERY_PORT}: {e}")
            return
        log(f"[*] Répondeur de découverte actif (visible sous « {device_name} »)...")
        while True:
            try:
                data, addr = sock.recvfrom(1024)
            except Exception:
                continue
            try:
                msg = json.loads(data.decode("utf-8"))
            except Exception:
                continue
            if msg.get("tag") == APP_TAG and msg.get("type") == REQUEST_TYPE:
                try:
                    sock.sendto(_make_response(device_name, tcp_port), addr)
                except Exception:
                    pass

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread


def scan_for_peers(timeout=2.5, log=print):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(0.3)

    try:
        sock.sendto(_make_request(), ("<broadcast>", DISCOVERY_PORT))
    except Exception as e:
        log(f"[Error] Impossible d'envoyer la requête de découverte: {e}")
        sock.close()
        return []

    peers = {}
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            data, addr = sock.recvfrom(1024)
        except socket.timeout:
            continue
        except Exception:
            break
        try:
            msg = json.loads(data.decode("utf-8"))
        except Exception:
            continue
        if msg.get("tag") == APP_TAG and msg.get("type") == RESPONSE_TYPE:
            ip = addr[0]
            port = msg.get("port")
            name = msg.get("name") or ip
            peers[(ip, port)] = {"ip": ip, "port": port, "name": name}

    sock.close()
    return list(peers.values())


def scan_for_peers_async(callback, timeout=2.5, log=print):
    def _run():
        peers = scan_for_peers(timeout=timeout, log=log)
        callback(peers)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread