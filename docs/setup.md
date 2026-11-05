# Setup on macOS and iPhone

## 1. Tools and Python

Install Git, Brave, and CPython 3.12. If you use Homebrew:

```sh
brew install python@3.12 mkcert
```

From the repository directory:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-notebook.txt
```

Choose one requirements file: `requirements.txt` for the terminal server without hand recognition; `requirements-gestures.txt` for terminal plus gestures; `requirements-notebook.txt` for gestures and JupyterLab/ipywidgets. The latter files include the earlier ones. The core server works without MediaPipe or notebook widgets. PyTurboJPEG is an optional accelerator and is not needed; OpenCV encoding is the default fallback.

For a complete snapshot of the validated macOS Python 3.12 environment, use `requirements-lock-macos-py312.txt` when available. It includes transitive packages and is platform-specific.

## 2. Find the Mac's address

Connect the Mac and phone to the same trusted Wi-Fi or hotspot. Find the Mac's IPv4 address in System Settings → Wi-Fi → Details → TCP/IP. Avoid guest networks that isolate devices. Export it in the shell used to launch the server:

```sh
export VR_HOST_IP=192.168.1.10
```

The address above is an example. Set your own address. Regenerate certificates when that address changes.

## 3. Create and trust HTTPS certificates

Phone camera and motion APIs require a secure browser context. Use your own locally trusted certificates rather than the original developer's keys.

```sh
mkcert -install
.venv/bin/python scripts/setup_certs.py --host "$VR_HOST_IP"
mkcert -CAROOT
```

`mkcert -install` adds a local CA to the Mac trust store and may ask for your macOS password. The helper creates `certs/localhost.pem` and `certs/localhost-key.pem`, which Git ignores. It does not change the system trust store itself.

From the CA directory printed by `mkcert -CAROOT`, transfer **only `rootCA.pem`** to your own phone, for example using AirDrop. Install the downloaded certificate profile in Settings, then enable full trust for that CA under Settings → General → About → Certificate Trust Settings. Exact wording varies by iOS version. Never transfer or publish `rootCA-key.pem` or any other private key.

Trust the CA only on devices you own or administer; remove the profile and trust when you no longer need it. See the [upstream mkcert mobile-device instructions](https://github.com/FiloSottile/mkcert#mobile-devices).

## 4. Grant Mac permissions

Allow Screen Recording (called Screen & System Audio Recording in some macOS versions) for the terminal, notebook host or other app running Python. Allow Accessibility for cursor movement/clicks. These are under System Settings → Privacy & Security. Restart that host app if permission changes do not take effect. Allow incoming local connections if the macOS firewall asks.

## 5. Start the server

```sh
.venv/bin/python server.py
```

The default port is 8443. The server opens the Mac host page in Brave when Brave is available. Otherwise manually open the printed `/host` URL in the desktop browser. Keep that page running; it renders the VR stream.

Open the printed viewer URL in Safari on the phone. Pair both browser sessions using the random code printed in the terminal. The code resets on a Python-process restart; sessions expire after 12 hours. The phone must use the same hostname/IP for pairing and viewing because cookies are scoped to the host.

Tap Enable Motion on the phone and accept access. Turn the phone to landscape. Enable Camera if using passthrough or gestures. Recenter while facing the direction you want the screen to occupy. Start with gestures and cursor disabled, check the picture and tracking, then enable the input mode you want.

## 6. Notebook controls

```sh
.venv/bin/python -m jupyterlab
```

Open `server.ipynb` and choose the `.venv` kernel. If Jupyter does not offer it, register a project kernel:

```sh
.venv/bin/python -m ipykernel install --user --name vision-se --display-name 'Vision SE (.venv)'
```

Run the start cell. Use Quit Server or the stop cell to stop serving. Restart the kernel before a fresh session to stop all old monitoring/UI workers. Do not run the terminal server at the same time.

## Configuration reference

Variables are read when `server.py` is imported. Restart the process/kernel after changing them.

| Variable | Default | Purpose |
|---|---|---|
| `VR_HOST_IP` | detected LAN address | Address printed in device URLs; must match the certificate |
| `VR_PORT` | `8443` | HTTPS port |
| `VR_BIND_HOST` | `0.0.0.0` | Listen interface; use `127.0.0.1` for Mac-only checks |
| `VR_MONITOR_INDEX` | `1` | MSS monitor index; 1 is the first monitor |
| `VR_CERT_FILE` | `certs/localhost.pem` | TLS certificate path |
| `VR_KEY_FILE` | `certs/localhost-key.pem` | TLS private-key path |
| `VR_OPEN_BROWSER` | `1` | Set to 0 to launch the host browser yourself |
| `VR_BRAVE_PATH` | standard Mac installation paths | Brave executable override |
| `VR_BRAVE_IGNORE_CERT_ERRORS` | `0` | Development-only bypass; prefer trusted certificates |

Changes to size, distance, curvature, camera, smoothing and quality are available in the viewer/notebook controls. Settings live in memory and reset at process restart.
