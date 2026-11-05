# Vision SE

Turn a Mac desktop into a head-tracked virtual screen on a phone in a Cardboard-style headset. Optional camera passthrough and MediaPipe hand gestures let you see your surroundings and interact with the Mac.

**Version 4.4.1 — a local-network research prototype based on the main v4.4 version.** It requires setup on both the Mac and phone. Hardware behavior is still being revalidated after a long development pause; see [validation](docs/validation.md) for what has actually been checked.

## Features

- A virtual desktop screen with size, distance and curvature controls.
- Phone orientation tracking with adjustable filtering and recentering.
- Split-eye phone display and camera overlay with adjustable opacity.
- Head-directed Mac cursor control.
- Optional hand tracking: pinch release for a left click, longer pinch for a right click, plus hand-spread drag detection.
- Notebook control panel, gesture debug view, and rendering/streaming quality presets.
- Per-run browser pairing over HTTPS.

## Requirements

The intended setup is a macOS host, a phone running Safari in landscape, a Cardboard-style phone headset, and a shared trusted Wi-Fi network or hotspot. Brave is the default desktop renderer. Other host browsers may work but are not validated. This release does not claim Windows/Linux or Android support.

Use **CPython 3.12**. The optional gesture implementation uses MediaPipe's legacy Solutions API and is pinned to 0.10.21. Do not replace it with the newest MediaPipe without checking API compatibility.

## Get started

Follow [the setup guide](docs/setup.md) for Python installation, local HTTPS certificates, phone certificate trust, and macOS permissions. Once those are ready:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-notebook.txt
.venv/bin/python scripts/setup_certs.py --host YOUR_MAC_LAN_IP
export VR_HOST_IP=YOUR_MAC_LAN_IP
.venv/bin/python server.py
```

Replace `YOUR_MAC_LAN_IP` with your Mac's actual IPv4 address. Run `mkcert -install` before generating certificates; install and trust the public CA certificate on the phone as described in the setup guide.

The terminal prints host/viewer URLs and a pairing code. Open `/host` on the Mac and `/` on the phone, and enter the code in both browsers. Pairing grants desktop access; share it only with the devices you want to use. Allow motion and camera when needed, select landscape, and recenter while looking forward.

For the notebook interface, run `.venv/bin/python -m jupyterlab`, open `server.ipynb`, select the `.venv` kernel, and run its start cell. Use one startup method at a time. Stop the terminal server with Ctrl+C or use the notebook stop cell. Restart the notebook kernel after stopping to fully reset background workers and pairing.

## How it works

The Mac captures its desktop using MSS and serves JPEG frames locally. A Three.js host page maps these frames onto a virtual screen, renders the scene, and streams it to the phone using WebRTC. Phone orientation travels back over a data channel. When gestures are enabled, selected phone camera frames are uploaded to the Mac for MediaPipe analysis. PyAutoGUI applies cursor movements and clicks.

The Flask HTTPS server supplies the pages, settings and WebRTC signaling. One host and one headset viewer are supported per server instance. This is a local desktop program; GitHub hosts the source, not the running VR session.

## Configuration and troubleshooting

See [setup and configuration](docs/setup.md), [troubleshooting](docs/troubleshooting.md), and [security scope](SECURITY.md). `.env.example` lists supported variables; export them in your shell. It is not loaded automatically.

The default quality targets are inherited from v4.4 and can be expensive. Start with the balanced or low-latency preset if performance is poor. Phone/headset optics and camera overlays are approximate and require adjustment.

## Project history

- v3.8–v4.4: main prototype development; v4.4 is the basis of this release.
- v4.4.1: packaging, setup documentation, pairing, safer startup and license preparation.
- v5.1: separate experimental virtual-window tech demo; not included here.
- v6.0: abandoned controller experiment; not included here.

This is a snapshot import of an existing project. Historical numbered folders have not been represented as fabricated Git commits.

## Contributing and license

See [CONTRIBUTING.md](CONTRIBUTING.md). The project is MIT licensed; bundled Three.js retains its own MIT notice. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
