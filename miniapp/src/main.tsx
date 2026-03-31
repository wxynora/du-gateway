import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./ui/App";
import { tgBootstrapEarly } from "./ui/tg";
import "./styles.css";

tgBootstrapEarly();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

