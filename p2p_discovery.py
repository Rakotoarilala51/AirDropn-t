"""
p2p_discovery.py — Découverte automatique des pairs sur le réseau
local (façon Xender), via UDP broadcast.

Ce module est totalement indépendant de p2p_core.py, qui reste
inchangé et continue de gérer uniquement le transfert de fichier lui
même (TCP, sockets, buffer). Ici on ne fait que répondre à la
question « qui est disponible sur le réseau et sur quel port ? » —
une fois un pair choisi, on retombe directement sur
p2p_core.send_file_async(ip, port, ...) comme avant, seule la saisie
manuelle de l'IP/port est remplacée par une sélection dans une liste.

Protocole (simple, best-effort, UDP) :
  - Le pair en mode "Recevoir" lance un répondeur UDP
    (start_discovery_responder) qui écoute sur DISCOVERY_PORT et
    répond à toute requête de découverte valide par ses infos (nom +
    port TCP d'écoute déjà ouvert par p2p_core).
  - Le pair en mode "Envoyer" diffuse une requête en broadcast UDP
    (scan_for_peers / scan_for_peers_async) puis collecte les
    réponses pendant un court délai.

Limites à connaître : le broadcast UDP ne traverse pas les routeurs
(donc uniquement pour un même réseau local/Wi-Fi), et certains
réseaux (VPN, isolation clients Wi-Fi côté routeur, pare-feu) peuvent
bloquer le broadcast ou l'UDP entrant — dans ce cas le scan ne
trouvera rien même si le récepteur est bien en écoute.
"""
import json
import socket
import threading
import time

DISCOVERY_PORT = 51234
APP_TAG = "P2P_TRANSFER_APP_V1"
REQUEST_TYPE = "discover"
RESPONSE_TYPE = "here"


def get_local_ip():
    """Best-effort : IP locale à afficher à titre informatif seulement
    (la connexion réelle passe toujours par la découverte broadcast,
    pas par cette valeur)."""
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
    """À lancer côté "Recevoir", en même temps que
    p2p_core.start_listener_thread(tcp_port, ...). Répond à toute
    requête de découverte reçue en broadcast par son nom et le port
    TCP sur lequel il écoute déjà. Tourne dans un thread daemon et ne
    bloque jamais l'appelant."""
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
    """À lancer côté "Envoyer" : diffuse une requête de découverte en
    broadcast UDP et collecte les réponses pendant `timeout` secondes.
    Bloquant (appelé depuis un thread par scan_for_peers_async si
    utilisé dans une GUI). Retourne une liste de dicts
    {"ip", "port", "name"}, dédupliquée par (ip, port)."""
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
    """Version non bloquante de scan_for_peers pour une GUI : lance le
    scan dans un thread daemon et appelle callback(peers_list) une
    fois terminé (callback est invoqué depuis ce thread — si tu
    touches un widget Tkinter dedans, repasse par root.after(0, ...) )."""

    def _run():
        peers = scan_for_peers(timeout=timeout, log=log)
        callback(peers)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread