# Third-party notices

## Bundled Three.js

`static/vendor/three/build/three.module.js` and `three.core.js` identify themselves as Three.js revision 174 (r174), copyright 2010–2025 Three.js Authors, SPDX MIT. The corresponding upstream license is included in `static/vendor/three/LICENSE`.

Source: https://github.com/mrdoob/three.js/tree/r174

The bundled JavaScript is retained from the original v4.4 snapshot. A byte-for-byte comparison with the upstream distribution is recorded in `docs/validation.md` when performed.

## Installed dependencies

Python dependencies are installed separately through the requirements files; their source, notices and any bundled model assets remain subject to their respective upstream licenses. In particular, MediaPipe is a separate Google project and this release uses its packaged hand-tracking implementation. Optional PyTurboJPEG/libjpeg-turbo are not distributed here.

This project's MIT license applies to the project's own code and documentation and does not replace third-party licenses.
