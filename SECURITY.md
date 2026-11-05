# Security scope

Vision SE shares a live desktop and can move/click the Mac's mouse. It is a trusted-local-network prototype, not an internet-facing remote desktop service. Do not port-forward it or expose it through a public tunnel.

Version 4.4.1 requires a random per-process pairing code for all application and static routes except the pairing form. Paired browsers get signed, Secure, HttpOnly, SameSite=Strict cookies that expire after 12 hours. Pairing is rate limited in memory. Browser cross-origin write requests are rejected. Restarting Python invalidates the code and all existing sessions. There are no separate viewer/admin roles: every paired device is trusted to access the application APIs.

HTTPS encrypts HTTP traffic; WebRTC carries media and orientation over encrypted browser transports. Phone camera frames are sent to the Mac when hand gestures are enabled. The application does not intentionally save camera frames or desktop captures to disk. Browser/OS behavior and any manual debugging are outside that statement.

The server listens on local network interfaces by default so the phone can connect. Use `VR_BIND_HOST=127.0.0.1` for Mac-only checks. Pairing does not protect against a compromised paired device, compromised host, denial of service, or an untrusted network administrator. Input toggles default to off; a paired device can change them.

Generate your own local TLS certificates and keep private keys outside Git. Never upload a mkcert CA private key. Certificate validation is enabled by default. The development-only `VR_BRAVE_IGNORE_CERT_ERRORS` override weakens that protection.

Before public publication, use GitHub's private vulnerability reporting if enabled. While the repository is private, report security problems directly to its owner rather than posting credentials or exploit details in a public issue. This project has no promised response SLA.
