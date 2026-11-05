# Release validation — 2026-11-06

## Completed

- Installed the full notebook/gesture requirements in a fresh CPython 3.12.11 virtual environment on macOS arm64.
- `uv pip check` reported all installed dependencies compatible (132 packages).
- Saved a transitive dependency snapshot in `requirements-lock-macos-py312.txt`.
- Initialized MediaPipe Hands and processed a synthetic blank image successfully with macOS graphics access (no camera or input automation).
- Imported the server, MediaPipe Solutions API and PyAutoGUI successfully. Importing the server did not launch the service/browser or start desktop capture.
- Passed 16 unittest cases covering pairing, unauthorized screen/API/static access, secure cookie attributes, cross-origin writes, brute-force throttling, process-session invalidation, redirect restrictions, input gating, upload limits and server lifecycle.
- The lifecycle test generated temporary test-only certificates, served `/pair` over a real loopback HTTPS connection with certificate verification, and stopped the owned server cleanly. Hardware monitoring/gesture workers were stubbed for that test.
- Python compilation and JavaScript module syntax checks passed.
- Validated the launcher's notebook schema and removed outputs.
- Compared both bundled Three.js JavaScript files' Git blob hashes with upstream r174: exact matches. Added the matching upstream license.

The local `.venv/` and `.python/` runtime are ignored and are not part of the repository. Users install their own Python environment following setup.md.

## Physical-device checks still required

These checks need the owner's actual Mac/phone/headset. They have not been established by automated tests in this preparation session.

- [ ] Run the documented certificate generation and phone CA-trust steps on the intended devices.
- [ ] Confirm real desktop capture after granting Screen Recording permission.
- [ ] Pair the Mac host and iPhone viewer and verify the WebRTC picture.
- [ ] Confirm motion permission, head tracking, recentering and split-eye presentation in Safari.
- [ ] Confirm camera permission, rear-lens selection and passthrough alignment.
- [ ] Confirm cursor movement and gesture left/right clicks after granting Accessibility permission.
- [ ] Confirm hand-spread drag detection and its visible behavior.
- [ ] Compare quality presets for latency, heat and readability on the actual network.
- [ ] Confirm phone disconnect behavior and clean stop/restart from terminal and notebook.

Record hardware models and exact OS/browser versions when completing these checks. No current device compatibility claim is inferred from file timestamps or the original prototype's prior use.
