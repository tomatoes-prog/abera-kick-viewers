# KICK Viewer Monitor

Script para **Windows, macOS y Linux** que vigila cuántas personas hay viendo tu stream de [Kick](https://kick.com).

Cuando el número de espectadores **sube**:

- suena un chime corto (no un bip de PC)
- muestra una notificación del sistema
- puede enviar un mensaje de bienvenida al chat (con pausa para no spamear)

Cuando **baja**, solo lo escribe en la consola.

Cada persona que use este proyecto debe crear **su propia app** en Kick. No copies el Client ID ni el Client Secret de nadie.

---

## Opción fácil (Windows): la app `.exe`

No hace falta instalar Python.

1. Descarga **KickViewerMonitor-windows.zip** en [Releases](https://github.com/tomatoes-prog/abera-kick-viewers/releases/latest).
2. Descomprime la carpeta y abre `KickViewerMonitor.exe`.
3. Crea tu app en [Kick Developer](https://kick.com/settings/developer) con esta Redirect URI **exacta**:

   ```
   http://localhost:8079/callback
   ```

4. Pega Client ID, Client Secret y el slug de tu canal (`kick.com/tu-canal` → `tu-canal`).
5. Pulsa **Iniciar**. La primera vez se abre el navegador para autorizar.

`.env` y `oauth_tokens.json` se crean solos junto al `.exe`. No los subas a internet.

La carpeta del zip es un `onedir` a propósito: arranca más rápido que un único `.exe` gigante.

---

## Qué necesitas (si usas Python)

- Python **3.10** o superior
- Una cuenta de Kick
- Una **aplicación de desarrollador** en Kick (se crea en 2 minutos)
- En Linux, para el sonido: `paplay`, `aplay` o `ffplay`
- En Linux, para las notificaciones: `notify-send` (paquete `libnotify-bin` en Debian/Ubuntu)

---



## 1. Instalar Python



### Windows

1. Entra en [https://www.python.org/downloads/](https://www.python.org/downloads/) y descarga la versión estable.
2. En el instalador, marca **Add python.exe to PATH**.
3. Pulsa *Install Now*.
4. Abre **PowerShell** y comprueba:

```powershell
python --version
```

Debe mostrar algo como `Python 3.12.x`.

### macOS

Opción A (instalador oficial): [https://www.python.org/downloads/macos/](https://www.python.org/downloads/macos/)

Opción B (Homebrew):

```bash
brew install python
```

Comprueba:

```bash
python3 --version
```



### Linux (Debian / Ubuntu)

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip
python3 --version
```

En Fedora:

```bash
sudo dnf install python3 python3-pip
```

---



## 2. Descargar el proyecto y crear el entorno

En una terminal, desde la carpeta donde quieras el proyecto:

```bash
git clone https://github.com/tomatoes-prog/abera-kick-viewers.git
cd abera-kick-viewers
```

Si no usas git, descarga el ZIP del repositorio y descomprímelo.

Crea un entorno virtual (aisla las librerías de este script):

**Windows (PowerShell):**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Si PowerShell bloquea el script de activación:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

**macOS / Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---



## 3. Crear la app en Kick (obligatorio)

1. Entra en Kick con la cuenta **del canal** que vas a monitorizar.
2. Abre [https://kick.com/settings/developer](https://kick.com/settings/developer) (ajustes → pestaña **Developer**).
3. Crea una aplicación nueva.
4. En **Redirect URI** pon **exactamente** esto, sin barra al final ni cambios de puerto:
  ```
   http://localhost:8079/callback
  ```
   Kick compara el texto al milímetro. Si no coincide, la autorización falla.
5. Copia el **Client ID** y el **Client Secret**.

El script pide estos permisos: `channel:read` y `chat:write`. Autoriza con la cuenta dueña del canal; si usas otra cuenta, consultar viewers puede funcionar y el mensaje de chat no.

---



## 4. Configurar el archivo `.env`

En la carpeta del proyecto:

**Windows (PowerShell):**

```powershell
Copy-Item .env.example .env
```

**macOS / Linux:**

```bash
cp .env.example .env
```

Abre `.env` con un editor y rellena:

```env
KICK_CLIENT_ID=el_client_id_de_tu_app
KICK_CLIENT_SECRET=el_client_secret_de_tu_app
KICK_CHANNEL=tu-canal
```

`KICK_CHANNEL` es el slug de la URL. Si tu stream es `https://kick.com/abera-cloud`, el valor es `abera-cloud`.

Opcional (si no los pones, se usan estos valores):


| Variable            | Default                                                              | Qué hace                                    |
| ------------------- | -------------------------------------------------------------------- | ------------------------------------------- |
| `KICK_REDIRECT_URI` | `http://localhost:8079/callback`                                     | Debe coincidir con Kick Developer           |
| `POLL_INTERVAL`     | `5`                                                                  | Segundos entre cada consulta de viewers     |
| `CHAT_COOLDOWN`     | `30`                                                                 | Segundos mínimos entre mensajes al chat     |
| `CHAT_MESSAGE`      | `👋 ¡Gracias por unirte al stream! Si quieres, saluda en el chat 😄` | Texto que se envía cuando suben los viewers |


**No subas** `.env` **a GitHub.** Ya está en `.gitignore`.

---



## 5. Arrancar

Con el entorno virtual activado:

**Windows:**

```powershell
python kick_viewers.py
```

**macOS / Linux:**

```bash
python3 kick_viewers.py
```

La **primera vez**:

1. Se abre el navegador para que autorices la app en Kick.
2. Tras aceptar, puedes cerrar esa pestaña y volver a la consola.
3. El script crea `oauth_tokens.json` **solo en tu PC**. No lo edites ni lo subas al repo.
4. Suena una prueba. Si oyes el chime, el audio está bien.
5. Cada 5 segundos (o el intervalo que hayas puesto) consulta los viewers.

Para parar: `Ctrl+C`.

Las siguientes veces reutiliza `oauth_tokens.json`. Si la autorización se rompe (token inválido, cambiaste de app, etc.), **borra** `oauth_tokens.json` y vuelve a ejecutar el script.

---



## Qué archivos tocas tú y cuáles no


| Archivo                  | ¿Lo creas tú?                | ¿Va al repo? | Notas                                                                   |
| ------------------------ | ---------------------------- | ------------ | ----------------------------------------------------------------------- |
| `.env`                   | Sí (copia de `.env.example`) | No           | Client ID, secret y nombre del canal                                    |
| `.env.example`           | No                           | Sí           | Plantilla vacía                                                         |
| `oauth_tokens.json`      | No                           | No           | Lo genera el script al autorizar Kick. No hace falta `auth-tokens.json` |
| `llaves.txt`             | No                           | No           | Ya no se usa                                                            |
| `assets/viewer_join.wav` | No                           | Sí           | Sonido de “nuevo espectador”                                            |
| `kick_viewers.py`        | No                           | Sí           | El monitor                                                              |


---



## Linux: sonido y notificaciones

Sonido (elige una):

```bash
sudo apt install pulseaudio-utils
# o
sudo apt install alsa-utils
# o
sudo apt install ffmpeg
```

Notificaciones:

```bash
sudo apt install libnotify-bin
```

---



## Problemas frecuentes

**“Falta KICK_CLIENT_ID en el archivo .env”**  
Copia `.env.example` a `.env` y rellena las tres variables obligatorias.

**El navegador abre Kick y luego falla el callback**  
El Redirect URI de la app tiene que ser exactamente `http://localhost:8079/callback`. Puerto, `http` (no `https`) y `/callback` tienen que coincidir.

**“No pude abrir el puerto 8079”**  
Cierra el otro programa que use ese puerto, o cambia el puerto en Kick Developer y en `KICK_REDIRECT_URI`.

**No suena nada**  
En Windows revisa el volumen de la app y de notificaciones. En Linux instala `paplay` o `aplay`. El archivo `assets/viewer_join.wav` debe existir.

**El chat no recibe el mensaje**  
Autoriza con la cuenta del canal. El cooldown evita un mensaje cada vez que alguien entra y sale en menos de 30 segundos.

**Error 401 / pide autorizar otra vez**  
Borra `oauth_tokens.json` y vuelve a lanzar el script.

---



## Privacidad

Este script llama a la API pública de Kick (`api.kick.com` e `id.kick.com`) con **tus** credenciales. El Client Secret, el access token y el refresh token se quedan en tu máquina (`.env` y `oauth_tokens.json`). No los compartas.

---

## Generar el `.exe` (mantenimiento)

En Windows, con el entorno virtual activado:

```powershell
pip install -r requirements.txt -r requirements-build.txt
pyinstaller --noconfirm kick_viewers.spec
```

El resultado queda en `dist/KickViewerMonitor/`. También se puede lanzar el flujo **Build Windows exe** en GitHub Actions.