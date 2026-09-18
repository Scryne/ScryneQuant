import { Navigate, Route, Routes } from "react-router-dom";
import { Kosular } from "./Kosular";
import { Kosu } from "./Kosu";

/** Gözlem panosu: **bütün** koşuları gösteren salt okunur konsol.
 *
 *  Koşu panosundan (`App.tsx`) ayrı bir uygulama, çünkü kaynağı da ayrı: o pano koşunun
 *  kendi sürecinden beslenir ve tek koşu tanır; bu pano dışarıdan, koşu dosyalarının
 *  anlık kopyasından okur ve hiçbirini değiştirmez.
 */
export function Pano() {
  return (
    <div className="min-h-dvh">
      <a href="#icerik" className="atla">
        İçeriğe atla
      </a>
      <header className="border-b border-border bg-surface-sunken">
        <div className="mx-auto flex max-w-[80rem] flex-wrap items-baseline justify-between gap-md px-lg py-md">
          <span className="text-h1 font-semibold tracking-tight text-primary">
            ScryneQuant <span className="text-tertiary">· gözlem panosu</span>
          </span>
          <span className="text-label text-tertiary">
            Salt okunur — bu ekran hiçbir koşuyu değiştiremez
          </span>
        </div>
      </header>
      <main id="icerik" className="mx-auto max-w-[80rem] p-lg lg:p-xl">
        <Routes>
          <Route path="/" element={<Kosular />} />
          <Route path="/kosu/:ad" element={<Kosu />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
