import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { Pano } from "./Pano";
import "../index.css";

const kok = document.getElementById("kok");
if (!kok) throw new Error("#kok bulunamadı");

createRoot(kok).render(
  <StrictMode>
    <BrowserRouter>
      <Pano />
    </BrowserRouter>
  </StrictMode>,
);
