# Changelog

## 4.4.1 — 2026-11-06

Release preparation based on the v4.4 main prototype.

- Added MIT license, Three.js notice, setup/configuration and troubleshooting documentation.
- Excluded original local TLS credentials and generated files.
- Added pinned dependency manifests and local certificate-generation helper.
- Replaced duplicated notebook implementation with a launcher for `server.py`.
- Added HTTPS browser pairing, session expiry, cross-origin write rejection and pairing rate limits.
- Disabled Brave certificate-error bypass by default.
- Made server startup explicit and import-safe; added a working owned-server shutdown path.
- Removed automatic termination of unrelated port owners.
- Added focused authentication/lifecycle tests and recorded validation limits.

The v5.1 tech demo and abandoned v6.0 experiment are not part of this release.
