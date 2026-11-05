# Troubleshooting

| Symptom | Check |
|---|---|
| Server says TLS files are missing | Run certificate setup; check `VR_CERT_FILE` and `VR_KEY_FILE`. |
| Certificate warning or unavailable camera/motion | Confirm CA trust on both devices, use HTTPS, and confirm the URL's IP is included in the generated certificate. Restart the browser after changing trust. |
| Phone cannot reach the URL | Check Mac IP, port, firewall and shared network; guest Wi-Fi/client isolation can block access. |
| Pairing code rejected | Use the code from the current process, without spaces. Restarting Python invalidates previous codes and sessions. After repeated failures wait a minute. |
| Unauthorized response after pairing | Use the same IP/hostname; accept cookies. A different hostname or expired session requires pairing again. |
| Black shared desktop | Grant Screen Recording to the app running Python, restart that app, and check `VR_MONITOR_INDEX`. Protected content may not be capturable. |
| No VR stream | Keep `/host` running on the Mac; pair it as well as the phone. Refresh the host then viewer. Only one viewer is supported. |
| Motion does nothing | Tap Enable Motion from a user gesture and accept Safari permission. Check HTTPS trust. |
| No passthrough / no hands | Enable camera and choose the appropriate lens. Install `requirements-gestures.txt` for recognition. Check `/gesture_host` and notebook logs. Use good light and visible hands. |
| MediaPipe cannot create an OpenGL pixel format | Run from a normal logged-in Mac desktop session with graphics access. Headless/restricted execution may fail; inspect gesture status logs. |
| `mediapipe` has no `solutions` | Use CPython 3.12 and the pinned MediaPipe 0.10.21. Avoid a newer Tasks-only release. |
| Cursor/clicks have no effect | Grant macOS Accessibility to the Python host app. Check the cursor/gesture toggle. |
| High lag or heat | Choose balanced or low latency quality; lower camera/gesture upload FPS; use a reliable local network. Default v4.4 resolutions are demanding. |
| Port already in use | Stop your previous server/kernel or choose `VR_PORT`. The application does not kill unrelated processes. |
| Notebook behaves oddly after stop/start | Restart its kernel, then run the start cell once. |

For reports, include Python/package versions, macOS/iOS and browser versions, launch method, steps, and redacted logs. Remove pairing codes, private keys, screenshots of personal content and unrelated local paths.
