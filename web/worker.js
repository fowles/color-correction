// SPDX-License-Identifier: MIT
//
// Runs the package's real correct.py inside Pyodide, off the main thread.
// A module worker: Pyodide 314 refuses to boot in a classic one.
//
// Protocol (main -> worker):  {type: "correct", id, width, height, buffer}
// Protocol (worker -> main):  {type: "status", text}
//                             {type: "ready", menu}
//                             {type: "result", id, name, ms, buffer}
//                             {type: "error", id?, name?, text}
//                             {type: "done", id}

import { loadPyodide } from "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/pyodide.mjs";

// Must cover every module-level third-party import of correct.py:
// tests/test_repo_contracts.py checks it.
const PACKAGES = ["numpy", "opencv-python"];
// Relative to this file, so the page must be served from the repo root.
const SOURCES = {
  "underwater_color/correct.py": "../underwater_color/correct.py",
  "glue.py": "glue.py",
};

let glue = null;
let latestId = 0;

const status = (text) => postMessage({ type: "status", text });

async function boot() {
  status("Loading Python…");
  const pyodide = await loadPyodide();
  status("Loading numpy and OpenCV…");
  await pyodide.loadPackage(PACKAGES);
  status("Loading corrections…");
  pyodide.FS.mkdirTree("underwater_color");
  pyodide.FS.writeFile("underwater_color/__init__.py", "");
  for (const [dest, url] of Object.entries(SOURCES)) {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`fetching ${url}: HTTP ${resp.status}`);
    pyodide.FS.writeFile(dest, await resp.text());
  }
  glue = pyodide.pyimport("glue");
  const menu = glue.menu().toJs({ dict_converter: Object.fromEntries });
  postMessage({ type: "ready", menu });
  return pyodide;
}

const booted = boot().catch((e) => {
  postMessage({ type: "error", text: `Startup failed: ${e.message ?? e}` });
  throw e;
});

// Yield to the event loop so a newer image's message can arrive and
// supersede the batch in flight.
const yieldToEvents = () => new Promise((r) => setTimeout(r, 0));

onmessage = async ({ data }) => {
  if (data.type !== "correct") return;
  const { id, width, height } = data;
  latestId = id;
  const pyodide = await booted;
  const methods = glue.menu().toJs({ dict_converter: Object.fromEntries });
  const bytes = pyodide.toPy(new Uint8Array(data.buffer));
  const rgb = glue.rgb_from_rgba(bytes, width, height);
  bytes.destroy();
  try {
    for (const { name } of methods) {
      await yieldToEvents();
      if (id !== latestId) return;
      const t0 = performance.now();
      try {
        const out = glue.correct(name, rgb);
        const buffer = out.toJs().buffer;
        out.destroy();
        postMessage(
          { type: "result", id, name, ms: performance.now() - t0, buffer },
          [buffer],
        );
      } catch (e) {
        postMessage({ type: "error", id, name, text: String(e.message ?? e) });
      }
    }
    postMessage({ type: "done", id });
  } finally {
    rgb.destroy();
  }
};
