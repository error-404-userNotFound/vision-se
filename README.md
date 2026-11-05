# Vision SE

Inspired by Apple's Vision Pro, but at a fraction of the cost. Turn your Mac desktop into a large, head-tracked virtual workspace in VR using only an iPhone and a cheap, Google Cardboard-style headset. Add a camera view of your surroundings, so you can see outside while in VR. Control the Mac's cursor with head movement, and use hand gestures to click and reposition the virtual screen.

This is an experimental local-network project. Setup is required on both the Mac and phone. See [release validation](docs/validation.md) for completed checks and the physical-device checks still to be performed.

## What you need

- **A Mac** to capture the desktop, run the Python server, and render the virtual scene.
- **An iPhone running Safari**, used in landscape, and a Cardboard-style phone headset. Keep the rear camera unobstructed if you want passthrough or gestures.
- **A trusted shared Wi-Fi network or hotspot.** The phone must be able to reach the Mac directly; guest networks with device isolation may prevent this.
- **Brave on the Mac**, the default browser for the host renderer. Other desktop browsers have not been validated.
- **CPython 3.12** and **mkcert** for local HTTPS certificates.

The intended platform is macOS with an iPhone/Safari viewer. Windows, Linux, and Android support has not been established. One Mac host page and one headset viewer are supported per server instance.

## Install and prepare

Clone this repository, then open its directory in a terminal:

```sh
git clone https://github.com/error-404-userNotFound/vision-se.git
cd vision-se
```

If you use Homebrew, install the setup tools:

```sh
brew install python@3.12 mkcert
```

Create a Python environment and install the full set of features, including gestures and notebook controls:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-notebook.txt
```

For a smaller installation, use `requirements-gestures.txt` for the terminal server with gestures, or `requirements.txt` for the terminal server without hand recognition. The gesture dependency is pinned to MediaPipe 0.10.21 because the code uses its Solutions API.

Before starting, complete these two setup steps:

1. **Set up HTTPS on both devices.** Find your Mac's LAN IPv4 address in System Settings → Wi-Fi → Details → TCP/IP. Replace the example address below with that address:

   ```sh
   export VR_HOST_IP=192.168.1.10
   mkcert -install
   .venv/bin/python scripts/setup_certs.py --host "$VR_HOST_IP"
   ```

   On the phone, install and trust the public `rootCA.pem` certificate from your local mkcert CA. Follow [the certificate and phone-trust instructions](docs/setup.md#3-create-and-trust-https-certificates). Never transfer the CA private key. Regenerate the server certificates if the Mac's IP changes.

2. **Grant macOS permissions.** In System Settings → Privacy & Security, allow **Screen Recording** for the app running Python and **Accessibility** for cursor movement/clicks. Restart that app if the permissions do not take effect. Allow incoming local connections if the firewall asks.

The [full setup guide](docs/setup.md) covers certificate trust, permissions, Python kernels, and configuration in more detail.

## Start and connect

### 1. Start on the Mac

From the repository directory, in the shell where you set `VR_HOST_IP`, run:

```sh
.venv/bin/python server.py
```

The terminal prints three URLs and a random **pairing code**. With the example address above and the default port, the URLs are:

| Page | Example URL | Open on |
|---|---|---|
| Host renderer | `https://192.168.1.10:8443/host` | Mac, in Brave |
| Headset viewer | `https://192.168.1.10:8443/` | iPhone, in Safari |
| Gesture debug view | `https://192.168.1.10:8443/gesture_host` | Mac, when troubleshooting |

Use the actual URLs printed by your server. The phone must use the Mac's network address; `localhost` on the phone refers to the phone itself.

### 2. Connect the Mac host page

The server attempts to open the host page in Brave automatically. If it does not, open the printed **Host view (Mac)** URL manually. Enter the pairing code when asked.

**Keep this page open and running.** It renders the virtual scene and sends the video stream to the phone. The Python server alone does not produce the headset view.

### 3. Connect the iPhone

Open the printed **Phone viewer** URL in Safari and enter the same pairing code. Pairing is required separately in each browser. Use the same IP/hostname throughout the session so the browser retains its pairing cookie.

Once the viewer connects:

1. Tap **Enable Motion** and allow motion/orientation access.
2. Rotate the phone to landscape.
3. Face the direction where you want the virtual screen and tap **Recenter**.
4. Adjust **Size**, **Dist**, **Curve radius**, and **Eye px** to suit your view and headset.
5. Try **Full Screen** if supported, then **Hide HUD** to hide the controls. Tap the gear icon to show them again.
6. Place the phone in the headset after granting the permissions and checking the picture.

Start with **Gaze Cursor** and **Pinch Click** off while adjusting the display. Then enable the input controls you want to use.

### Optional: use the notebook control panel

Instead of starting `server.py` in the terminal, run:

```sh
.venv/bin/python -m jupyterlab
```

Open `server.ipynb`, select the `.venv` Python kernel, and run the start cell. It prints the URLs and pairing code and displays the control panel. The device-connection steps are the same. The notebook also exposes quality presets and extra gesture settings.

Use one startup method at a time. To stop, press **Ctrl+C** in the terminal, or use **Quit Server** / the stop cell in the notebook. Restart the notebook kernel before starting a fresh session to reset its background workers and pairing.

## Use the controls

### Look around and adjust the screen

Head movement changes the view of the virtual screen. **Recenter** resets the forward reference; use it while looking straight ahead.

| Control | Effect |
|---|---|
| **Size** | Changes the virtual screen's size. |
| **Dist** | Moves the screen closer or farther away. |
| **Curve radius** | Adjusts the screen's curvature; a larger radius is flatter. |
| **Eye px** / **Converge** | Adjusts the split-eye presentation for your headset. |
| **Filter** | Selects simple orientation tracking or One-Euro smoothing. |
| **Screen opacity** | Adjusts the virtual-screen overlay opacity. |

If the view is slow or the devices run hot, use the notebook's **Preset** selector and **Apply Preset** button to choose a balanced or low-latency profile. The highest resolutions can be demanding.

### See your surroundings

On the phone, tap **Enable Camera** and grant camera access. **Cam On** controls whether the camera overlay is visible. Use **Lens**, **Opacity**, and **Blend** to adjust it.

The camera view is an approximate overlay, and its alignment depends on your phone and headset. Gestures can continue using the camera with the visible overlay off, as long as **Pinch Click** remains enabled.

### Move the Mac cursor with your head

Enable **Gaze Cursor**. Aim the center of your view at a point on the virtual desktop; the Mac cursor follows that direction. This uses phone orientation, not eye tracking.

Gaze Cursor controls movement. The pinch-click behavior described below uses camera-relative hand coordinates, so enabling both does not make a pinch click automatically select the gaze target. When learning gestures, leave Gaze Cursor off to make the targeting behavior easier to see.

### Click with a pinch

First install the gesture dependencies, tap **Enable Camera**, and enable **Pinch Click** on the phone. Keep your hand in view of the rear camera with good lighting. You can enable **Cam On** and **MP Overlay** to see the camera view and detected hand landmarks.

| Action | Gesture |
|---|---|
| **Left click** | Bring your thumb and index fingertip together, then separate them before the hold threshold. |
| **Right click / context menu** | Keep the thumb–index pinch held beyond the hold threshold, then separate them. The initial threshold is **1.75 seconds**. |
| **Move the click target** | Move the pinching hand within the camera image before releasing. Its position maps across the captured Mac monitor. |

**Clicks happen when the pinch ends.** The target comes from the latest detected midpoint between the thumb and index fingertip, mapped from the camera image to desktop coordinates. Keep the hand visible through release; losing detection can also end a pinch.

Either detected hand can supply the pinch. The right-click gesture is a longer pinch; you do not need to hold up two fingers or perform a double click.

Two phone controls affect timing:

- **Pinch hold threshold:** the duration separating a left click from a right click. Check its displayed value if you have changed settings.
- **Pinch inactive:** the cooldown after a successful click. The initial value is **700 ms**; a new pinch started during that cooldown is ignored.

### Move and resize the virtual screen with an open hand

With **Pinch Click** enabled, hand tracking also supports moving and scaling the virtual screen. **Drag Detect** in the notebook is enabled by default.

1. Show your **right hand** to the rear camera with all five fingers extended and clearly spread apart.
2. While holding that pose, move your hand across the camera view to reposition the virtual screen.
3. Move the spread hand closer to the camera to enlarge the screen, or farther away to shrink it. Scaling follows the hand's apparent size relative to when the pose began.
4. Bring the fingers together, close the hand, or move it out of view to stop tracking. The screen retains its last placement and size.

If the wrong hand activates screen movement, toggle **Swap Drag Hand** in the notebook; handedness labels can vary with camera orientation. Turn **Drag Detect** off if you want pinch clicks without accidentally moving the screen. **Drag Scale Gain** adjusts scaling sensitivity.

This gesture manipulates the virtual screen itself. It does not hold down the Mac mouse button or drag an individual macOS window.

## Troubleshooting

| Problem | First things to check |
|---|---|
| Phone cannot open the viewer | Same network, correct Mac IP/port, firewall permissions, and no Wi-Fi client isolation. |
| Certificate warning, camera unavailable, or motion unavailable | Trust the local CA on the phone and Mac, use HTTPS, and make sure the certificate includes the Mac's current IP. |
| No headset picture | Keep the Mac `/host` page running and pair both browsers. Try refreshing the host, then the viewer. |
| Desktop is black | Check macOS Screen Recording permission and the selected monitor. |
| Gestures do not respond | Check camera access, **Pinch Click**, lighting, hand visibility, and the gesture dependency installation. Open `/gesture_host` to inspect detection/status. |
| Cursor or clicks do nothing | Check macOS Accessibility permission for the app running Python. |
| Virtual screen moves unexpectedly | Close/lower the spread hand or disable **Drag Detect** in the notebook. |

See [detailed troubleshooting](docs/troubleshooting.md) and [configuration options](docs/setup.md#configuration-reference). `.env.example` lists environment variables; export them in your launch shell, since that file is not loaded automatically.

## How it works

The Mac captures the desktop with MSS and serves JPEG frames locally. The Three.js host page places those frames on a virtual screen, renders the scene, and streams it to the phone using WebRTC. The phone sends orientation back over a data channel. When gestures are enabled, camera frames are uploaded to the Mac for MediaPipe analysis; PyAutoGUI applies desktop cursor movements and clicks.

GitHub hosts the source code. Run the application on your own Mac and connect the phone to that Mac.

## Privacy and access

Use the application on a trusted local network. Every paired browser can access the shared desktop and control APIs. Pairing sessions expire after 12 hours; restarting the Python process resets the pairing code and invalidates existing sessions.

Keep local certificates, private keys, pairing codes, and personal captures out of Git. Do not expose the server through port forwarding or a public tunnel. See [SECURITY.md](SECURITY.md) for the security scope.

## Contributing and license

See [CONTRIBUTING.md](CONTRIBUTING.md) for development and bug-reporting guidance. Vision SE is [MIT licensed](LICENSE). Bundled Three.js retains its own MIT notice; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
