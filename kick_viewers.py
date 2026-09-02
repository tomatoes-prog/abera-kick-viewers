import time
import json
import os
import sys
import base64
import hashlib
import secrets
import webbrowser
import subprocess

from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

try:
    from dotenv import load_dotenv
except ImportError as error:
    raise SystemExit(
        "Falta python-dotenv. Instala las dependencias:\n"
        "  pip install -r requirements.txt"
    ) from error


# ============================================================
# RUTAS (junto al .exe si está empaquetado)
# ============================================================

def carpeta_recursos():
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def carpeta_datos():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


CARPETA_RECURSOS = carpeta_recursos()
CARPETA_DATOS = carpeta_datos()
ARCHIVO_ENV = CARPETA_DATOS / ".env"
ARCHIVO_TOKEN = CARPETA_DATOS / "oauth_tokens.json"
ARCHIVO_SONIDO = CARPETA_RECURSOS / "assets" / "viewer_join.wav"

REDIRECT_URI_DEFAULT = "http://localhost:8079/callback"
MENSAJE_CHAT_DEFAULT = (
    "👋 ¡Gracias por unirte al stream! Si quieres, saluda en el chat 😄"
)


class ConfigError(Exception):
    pass


CLIENT_ID = ""
CLIENT_SECRET = ""
CANAL = ""
REDIRECT_URI = REDIRECT_URI_DEFAULT
INTERVALO = 5
COOLDOWN_CHAT = 30
MENSAJE_CHAT = MENSAJE_CHAT_DEFAULT
OAUTH_HOST = "localhost"
OAUTH_PORT = 8079


# ============================================================
# LEER / GUARDAR CONFIGURACIÓN
# ============================================================

def leer_env_archivo(ruta=None):
    ruta = ruta or ARCHIVO_ENV
    datos = {}

    if not ruta.exists():
        return datos

    for linea in ruta.read_text(encoding="utf-8").splitlines():
        limpia = linea.strip()

        if not limpia or limpia.startswith("#") or "=" not in limpia:
            continue

        clave, valor = limpia.split("=", 1)
        datos[clave.strip()] = valor.strip().strip('"').strip("'")

    return datos


def _env_linea(clave, valor):
    texto = "" if valor is None else str(valor)

    if any(caracter in texto for caracter in ' \n#"\''):
        escapado = texto.replace("\\", "\\\\").replace('"', '\\"')
        return f'{clave}="{escapado}"'

    return f"{clave}={texto}"


def guardar_env(valores):
    actual = leer_env_archivo(ARCHIVO_ENV)
    actual.update(
        {
            clave: valor
            for clave, valor in valores.items()
            if valor is not None
        }
    )

    lineas = [
        "# Generado por KICK Viewer Monitor. No subas este archivo.",
        _env_linea("KICK_CLIENT_ID", actual.get("KICK_CLIENT_ID", "")),
        _env_linea(
            "KICK_CLIENT_SECRET",
            actual.get("KICK_CLIENT_SECRET", "")
        ),
        _env_linea("KICK_CHANNEL", actual.get("KICK_CHANNEL", "")),
        _env_linea(
            "KICK_REDIRECT_URI",
            actual.get("KICK_REDIRECT_URI", REDIRECT_URI_DEFAULT)
        ),
        _env_linea("POLL_INTERVAL", actual.get("POLL_INTERVAL", "5")),
        _env_linea("CHAT_COOLDOWN", actual.get("CHAT_COOLDOWN", "30")),
        _env_linea(
            "CHAT_MESSAGE",
            actual.get("CHAT_MESSAGE", MENSAJE_CHAT_DEFAULT)
        ),
        "",
    ]

    ARCHIVO_ENV.write_text("\n".join(lineas), encoding="utf-8")
    return ARCHIVO_ENV


def _exigir(datos, nombre):
    valor = str(datos.get(nombre, "")).strip()

    if not valor:
        raise ConfigError(
            f"Falta {nombre}.\n"
            "Rellena los datos en la ventana o en el archivo .env.\n"
            "Más detalle en README.md."
        )

    return valor


def _entero(datos, nombre, predeterminado):
    valor = str(datos.get(nombre, "")).strip()

    if not valor:
        return predeterminado

    try:
        numero = int(valor)
    except ValueError as error:
        raise ConfigError(
            f"{nombre} debe ser un número entero. "
            f"Valor actual: {valor!r}"
        ) from error

    if numero < 1:
        raise ConfigError(f"{nombre} debe ser 1 o mayor.")

    return numero


def _aplicar_callback(redirect_uri):
    global OAUTH_HOST, OAUTH_PORT

    callback = urlparse(redirect_uri)
    OAUTH_HOST = callback.hostname or "localhost"

    if callback.port:
        OAUTH_PORT = callback.port
    elif callback.scheme == "https":
        OAUTH_PORT = 443
    else:
        OAUTH_PORT = 80


def cargar_configuracion():
    global CLIENT_ID, CLIENT_SECRET, CANAL
    global REDIRECT_URI, INTERVALO, COOLDOWN_CHAT, MENSAJE_CHAT

    if not ARCHIVO_ENV.exists():
        raise ConfigError(
            f"No encontré el archivo:\n{ARCHIVO_ENV}\n\n"
            "Usa la ventana gráfica o copia .env.example a .env."
        )

    load_dotenv(ARCHIVO_ENV, override=True)
    datos = leer_env_archivo(ARCHIVO_ENV)

    CLIENT_ID = _exigir(datos, "KICK_CLIENT_ID")
    CLIENT_SECRET = _exigir(datos, "KICK_CLIENT_SECRET")
    CANAL = _exigir(datos, "KICK_CHANNEL")

    REDIRECT_URI = (
        datos.get("KICK_REDIRECT_URI", REDIRECT_URI_DEFAULT).strip()
        or REDIRECT_URI_DEFAULT
    )
    INTERVALO = _entero(datos, "POLL_INTERVAL", 5)
    COOLDOWN_CHAT = _entero(datos, "CHAT_COOLDOWN", 30)
    MENSAJE_CHAT = (
        datos.get("CHAT_MESSAGE", MENSAJE_CHAT_DEFAULT).strip()
        or MENSAJE_CHAT_DEFAULT
    )

    _aplicar_callback(REDIRECT_URI)
    return datos


def esperar(segundos, stop_event=None):
    """Duerme, o sale antes si la GUI pide detener el monitor."""

    if stop_event is None:
        time.sleep(segundos)
        return False

    return stop_event.wait(segundos)

# Scopes que pediremos a tu cuenta
SCOPES = "channel:read chat:write"

API_BASE = "https://api.kick.com/public/v1"
OAUTH_BASE = "https://id.kick.com/oauth"


# ============================================================
# UTILIDADES PKCE
# ============================================================

def generar_pkce():
    """
    Crea code_verifier y code_challenge para OAuth PKCE.
    """

    code_verifier = secrets.token_urlsafe(64)

    digest = hashlib.sha256(
        code_verifier.encode("utf-8")
    ).digest()

    code_challenge = base64.urlsafe_b64encode(
        digest
    ).decode("utf-8").rstrip("=")

    return code_verifier, code_challenge


# ============================================================
# SERVIDOR LOCAL PARA CALLBACK OAUTH
# ============================================================

oauth_resultado = {
    "code": None,
    "state": None,
    "error": None
}


class OAuthCallbackHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return

        parametros = parse_qs(parsed.query)

        oauth_resultado["code"] = parametros.get(
            "code", [None]
        )[0]

        oauth_resultado["state"] = parametros.get(
            "state", [None]
        )[0]

        oauth_resultado["error"] = parametros.get(
            "error", [None]
        )[0]

        if oauth_resultado["code"]:
            mensaje = """
            <html>
            <head>
                <meta charset="utf-8">
                <title>KICK Viewer Monitor</title>
            </head>
            <body style="
                background:#111;
                color:white;
                font-family:Arial;
                text-align:center;
                padding-top:80px;
            ">
                <h1 style="color:#53fc18;">
                    ✅ Autorización completada
                </h1>
                <p>
                    Ya puedes cerrar esta pestaña
                    y volver a Kick Viewer Monitor.
                </p>
            </body>
            </html>
            """
        else:
            mensaje = """
            <html>
            <head>
                <meta charset="utf-8">
            </head>
            <body>
                <h1>Error autorizando KICK</h1>
                <p>Vuelve a la consola para ver el error.</p>
            </body>
            </html>
            """

        contenido = mensaje.encode("utf-8")

        self.send_response(200)
        self.send_header(
            "Content-Type",
            "text/html; charset=utf-8"
        )
        self.send_header(
            "Content-Length",
            str(len(contenido))
        )
        self.end_headers()

        self.wfile.write(contenido)

    def log_message(self, format, *args):
        # Evita mensajes innecesarios del servidor HTTP
        return


# ============================================================
# AUTORIZACIÓN OAUTH
# ============================================================

def autorizar_usuario():

    print()
    print("=" * 55)
    print("       AUTORIZACIÓN DE TU CUENTA DE KICK")
    print("=" * 55)

    code_verifier, code_challenge = generar_pkce()

    state = secrets.token_urlsafe(32)

    parametros = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state
    }

    url_autorizacion = (
        f"{OAUTH_BASE}/authorize?"
        + urlencode(parametros)
    )

    # Limpiar datos anteriores
    oauth_resultado["code"] = None
    oauth_resultado["state"] = None
    oauth_resultado["error"] = None

    try:
        servidor = HTTPServer(
            (OAUTH_HOST, OAUTH_PORT),
            OAuthCallbackHandler
        )
    except OSError as error:
        raise RuntimeError(
            f"No pude abrir el puerto {OAUTH_PORT}.\n"
            f"Asegúrate de que esté libre.\n\n"
            f"Error: {error}"
        )

    print()
    print("🌐 Abriendo KICK en tu navegador...")
    print()
    print("Autoriza la aplicación con tu cuenta.")
    print(
        f"Callback configurado: {REDIRECT_URI}"
    )

    webbrowser.open(url_autorizacion)

    # Esperar UNA petición de callback
    servidor.handle_request()

    servidor.server_close()

    if oauth_resultado["error"]:
        raise RuntimeError(
            "KICK rechazó la autorización: "
            + str(oauth_resultado["error"])
        )

    code = oauth_resultado["code"]

    if not code:
        raise RuntimeError(
            "No recibí el código OAuth de KICK."
        )

    if oauth_resultado["state"] != state:
        raise RuntimeError(
            "El parámetro OAuth 'state' no coincide. "
            "Autorización cancelada por seguridad."
        )

    print()
    print("✅ Código OAuth recibido.")
    print("🔑 Obteniendo User Access Token...")

    datos = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "code_verifier": code_verifier,
        "code": code,
    }

    response = requests.post(
        f"{OAUTH_BASE}/token",
        data=datos,
        timeout=20
    )

    if not response.ok:
        print()
        print("❌ Error intercambiando OAuth code:")
        print("Código:", response.status_code)
        print("Respuesta:", response.text)

    response.raise_for_status()

    tokens = response.json()

    tokens["obtenido_en"] = time.time()

    guardar_tokens(tokens)

    print("✅ Cuenta autorizada correctamente.")

    return tokens


# ============================================================
# GUARDAR / CARGAR TOKENS
# ============================================================

def guardar_tokens(tokens):

    with open(
        ARCHIVO_TOKEN,
        "w",
        encoding="utf-8"
    ) as archivo:

        json.dump(
            tokens,
            archivo,
            indent=4
        )


def cargar_tokens():

    if not ARCHIVO_TOKEN.exists():
        return None

    try:
        with open(
            ARCHIVO_TOKEN,
            "r",
            encoding="utf-8"
        ) as archivo:

            return json.load(archivo)

    except Exception:
        return None


# ============================================================
# REFRESH TOKEN
# ============================================================

def renovar_token(tokens):

    refresh_token = tokens.get("refresh_token")

    if not refresh_token:
        print(
            "⚠️ No hay refresh token. "
            "Necesitamos autorizar nuevamente."
        )
        return autorizar_usuario()

    print()
    print("🔄 Renovando User Access Token...")

    datos = {
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_token
    }

    try:
        response = requests.post(
            f"{OAUTH_BASE}/token",
            data=datos,
            timeout=20
        )

        if not response.ok:
            print(
                "⚠️ No se pudo renovar el token."
            )
            print(
                "Respuesta:",
                response.status_code,
                response.text
            )

            return autorizar_usuario()

        nuevos_tokens = response.json()

        # Por seguridad, si KICK no devuelve uno nuevo
        # conservamos el anterior.
        if not nuevos_tokens.get("refresh_token"):
            nuevos_tokens["refresh_token"] = refresh_token

        nuevos_tokens["obtenido_en"] = time.time()

        guardar_tokens(nuevos_tokens)

        print("✅ Token renovado.")

        return nuevos_tokens

    except requests.RequestException:
        raise


# ============================================================
# SABER SI EL TOKEN ESTÁ POR EXPIRAR
# ============================================================

def token_necesita_renovacion(tokens):

    obtenido = tokens.get("obtenido_en", 0)
    expires_in = tokens.get("expires_in", 0)

    if not obtenido or not expires_in:
        return False

    expira = obtenido + int(expires_in)

    # Renovar 60 segundos antes
    return time.time() >= expira - 60


# ============================================================
# OBTENER TOKEN VÁLIDO
# ============================================================

def obtener_tokens_usuario():

    tokens = cargar_tokens()

    if tokens is None:
        return autorizar_usuario()

    if token_necesita_renovacion(tokens):
        tokens = renovar_token(tokens)

    return tokens


# ============================================================
# HEADERS DE LA API
# ============================================================

def headers_api(access_token):

    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


# ============================================================
# OBTENER BROADCASTER ID
# ============================================================

def obtener_id_canal(access_token):

    url = f"{API_BASE}/channels"

    response = requests.get(
        url,
        headers=headers_api(access_token),
        params={
            "slug": CANAL
        },
        timeout=15
    )

    if response.status_code == 401:
        return None

    if not response.ok:
        print()
        print("❌ Error buscando canal:")
        print("Código:", response.status_code)
        print("Respuesta:", response.text)

    response.raise_for_status()

    datos = response.json()

    canales = datos.get("data", [])

    if not canales:
        raise RuntimeError(
            f"No se encontró el canal '{CANAL}'."
        )

    broadcaster_id = canales[0].get(
        "broadcaster_user_id"
    )

    if broadcaster_id is None:
        raise RuntimeError(
            "KICK encontró el canal, pero no devolvió "
            "broadcaster_user_id."
        )

    return int(broadcaster_id)


# ============================================================
# OBTENER VIEWERS
# ============================================================

def obtener_viewers(access_token, broadcaster_id):

    url = f"{API_BASE}/livestreams"

    response = requests.get(
        url,
        headers=headers_api(access_token),
        params={
            "broadcaster_user_id": broadcaster_id
        },
        timeout=15
    )

    if response.status_code == 401:
        return None

    if not response.ok:
        print()
        print("❌ Error consultando viewers:")
        print("Código:", response.status_code)
        print("Respuesta:", response.text)

    response.raise_for_status()

    datos = response.json()

    streams = datos.get("data", [])

    if not streams:
        return 0

    return int(
        streams[0].get("viewer_count", 0)
    )


# ============================================================
# ENVIAR MENSAJE AL CHAT
# ============================================================

def enviar_mensaje_chat(
    access_token,
    broadcaster_id,
    mensaje
):

    url = f"{API_BASE}/chat"

    payload = {
        "broadcaster_user_id": broadcaster_id,
        "content": mensaje,
        "type": "user"
    }

    response = requests.post(
        url,
        headers=headers_api(access_token),
        json=payload,
        timeout=15
    )

    if response.status_code == 401:
        return None

    if not response.ok:
        print()
        print("❌ No pude mandar el mensaje al chat.")
        print("Código:", response.status_code)
        print("Respuesta:", response.text)

        return False

    try:
        datos = response.json()

        enviado = (
            datos.get("data", {})
            .get("is_sent", True)
        )

        if enviado:
            print(
                "💬 Mensaje enviado al chat."
            )
            return True

    except Exception:
        # Un HTTP 200 ya indica que la solicitud
        # fue aceptada.
        print("💬 Mensaje enviado al chat.")
        return True

    return False


# ============================================================
# SONIDO
# ============================================================

def reproducir_sonido():

    if not ARCHIVO_SONIDO.exists():
        print(
            f"\n⚠️ No encontré el sonido:\n{ARCHIVO_SONIDO}"
        )
        return

    ruta = str(ARCHIVO_SONIDO)

    try:
        if sys.platform == "win32":
            import winsound

            winsound.PlaySound(
                ruta,
                winsound.SND_FILENAME |
                winsound.SND_ASYNC
            )
            return

        if sys.platform == "darwin":
            subprocess.Popen(
                ["afplay", ruta],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return

        for comando in (
            ["paplay", ruta],
            ["aplay", "-q", ruta],
            [
                "ffplay",
                "-nodisp",
                "-autoexit",
                "-loglevel",
                "quiet",
                ruta,
            ],
        ):
            try:
                subprocess.Popen(
                    comando,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return
            except FileNotFoundError:
                continue

        print(
            "\n⚠️ No pude reproducir el sonido. "
            "En Linux instala paplay, aplay o ffplay."
        )

    except Exception as error:
        print(
            f"\n⚠️ No se pudo reproducir sonido: {error}"
        )


# ============================================================
# NOTIFICACIÓN DEL SISTEMA
# ============================================================

def mostrar_notificacion(titulo, mensaje):

    try:
        if sys.platform == "win32":
            try:
                from winotify import Notification
            except ImportError:
                return

            toast = Notification(
                app_id="KICK Viewer Monitor",
                title=titulo,
                msg=mensaje,
                duration="short"
            )
            toast.show()
            return

        if sys.platform == "darwin":
            texto_titulo = titulo.replace('"', '\\"')
            texto_mensaje = mensaje.replace('"', '\\"')
            subprocess.run(
                [
                    "osascript",
                    "-e",
                    (
                        f'display notification "{texto_mensaje}" '
                        f'with title "{texto_titulo}"'
                    ),
                ],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return

        subprocess.run(
            ["notify-send", titulo, mensaje],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    except FileNotFoundError:
        return

    except Exception as error:
        print(
            f"\n⚠️ Notificación falló: {error}"
        )


def notificar(anterior, actual):

    diferencia = actual - anterior

    reproducir_sonido()

    if diferencia == 1:
        titulo = "👀 ¡Nuevo espectador!"
    else:
        titulo = f"👀 ¡+{diferencia} espectadores!"

    mensaje = f"Ahora tienes {actual} espectadores"

    mostrar_notificacion(titulo, mensaje)


# ============================================================
# PRUEBA DE SONIDO
# ============================================================

def probar_sonido():

    print()
    print("🔊 Probando sonido de alerta...")

    reproducir_sonido()

    print(
        "   Si escuchaste un chime corto, "
        "el sonido está funcionando."
    )


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

def main(stop_event=None):

    try:
        cargar_configuracion()
    except ConfigError as error:
        if stop_event is not None:
            raise
        raise SystemExit(str(error)) from error

    print()
    print("=" * 55)
    print("              KICK VIEWER MONITOR")
    print("=" * 55)

    print()
    print(f"Canal: https://kick.com/{CANAL}")
    print(f"OAuth callback: {REDIRECT_URI}")

    # --------------------------------------------------------
    # OAUTH USER TOKEN
    # --------------------------------------------------------

    print()
    print("🔑 Preparando autorización de KICK...")

    tokens = obtener_tokens_usuario()

    access_token = tokens["access_token"]

    print("✅ User Access Token disponible.")

    # --------------------------------------------------------
    # BUSCAR ID
    # --------------------------------------------------------

    print(f"🔎 Buscando canal '{CANAL}'...")

    broadcaster_id = obtener_id_canal(
        access_token
    )

    if broadcaster_id is None:

        tokens = renovar_token(tokens)

        access_token = tokens["access_token"]

        broadcaster_id = obtener_id_canal(
            access_token
        )

    print("✅ Canal encontrado.")
    print(
        f"🆔 Broadcaster ID: {broadcaster_id}"
    )

    # --------------------------------------------------------
    # PRUEBA DE SONIDO AL ARRANCAR
    # --------------------------------------------------------

    probar_sonido()

    como_parar = (
        "Pulsa Detener para parar."
        if stop_event is not None
        else "Pulsa CTRL+C para detener."
    )

    print()
    print("-" * 55)
    print("Monitor activo.")
    print(
        f"Consultando viewers cada "
        f"{INTERVALO} segundos."
    )
    print(
        f"Cooldown del mensaje de chat: "
        f"{COOLDOWN_CHAT} segundos."
    )
    print(como_parar)
    print("-" * 55)
    print()

    viewers_anteriores = None

    ultimo_mensaje_chat = 0

    while True:

        try:

            if stop_event is not None and stop_event.is_set():
                print()
                print("🛑 Monitor detenido.")
                break

            # ------------------------------------------------
            # RENOVAR TOKEN SI SE ACERCA SU EXPIRACIÓN
            # ------------------------------------------------

            if token_necesita_renovacion(tokens):

                tokens = renovar_token(tokens)

                access_token = tokens[
                    "access_token"
                ]

            # ------------------------------------------------
            # VIEWERS
            # ------------------------------------------------

            viewers = obtener_viewers(
                access_token,
                broadcaster_id
            )

            # 401
            if viewers is None:

                tokens = renovar_token(tokens)

                access_token = tokens[
                    "access_token"
                ]

                if esperar(1, stop_event):
                    print()
                    print("🛑 Monitor detenido.")
                    break
                continue

            # ------------------------------------------------
            # PRIMERA MEDICIÓN
            # ------------------------------------------------

            if viewers_anteriores is None:

                viewers_anteriores = viewers

                print(
                    f"👁️ Viewers iniciales: {viewers}"
                )

                if esperar(INTERVALO, stop_event):
                    print()
                    print("🛑 Monitor detenido.")
                    break
                continue

            # ------------------------------------------------
            # SUBIDA
            # ------------------------------------------------

            if viewers > viewers_anteriores:

                diferencia = (
                    viewers - viewers_anteriores
                )

                print()
                print(
                    f"🔔 SUBIDA: "
                    f"{viewers_anteriores} → "
                    f"{viewers} (+{diferencia})"
                )

                # Sonido + notificación
                notificar(
                    viewers_anteriores,
                    viewers
                )

                # --------------------------------------------
                # MENSAJE AL CHAT CON COOLDOWN
                # --------------------------------------------

                ahora = time.time()

                segundos_desde_ultimo = (
                    ahora - ultimo_mensaje_chat
                )

                if segundos_desde_ultimo >= COOLDOWN_CHAT:

                    resultado = enviar_mensaje_chat(
                        access_token,
                        broadcaster_id,
                        MENSAJE_CHAT
                    )

                    # Token expirado justo al enviar
                    if resultado is None:

                        tokens = renovar_token(tokens)

                        access_token = tokens[
                            "access_token"
                        ]

                        resultado = enviar_mensaje_chat(
                            access_token,
                            broadcaster_id,
                            MENSAJE_CHAT
                        )

                    if resultado:
                        ultimo_mensaje_chat = ahora

                else:

                    faltan = int(
                        COOLDOWN_CHAT
                        - segundos_desde_ultimo
                    )

                    print(
                        "💬 Mensaje no enviado "
                        f"(cooldown: {faltan}s)."
                    )

            # ------------------------------------------------
            # BAJADA
            # ------------------------------------------------

            elif viewers < viewers_anteriores:

                print()
                print(
                    f"📉 BAJADA: "
                    f"{viewers_anteriores} → "
                    f"{viewers}"
                )

            # ------------------------------------------------
            # MOSTRAR VIEWERS
            # ------------------------------------------------

            print(
                f"\r👁️ Viewers actuales: {viewers}   ",
                end="",
                flush=True
            )

            viewers_anteriores = viewers

            if esperar(INTERVALO, stop_event):
                print()
                print("🛑 Monitor detenido.")
                break

        # ----------------------------------------------------
        # CTRL+C
        # ----------------------------------------------------

        except KeyboardInterrupt:

            print()
            print()
            print("🛑 Monitor detenido.")
            break

        # ----------------------------------------------------
        # ERRORES DE RED
        # ----------------------------------------------------

        except requests.RequestException as error:

            print()
            print(
                f"⚠️ Error de conexión: {error}"
            )
            print(
                "Reintentando en 10 segundos..."
            )

            if esperar(10, stop_event):
                print()
                print("🛑 Monitor detenido.")
                break

        # ----------------------------------------------------
        # OTRO ERROR
        # ----------------------------------------------------

        except Exception as error:

            print()
            print(
                f"❌ Error: {error}"
            )
            print(
                "Reintentando en 10 segundos..."
            )

            if esperar(10, stop_event):
                print()
                print("🛑 Monitor detenido.")
                break


# ============================================================
# INICIO
# ============================================================

if __name__ == "__main__":
    main()