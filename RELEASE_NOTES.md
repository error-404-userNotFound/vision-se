# Vision SE v4.4.1

This release packages the v4.4 main phone-based VR desktop prototype for sharing. It adds an MIT license, reproducible dependency manifests, HTTPS setup instructions, per-run browser pairing, safer startup/shutdown, and contributor/security documentation.

The main VR screen, camera overlay, head cursor and MediaPipe gesture implementation come from v4.4. The v5.1 virtual-window tech demo and abandoned v6.0 controller experiment are excluded.

Start with README.md and docs/setup.md. Each user must generate and trust their own local TLS certificates; original developer keys are not distributed. Python 3.12 is the supported setup target.

Validation includes automated authentication/lifecycle tests, a verified loopback HTTPS connection, dependency installation and import checks. Phone/headset behavior remains subject to the device checklist in docs/validation.md. Treat this as a prototype release, not a fully device-certified product.
