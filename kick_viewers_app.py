"""Ventana gráfica de KICK Viewer Monitor (Windows, ligera)."""

import queue
import sys
import threading
import webbrowser
from tkinter import Tk, StringVar, BooleanVar, messagebox
from tkinter import ttk, scrolledtext

import kick_viewers as monitor


KICK_VERDE = "#53fc18"
FONDO = "#111111"
FONDO_PANEL = "#1a1a1a"
TEXTO = "#f2f2f2"
TEXTO_SUAVE = "#9a9a9a"
KICK_DEV = "https://kick.com/settings/developer"


class EscritorCola:
    def __init__(self, cola):
        self.cola = cola

    def write(self, texto):
        if texto:
            self.cola.put(texto)

    def flush(self):
        return None


class KickViewerApp:
    def __init__(self, raiz):
        self.raiz = raiz
        self.raiz.title("KICK Viewer Monitor")
        self.raiz.configure(bg=FONDO)
        self.raiz.minsize(560, 620)
        self.raiz.geometry("640x720")

        self.cola_log = queue.Queue()
        self.stop_event = None
        self.hilo = None
        self._stdout_original = sys.stdout
        self._stderr_original = sys.stderr

        self.canal = StringVar()
        self.client_id = StringVar()
        self.client_secret = StringVar()
        self.mostrar_secreto = BooleanVar(value=False)
        self.intervalo = StringVar(value="5")
        self.cooldown = StringVar(value="30")
        self.mensaje_chat = StringVar(value=monitor.MENSAJE_CHAT_DEFAULT)

        self._cargar_env()
        self._estilos()
        self._construir()
        self._actualizar_log()
        self.raiz.protocol("WM_DELETE_WINDOW", self._al_cerrar)

    def _cargar_env(self):
        datos = monitor.leer_env_archivo()
        self.canal.set(datos.get("KICK_CHANNEL", ""))
        self.client_id.set(datos.get("KICK_CLIENT_ID", ""))
        self.client_secret.set(datos.get("KICK_CLIENT_SECRET", ""))
        self.intervalo.set(datos.get("POLL_INTERVAL", "5"))
        self.cooldown.set(datos.get("CHAT_COOLDOWN", "30"))
        self.mensaje_chat.set(
            datos.get("CHAT_MESSAGE", monitor.MENSAJE_CHAT_DEFAULT)
        )

    def _estilos(self):
        estilo = ttk.Style()
        estilo.theme_use("clam")

        estilo.configure(".", background=FONDO, foreground=TEXTO)
        estilo.configure("TFrame", background=FONDO)
        estilo.configure(
            "TLabel",
            background=FONDO,
            foreground=TEXTO,
            font=("Segoe UI", 10),
        )
        estilo.configure(
            "Titulo.TLabel",
            background=FONDO,
            foreground=KICK_VERDE,
            font=("Segoe UI", 16, "bold"),
        )
        estilo.configure(
            "Suave.TLabel",
            background=FONDO,
            foreground=TEXTO_SUAVE,
            font=("Segoe UI", 9),
        )
        estilo.configure(
            "TEntry",
            fieldbackground=FONDO_PANEL,
            foreground=TEXTO,
            insertcolor=TEXTO,
            bordercolor="#333333",
            lightcolor="#333333",
            darkcolor="#333333",
            padding=6,
        )
        estilo.configure(
            "Verde.TButton",
            background=KICK_VERDE,
            foreground="#111111",
            font=("Segoe UI", 10, "bold"),
            padding=(14, 8),
        )
        estilo.map(
            "Verde.TButton",
            background=[("disabled", "#3d5c2a"), ("active", "#6aff3d")],
        )
        estilo.configure(
            "TButton",
            background="#2a2a2a",
            foreground=TEXTO,
            padding=(12, 8),
        )
        estilo.map("TButton", background=[("active", "#3a3a3a")])
        estilo.configure(
            "TCheckbutton",
            background=FONDO,
            foreground=TEXTO_SUAVE,
        )
        estilo.configure(
            "TLabelframe",
            background=FONDO,
            foreground=KICK_VERDE,
        )
        estilo.configure(
            "TLabelframe.Label",
            background=FONDO,
            foreground=KICK_VERDE,
        )

    def _construir(self):
        marco = ttk.Frame(self.raiz, padding=18)
        marco.pack(fill="both", expand=True)

        ttk.Label(
            marco,
            text="KICK Viewer Monitor",
            style="Titulo.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            marco,
            text="Avisa con sonido cuando entra gente a tu stream.",
            style="Suave.TLabel",
        ).pack(anchor="w", pady=(2, 12))

        formulario = ttk.Frame(marco)
        formulario.pack(fill="x")
        formulario.columnconfigure(1, weight=1)

        self._fila(formulario, 0, "Canal", self.canal)
        self._fila(formulario, 1, "Client ID", self.client_id)
        self._fila(
            formulario,
            2,
            "Client Secret",
            self.client_secret,
            secreto=True,
        )

        ttk.Checkbutton(
            formulario,
            text="Mostrar secret",
            variable=self.mostrar_secreto,
            command=self._toggle_secreto,
        ).grid(row=3, column=1, sticky="w", pady=(0, 8))

        ttk.Label(
            formulario,
            text=(
                "Redirect URI en Kick Developer: "
                f"{monitor.REDIRECT_URI_DEFAULT}"
            ),
            style="Suave.TLabel",
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(0, 10))

        avanzado = ttk.LabelFrame(marco, text="Opcional", padding=10)
        avanzado.pack(fill="x", pady=(0, 12))
        avanzado.columnconfigure(1, weight=1)
        self._fila(avanzado, 0, "Intervalo (s)", self.intervalo)
        self._fila(avanzado, 1, "Cooldown chat (s)", self.cooldown)
        self._fila(avanzado, 2, "Mensaje chat", self.mensaje_chat)

        botones = ttk.Frame(marco)
        botones.pack(fill="x", pady=(0, 10))

        self.boton_iniciar = ttk.Button(
            botones,
            text="Iniciar",
            style="Verde.TButton",
            command=self.iniciar,
        )
        self.boton_iniciar.pack(side="left")

        self.boton_detener = ttk.Button(
            botones,
            text="Detener",
            command=self.detener,
            state="disabled",
        )
        self.boton_detener.pack(side="left", padx=(8, 0))

        ttk.Button(
            botones,
            text="Kick Developer",
            command=lambda: webbrowser.open(KICK_DEV),
        ).pack(side="right")

        ttk.Label(marco, text="Registro", style="Suave.TLabel").pack(
            anchor="w"
        )
        self.log = scrolledtext.ScrolledText(
            marco,
            height=16,
            bg=FONDO_PANEL,
            fg=TEXTO,
            insertbackground=TEXTO,
            relief="flat",
            font=("Consolas", 10),
            wrap="word",
        )
        self.log.pack(fill="both", expand=True, pady=(4, 0))
        self.log.configure(state="disabled")

        self._escribir(
            "1) Crea una app en Kick Developer (botón de la derecha).\n"
            f"2) Redirect URI exacta: {monitor.REDIRECT_URI_DEFAULT}\n"
            "3) Pega Client ID, Client Secret y el slug de tu canal.\n"
            "4) Pulsa Iniciar. La primera vez se abre el navegador.\n"
        )

    def _fila(self, padre, fila, etiqueta, variable, secreto=False):
        ttk.Label(padre, text=etiqueta).grid(
            row=fila, column=0, sticky="nw", pady=5, padx=(0, 10)
        )
        entrada = ttk.Entry(padre, textvariable=variable)
        if secreto:
            entrada.configure(show="*")
            self.entrada_secreto = entrada
        entrada.grid(row=fila, column=1, sticky="ew", pady=5)

    def _toggle_secreto(self):
        self.entrada_secreto.configure(
            show="" if self.mostrar_secreto.get() else "*"
        )

    def _escribir(self, texto):
        self.log.configure(state="normal")
        self.log.insert("end", texto)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _actualizar_log(self):
        try:
            while True:
                self._escribir(self.cola_log.get_nowait())
        except queue.Empty:
            pass
        self.raiz.after(80, self._actualizar_log)

    def _guardar(self):
        monitor.guardar_env(
            {
                "KICK_CHANNEL": self.canal.get().strip(),
                "KICK_CLIENT_ID": self.client_id.get().strip(),
                "KICK_CLIENT_SECRET": self.client_secret.get().strip(),
                "KICK_REDIRECT_URI": monitor.REDIRECT_URI_DEFAULT,
                "POLL_INTERVAL": self.intervalo.get().strip() or "5",
                "CHAT_COOLDOWN": self.cooldown.get().strip() or "30",
                "CHAT_MESSAGE": self.mensaje_chat.get().strip()
                or monitor.MENSAJE_CHAT_DEFAULT,
            }
        )

    def _corriendo(self):
        return self.hilo is not None and self.hilo.is_alive()

    def iniciar(self):
        if self._corriendo():
            return

        if not all(
            (
                self.canal.get().strip(),
                self.client_id.get().strip(),
                self.client_secret.get().strip(),
            )
        ):
            messagebox.showwarning(
                "Faltan datos",
                "Canal, Client ID y Client Secret son obligatorios.",
            )
            return

        try:
            self._guardar()
            monitor.cargar_configuracion()
        except Exception as error:
            messagebox.showerror("Configuración", str(error))
            return

        self.stop_event = threading.Event()
        sys.stdout = EscritorCola(self.cola_log)
        sys.stderr = EscritorCola(self.cola_log)

        self.boton_iniciar.configure(state="disabled")
        self.boton_detener.configure(state="normal")

        self.hilo = threading.Thread(
            target=self._correr_monitor,
            daemon=True,
        )
        self.hilo.start()

    def _correr_monitor(self):
        try:
            monitor.main(self.stop_event)
        except Exception as error:
            self.cola_log.put(f"\n❌ {error}\n")
        finally:
            self.raiz.after(0, self._al_parar)

    def detener(self):
        if self.stop_event is not None:
            self.stop_event.set()
        self.boton_detener.configure(state="disabled")

    def _al_parar(self):
        sys.stdout = self._stdout_original
        sys.stderr = self._stderr_original
        self.hilo = None
        self.stop_event = None
        self.boton_iniciar.configure(state="normal")
        self.boton_detener.configure(state="disabled")

    def _al_cerrar(self):
        if self._corriendo():
            self.detener()
            self.raiz.after(200, self._al_cerrar)
            return
        self.raiz.destroy()


def main():
    try:
        raiz = Tk()
        KickViewerApp(raiz)
        raiz.mainloop()
    except Exception as error:
        messagebox.showerror("KICK Viewer Monitor", str(error))
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
