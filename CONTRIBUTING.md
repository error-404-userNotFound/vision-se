# Contributing

This repository contains the v4.4 main prototype and its v4.4.1 release preparation. The v5.1 window demo and abandoned v6.0 controller are outside its scope.

Describe the behavior you want to change before a large refactor. Keep changes focused and include steps to reproduce bugs. Report hardware, OS/browser and Python versions; redact private content and pairing codes.

Use Python 3.12 and the pinned requirements. Run:

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q server.py security.py scripts tests
```

With Node.js installed, syntax-check JavaScript using:

```sh
node --input-type=module --check < static/js/host.js
node --input-type=module --check < static/js/viewer.js
node --input-type=module --check < static/js/gesture_host.js
```

For UI/stream/gesture changes, also perform the device checks in `docs/validation.md`. Automated tests cannot establish real camera/headset behavior. Clear notebook outputs before committing and review `git diff --cached` for local data. Never commit certificate/private-key files.

Contributions are offered under the project's MIT license; keep upstream notices intact.
