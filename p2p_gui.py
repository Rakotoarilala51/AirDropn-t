import queue
import socket
import time
import tkinter as tk
from tkinter import font as tkfont
from tkinter import filedialog, messagebox

import p2p_core
import p2p_discovery

COLORS = {
    "bg": "#11151C",
    "panel": "#181E28",
    "input_bg": "#212938",
    "border": "#2B3444",
    "text": "#E6E9F0",
    "muted": "#7C8698",
    "accent": "#45D9C0",
    "accent2": "#5B8DEF",
    "error": "#F0637A",
    "console_bg": "#0C0F14",
}


def pick_font(root, candidates, fallback="TkDefaultFont"):
    available = set(tkfont.families(root))
    for name in candidates:
        if name in available:
            return name
    return fallback


def round_points(x1, y1, x2, y2, r):
    return [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]


class RoundedButton(tk.Canvas):
    def __init__(self, parent, text, command, bg, fg, hover_bg,
                 width=180, height=36, radius=10, font=None):
        super().__init__(parent, width=width, height=height,
                          bg=parent["bg"], highlightthickness=0, bd=0,
                          cursor="hand2")
        self.text = text
        self.command = command
        self.bg_color = bg
        self.hover_bg = hover_bg
        self.fg = fg
        self.radius = radius
        self.width = width
        self.height = height
        self.font = font
        self.enabled = True
        self._draw(self.bg_color)
        self.bind("<Button-1>", self._on_click)
        self.bind("<Enter>", lambda e: self._draw(self.hover_bg) if self.enabled else None)
        self.bind("<Leave>", lambda e: self._draw(self.bg_color) if self.enabled else None)

    def _draw(self, color):
        self.delete("all")
        pts = round_points(1, 1, self.width - 1, self.height - 1, self.radius)
        self.create_polygon(pts, smooth=True, fill=color, outline=color)
        fg = self.fg if self.enabled else COLORS["muted"]
        self.create_text(self.width / 2, self.height / 2, text=self.text,
                          fill=fg, font=self.font)

    def _on_click(self, event):
        if self.enabled and self.command:
            self.command()

    def set_enabled(self, enabled):
        self.enabled = enabled
        self._draw(self.bg_color if enabled else COLORS["input_bg"])

    def set_text(self, text):
        self.text = text
        self._draw(self.bg_color if self.enabled else COLORS["input_bg"])


class StatusPill(tk.Canvas):
    def __init__(self, parent, width=170, height=28, font=None):
        super().__init__(parent, width=width, height=height,
                          bg=parent["bg"], highlightthickness=0, bd=0)
        self.width = width
        self.height = height
        self.font = font
        self.set_state(False, "hors ligne")

    def set_state(self, online, label):
        self.delete("all")
        border = COLORS["accent"] if online else COLORS["border"]
        dot = COLORS["accent"] if online else COLORS["muted"]
        pts = round_points(1, 1, self.width - 1, self.height - 1, self.height / 2)
        self.create_polygon(pts, smooth=True, fill=COLORS["panel"], outline=border)
        self.create_oval(12, self.height / 2 - 4, 20, self.height / 2 + 4, fill=dot, outline=dot)
        self.create_text(30, self.height / 2, text=label, fill=COLORS["text"],
                          font=self.font, anchor="w")


def node_icon(parent, size=32):
    c = tk.Canvas(parent, width=size, height=size, bg=parent["bg"], highlightthickness=0)
    c.create_line(9, size - 9, size - 9, 9, fill=COLORS["accent"], width=2)
    c.create_oval(3, size - 13, 13, size - 3, fill=COLORS["accent2"], outline="")
    c.create_oval(size - 13, 3, size - 3, 13, fill=COLORS["accent"], outline="")
    return c


class Card(tk.Frame):
    def __init__(self, parent, title, label_font):
        super().__init__(parent, bg=COLORS["panel"],
                          highlightbackground=COLORS["border"],
                          highlightthickness=1, bd=0)
        eyebrow = " ".join(list(title.upper()))
        tk.Label(self, text=eyebrow, bg=COLORS["panel"], fg=COLORS["muted"],
                  font=label_font).pack(anchor="w", padx=16, pady=(14, 6))
        self.body = tk.Frame(self, bg=COLORS["panel"])
        self.body.pack(fill="both", expand=True, padx=16, pady=(0, 16))


class StyledEntry(tk.Entry):
    def __init__(self, parent, font, width=None):
        kwargs = dict(
            bg=COLORS["input_bg"], fg=COLORS["text"],
            insertbackground=COLORS["text"], relief="flat",
            highlightthickness=1, highlightbackground=COLORS["border"],
            highlightcolor=COLORS["accent2"], font=font,
        )
        if width:
            kwargs["width"] = width
        super().__init__(parent, **kwargs)


class PeerRow(tk.Frame):
    def __init__(self, parent, name, ip, port, on_choose, font_name, font_ip, font_btn):
        super().__init__(parent, bg=COLORS["input_bg"],
                          highlightbackground=COLORS["border"],
                          highlightthickness=1, bd=0, cursor="hand2")
        self.ip = ip
        self.port = port
        self.on_choose = on_choose

        info = tk.Frame(self, bg=COLORS["input_bg"])
        info.pack(side="left", fill="both", expand=True, padx=12, pady=8)
        tk.Label(info, text=name, bg=COLORS["input_bg"], fg=COLORS["text"],
                  font=font_name, anchor="w").pack(anchor="w")
        tk.Label(info, text=f"{ip}:{port}", bg=COLORS["input_bg"], fg=COLORS["muted"],
                  font=font_ip, anchor="w").pack(anchor="w")

        RoundedButton(self, "Choisir", self._choose, bg=COLORS["accent2"],
                      fg="#F5F8FF", hover_bg="#7BA3F5", width=90, height=30,
                      font=font_btn).pack(side="right", padx=12, pady=8)

        for widget in (self, info):
            widget.bind("<Button-1>", lambda e: self._choose())

    def _choose(self):
        self.on_choose(self.ip, self.port)


class P2PApp:
    def __init__(self, root):
        self.root = root
        self.root.title("P2P Transfer")
        self.root.configure(bg=COLORS["bg"])
        self.root.geometry("640x680")
        self.root.resizable(False, False)

        self.sans = pick_font(root, ["Segoe UI", "Helvetica Neue", "Helvetica", "Arial"])
        self.mono = pick_font(root, ["Cascadia Mono", "Consolas", "SF Mono", "Menlo",
                                      "DejaVu Sans Mono", "Courier New"])

        self.f_title = (self.sans, 15, "bold")
        self.f_label = (self.sans, 9)
        self.f_eyebrow = (self.sans, 9, "bold")
        self.f_button = (self.sans, 10, "bold")
        self.f_mono = (self.mono, 10)
        self.f_log = (self.mono, 9)

        self.log_queue = queue.Queue()
        self.listening = False
        self.role = None
        self.selected_peer = None
        self.peer_rows = []

        self._build_shell()
        self._show_page(self.page_mode)
        self._poll_log_queue()

    # ---------- Construction de l'UI ----------

    def _build_shell(self):
        # --- En-tête (toujours visible) ---
        header = tk.Frame(self.root, bg=COLORS["bg"])
        header.pack(fill="x", padx=20, pady=(18, 10))

        left = tk.Frame(header, bg=COLORS["bg"])
        left.pack(side="left")
        node_icon(left).pack(side="left", padx=(0, 10))
        tk.Label(left, text="P2P Transfer", bg=COLORS["bg"], fg=COLORS["text"],
                  font=self.f_title).pack(side="left")

        self.status_pill = StatusPill(header, font=self.f_label)
        self.status_pill.pack(side="right")

        # --- Conteneur de pages empilées (une seule visible à la fois) ---
        self.container = tk.Frame(self.root, bg=COLORS["bg"])
        self.container.pack(fill="x", padx=20, pady=8)
        self.container.grid_columnconfigure(0, weight=1)

        self.page_mode = tk.Frame(self.container, bg=COLORS["bg"])
        self.page_receive = tk.Frame(self.container, bg=COLORS["bg"])
        self.page_scan = tk.Frame(self.container, bg=COLORS["bg"])
        self.page_send = tk.Frame(self.container, bg=COLORS["bg"])

        for page in (self.page_mode, self.page_receive, self.page_scan, self.page_send):
            page.grid(row=0, column=0, sticky="nsew")

        self._build_mode_page()
        self._build_receive_page()
        self._build_scan_page()
        self._build_send_page()

        # --- Carte : journal (toujours visible, peu importe la page) ---
        log_card = Card(self.root, "Journal", self.f_eyebrow)
        log_card.pack(fill="both", expand=True, padx=20, pady=(8, 18))

        console = tk.Frame(log_card.body, bg=COLORS["console_bg"],
                             highlightbackground=COLORS["border"], highlightthickness=1)
        console.pack(fill="both", expand=True)

        self.log_widget = tk.Text(
            console, bg=COLORS["console_bg"], fg=COLORS["text"],
            insertbackground=COLORS["text"], relief="flat", font=self.f_log,
            height=10, wrap="word", state="disabled", padx=10, pady=8,
        )
        self.log_widget.pack(fill="both", expand=True)
        self.log_widget.tag_configure("success", foreground=COLORS["accent"])
        self.log_widget.tag_configure("error", foreground=COLORS["error"])
        self.log_widget.tag_configure("transfer", foreground=COLORS["accent2"])
        self.log_widget.tag_configure("muted", foreground=COLORS["muted"])
        self.log_widget.tag_configure("normal", foreground=COLORS["text"])

    def _show_page(self, page):
        page.tkraise()

    # --- Page 1 : choix du rôle ---

    def _build_mode_page(self):
        card = Card(self.page_mode, "Choisir un rôle", self.f_eyebrow)
        card.pack(fill="x")
        body = card.body

        tk.Label(body, text="Que veux-tu faire ?", bg=COLORS["panel"], fg=COLORS["text"],
                  font=self.f_label).pack(anchor="w", pady=(0, 10))

        row = tk.Frame(body, bg=COLORS["panel"])
        row.pack(fill="x")
        RoundedButton(
            row, "Recevoir un fichier", lambda: self._select_role("receive"),
            bg=COLORS["accent"], fg="#0B1410", hover_bg="#5CEBD2",
            width=200, height=44, font=self.f_button,
        ).pack(side="left")
        RoundedButton(
            row, "Envoyer un fichier", lambda: self._select_role("send"),
            bg=COLORS["accent2"], fg="#F5F8FF", hover_bg="#7BA3F5",
            width=200, height=44, font=self.f_button,
        ).pack(side="left", padx=(14, 0))

        tk.Label(
            body,
            text="« Recevoir » se rend simplement visible sur le réseau. "
                 "« Envoyer » scanne le réseau pour te montrer les appareils "
                 "en mode « Recevoir » et t'y connecte directement — "
                 "aucune IP ni port à saisir.",
            bg=COLORS["panel"], fg=COLORS["muted"], font=self.f_label,
            wraplength=560, justify="left",
        ).pack(anchor="w", pady=(14, 0))

    def _select_role(self, role):
        self.role = role
        if role == "receive":
            self._show_page(self.page_receive)
        else:
            self.selected_peer = None
            self.peer_label.config(text="Pair sélectionné : —")
            self._show_page(self.page_scan)
            self._start_scan()

    # --- Page 2 : rôle "Recevoir" ---

    def _build_receive_page(self):
        card = Card(self.page_receive, "Nœud local (recevoir)", self.f_eyebrow)
        card.pack(fill="x")
        body = card.body

        top = tk.Frame(body, bg=COLORS["panel"])
        top.pack(fill="x")
        RoundedButton(
            top, "\u2190 Retour", lambda: self._show_page(self.page_mode),
            bg=COLORS["input_bg"], fg=COLORS["text"], hover_bg=COLORS["border"],
            width=100, height=30, font=self.f_label,
        ).pack(side="left")

        tk.Label(body, text="Port d'écoute", bg=COLORS["panel"], fg=COLORS["muted"],
                  font=self.f_label).pack(anchor="w", pady=(14, 4))
        self.port_entry = StyledEntry(body, self.f_mono, width=8)
        self.port_entry.insert(0, "5001")
        self.port_entry.pack(anchor="w", ipady=4)

        self.listen_button = RoundedButton(
            body, "Démarrer l'écoute", self.on_start_listening,
            bg=COLORS["accent"], fg="#0B1410", hover_bg="#5CEBD2",
            width=190, height=38, font=self.f_button,
        )
        self.listen_button.pack(anchor="w", pady=(14, 0))

        self.receive_hint = tk.Label(
            body, text="En attente d'être découvert par un pair...",
            bg=COLORS["panel"], fg=COLORS["muted"], font=self.f_label,
            wraplength=560, justify="left",
        )
        self.receive_hint.pack(anchor="w", pady=(12, 0))

    def on_start_listening(self):
        if self.listening:
            return
        try:
            port = int(self.port_entry.get())
        except ValueError:
            messagebox.showerror("Erreur", "Le port doit être un nombre entier.")
            return

        device_name = socket.gethostname()
        p2p_core.start_listener_thread(port, log=self._log_from_thread)
        p2p_discovery.start_discovery_responder(
            port, device_name=device_name, log=self._log_from_thread
        )

        self.listening = True
        self.listen_button.set_enabled(False)
        self.listen_button.set_text("En écoute...")
        self.port_entry.config(state="disabled")
        self.status_pill.set_state(True, f"en écoute · {port}")
        self.receive_hint.config(
            text=f"Visible sous le nom « {device_name} » — les pairs qui "
                 f"scannent le réseau te trouveront automatiquement."
        )

    # --- Page 3 : rôle "Envoyer", étape scan ---

    def _build_scan_page(self):
        card = Card(self.page_scan, "Pairs détectés", self.f_eyebrow)
        card.pack(fill="x")
        body = card.body

        top = tk.Frame(body, bg=COLORS["panel"])
        top.pack(fill="x")
        RoundedButton(
            top, "\u2190 Retour", lambda: self._show_page(self.page_mode),
            bg=COLORS["input_bg"], fg=COLORS["text"], hover_bg=COLORS["border"],
            width=100, height=30, font=self.f_label,
        ).pack(side="left")
        self.scan_button = RoundedButton(
            top, "Rescanner", self._start_scan,
            bg=COLORS["accent2"], fg="#F5F8FF", hover_bg="#7BA3F5",
            width=120, height=30, font=self.f_label,
        )
        self.scan_button.pack(side="right")

        self.scan_status = tk.Label(
            body, text="Scan en cours...", bg=COLORS["panel"],
            fg=COLORS["muted"], font=self.f_label,
        )
        self.scan_status.pack(anchor="w", pady=(12, 8))

        self.peers_container = tk.Frame(body, bg=COLORS["panel"])
        self.peers_container.pack(fill="x")

    def _start_scan(self):
        for row in self.peer_rows:
            row.destroy()
        self.peer_rows = []
        self.scan_status.config(text="Scan en cours...")
        self.scan_button.set_enabled(False)
        self.status_pill.set_state(False, "scan en cours")
        p2p_discovery.scan_for_peers_async(
            self._on_scan_done, timeout=2.5, log=self._log_from_thread
        )

    def _on_scan_done(self, peers):
        # scan_for_peers_async appelle ce callback depuis un thread
        # d'arrière-plan : on repasse par root.after pour ne toucher
        # les widgets Tkinter que depuis le thread principal.
        self.root.after(0, lambda: self._render_peers(peers))

    def _render_peers(self, peers):
        self.scan_button.set_enabled(True)
        self.status_pill.set_state(False, "hors ligne")
        for row in self.peer_rows:
            row.destroy()
        self.peer_rows = []

        if not peers:
            self.scan_status.config(
                text="Aucun pair trouvé. Vérifie que l'autre appareil est en "
                     "mode « Recevoir », sur le même réseau Wi-Fi/local."
            )
            return

        self.scan_status.config(text=f"{len(peers)} pair(s) trouvé(s) :")
        for peer in peers:
            row = PeerRow(
                self.peers_container, peer["name"], peer["ip"], peer["port"],
                self._on_peer_chosen, self.f_label, self.f_mono, self.f_label,
            )
            row.pack(fill="x", pady=4)
            self.peer_rows.append(row)

    def _on_peer_chosen(self, ip, port):
        self.selected_peer = (ip, port)
        self.peer_label.config(text=f"Pair sélectionné : {ip}:{port}")
        self._show_page(self.page_send)

    # --- Page 4 : rôle "Envoyer", étape transfert (fichier + envoi) ---

    def _build_send_page(self):
        card = Card(self.page_send, "Envoyer un fichier", self.f_eyebrow)
        card.pack(fill="x")
        body = card.body
        body.grid_columnconfigure(0, weight=1)

        top = tk.Frame(body, bg=COLORS["panel"])
        top.grid(row=0, column=0, columnspan=2, sticky="we")
        RoundedButton(
            top, "\u2190 Changer de pair", lambda: self._show_page(self.page_scan),
            bg=COLORS["input_bg"], fg=COLORS["text"], hover_bg=COLORS["border"],
            width=160, height=30, font=self.f_label,
        ).pack(side="left")

        self.peer_label = tk.Label(
            body, text="Pair sélectionné : —", bg=COLORS["panel"],
            fg=COLORS["text"], font=self.f_label,
        )
        self.peer_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=(12, 10))

        tk.Label(body, text="Fichier", bg=COLORS["panel"], fg=COLORS["muted"],
                  font=self.f_label).grid(row=2, column=0, sticky="w", columnspan=2)

        file_row = tk.Frame(body, bg=COLORS["panel"])
        file_row.grid(row=3, column=0, columnspan=2, sticky="we", pady=(4, 14))
        self.file_entry = StyledEntry(file_row, self.f_mono)
        self.file_entry.pack(side="left", fill="x", expand=True, ipady=4)
        RoundedButton(
            file_row, "Parcourir", self.on_browse_file,
            bg=COLORS["input_bg"], fg=COLORS["text"], hover_bg=COLORS["border"],
            width=100, height=32, font=self.f_label,
        ).pack(side="left", padx=(10, 0))

        self.send_button = RoundedButton(
            body, "Envoyer le fichier \u2192", self.on_send_file,
            bg=COLORS["accent2"], fg="#F5F8FF", hover_bg="#7BA3F5",
            width=210, height=38, font=self.f_button,
        )
        self.send_button.grid(row=4, column=0, columnspan=2, sticky="w")

    def on_browse_file(self):
        path = filedialog.askopenfilename()
        if path:
            self.file_entry.delete(0, tk.END)
            self.file_entry.insert(0, path)

    def on_send_file(self):
        if not self.selected_peer:
            messagebox.showerror("Erreur", "Choisis d'abord un pair détecté dans la liste.")
            return
        peer_ip, peer_port = self.selected_peer
        file_path = self.file_entry.get().strip()
        if not file_path:
            messagebox.showerror("Erreur", "Choisis un fichier à envoyer.")
            return

        # Toujours la même fonction p2p_core, inchangée — seule la
        # provenance de peer_ip/peer_port change (scan au lieu de saisie).
        p2p_core.send_file_async(peer_ip, peer_port, file_path, log=self._log_from_thread)

    # ---------- Logging thread-safe (identique à avant, + coloration) ----------

    def _log_from_thread(self, message):
        self.log_queue.put(message)

    def _tag_for(self, message):
        if message.startswith("[Success]"):
            return "success"
        if message.startswith("[Error]"):
            return "error"
        if message.startswith("[Sending]") or message.startswith("[Receiving]"):
            return "transfer"
        if message.startswith("[*]"):
            return "muted"
        return "normal"

    def _poll_log_queue(self):
        while not self.log_queue.empty():
            message = self.log_queue.get_nowait()
            timestamp = time.strftime("%H:%M:%S")
            tag = self._tag_for(message)
            self.log_widget.config(state="normal")
            self.log_widget.insert(tk.END, f"{timestamp}  ", "muted")
            self.log_widget.insert(tk.END, message + "\n", tag)
            self.log_widget.see(tk.END)
            self.log_widget.config(state="disabled")
        self.root.after(100, self._poll_log_queue)


def main():
    root = tk.Tk()
    P2PApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()