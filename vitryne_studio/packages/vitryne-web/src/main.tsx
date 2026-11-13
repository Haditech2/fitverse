// SPDX-License-Identifier: AGPL-3.0-or-later
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "@tanstack/react-router";
import "@fontsource/dm-sans/latin-400.css";
import "@fontsource/dm-sans/latin-500.css";
import "@fontsource/dm-sans/latin-600.css";
import "@fontsource/bricolage-grotesque/latin-600.css";
import "@fontsource/bricolage-grotesque/latin-700.css";
import "./index.css";
import { router } from "./router";

const root = document.getElementById("root");
if (!root) throw new Error("index.html has no #root");
createRoot(root).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
);

const loader = document.getElementById("fitverse-loader");
if (loader) {
  let dismissed = false;
  const dismiss = () => {
    if (dismissed) return;
    dismissed = true;
    window.setTimeout(() => {
      loader.classList.add("is-ready");
      window.setTimeout(() => loader.remove(), 450);
    }, Math.max(0, 700 - performance.now()));
  };
  if (document.readyState === "complete") dismiss();
  else window.addEventListener("load", dismiss, { once: true });
  window.setTimeout(dismiss, 3200);
}
