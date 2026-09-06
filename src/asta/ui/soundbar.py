"""Soundbar: i tormentoni da far partire durante l'asta.

Vive nella barra laterale, aperta e chiusa dalla freccia in alto a sinistra:
e' a portata di mano da qualsiasi pagina, e chiusa non occupa niente.

Gli audio sono file dentro ``static/audio/``, divisi per cartella: ``calcio``
per calciatori e allenatori, ``amici`` per le voci del gruppo. Il titolo del
pulsante si ricava dal nome del file - trattini al posto degli spazi - quindi
per aggiungere un tormentone basta lasciare il file nella cartella giusta.

La pagina e' un componente HTML: i pulsanti suonano **nel browser**, senza
passare dal server. E' l'unico modo perche' partano subito e perche' funzionino
sul telefono, dove la riproduzione automatica dopo un giro di rete verrebbe
bloccata. I file si scaricano solo quando si preme il pulsante, uno alla volta:
in una stanza con la rete dati non si scarica 1,6 MB per guardare l'asta.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from html import escape
from pathlib import Path
from urllib.parse import quote

import streamlit as st

#: Cartella degli audio, servita da Streamlit sotto ``app/static/``.
AUDIO_DIR = Path(__file__).resolve().parents[3] / "static" / "audio"

#: Formati che i browser sanno suonare senza plugin.
SUPPORTED = (".mp3", ".m4a", ".wav", ".ogg", ".opus")

#: Cartella -> titolo della sezione. In tutte e due la prima parola del nome
#: del file e' chi parla ("allegri-buona-giornata", "carlo-passa-la-palla"), e
#: finisce sul pulsante come etichetta verde sopra la frase.
SEZIONI: tuple[tuple[str, str], ...] = (
    ("calcio", "⚽ Calciatori e allenatori"),
    ("amici", "🎙️ Amici"),
)


@dataclass(frozen=True, slots=True)
class Sound:
    """Un audio della soundbar."""

    url: str
    """Percorso da cui il browser lo scarica, relativo alla pagina."""
    title: str
    """Frase, formattata per il pulsante."""
    speaker: str | None
    """Chi la dice, quando il nome del file lo indica."""

    @property
    def label(self) -> str:
        """Etichetta completa del pulsante."""
        return f"{self.speaker}: {self.title}" if self.speaker else self.title


def format_title(stem: str) -> tuple[str | None, str]:
    """Ricava chi parla e la frase dal nome del file.

    La prima parola e' il nome di chi parla, il resto la frase. Con una parola
    sola non c'e' nessun nome da mostrare e diventa tutta titolo: e' il modo
    per avere un pulsante senza etichetta verde.

    Args:
        stem: nome del file senza estensione, con i trattini al posto degli
            spazi (``allegri-buona-giornata``).

    Returns:
        ``(chi parla, frase)``; il primo elemento e' ``None`` quando non c'e'.
    """
    parole = [p for p in stem.replace("_", "-").split("-") if p]
    if not parole:
        return None, stem
    if len(parole) > 1:
        return parole[0].capitalize(), _frase(parole[1:])
    return None, _frase(parole)


def _frase(parole: list[str]) -> str:
    """Parole unite in una frase con la sola iniziale maiuscola.

    Non si tocca il resto: mettere l'iniziale a ogni parola trasformerebbe
    "carlo passa la palla" in un titolo di giornale.
    """
    testo = " ".join(parole)
    return testo[:1].upper() + testo[1:]


def load_sounds(base: Path | None = None) -> list[tuple[str, tuple[Sound, ...]]]:
    """Legge gli audio dalle cartelle, sezione per sezione.

    Le sezioni senza file non vengono restituite: una sezione vuota sulla
    pagina sarebbe solo un titolo appeso al nulla.
    """
    radice = base or AUDIO_DIR
    sezioni: list[tuple[str, tuple[Sound, ...]]] = []
    for cartella, titolo in SEZIONI:
        percorso = radice / cartella
        if not percorso.is_dir():
            continue
        trovati = sorted(
            (f for f in percorso.iterdir() if f.suffix.lower() in SUPPORTED),
            key=lambda f: f.name.lower(),
        )
        suoni = []
        for file in trovati:
            speaker, title = format_title(file.stem)
            suoni.append(
                Sound(
                    url=f"app/static/audio/{quote(cartella)}/{quote(file.name)}",
                    title=title,
                    speaker=speaker,
                )
            )
        if suoni:
            sezioni.append((titolo, tuple(suoni)))
    return sezioni


_CSS = """
*{box-sizing:border-box}
body{margin:0;background:transparent;color:#fafafa;
  font-family:"Source Sans Pro",system-ui,-apple-system,sans-serif}
.sb-dado{width:100%;padding:11px;margin-bottom:12px;border-radius:10px;cursor:pointer;
  border:1px solid rgba(74,222,128,.5);background:rgba(74,222,128,.14);color:#4ade80;
  font-size:15px;font-weight:800;letter-spacing:.02em}
.sb-dado:hover{background:rgba(74,222,128,.22)}
.sb-titolo{font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;
  opacity:.6;margin:14px 0 6px}
/* Una colonna nella barra laterale, due o piu' se qualcuno la allarga. */
.sb-griglia{display:grid;gap:6px;grid-template-columns:repeat(auto-fill,minmax(150px,1fr))}
.sb-btn{display:flex;flex-direction:column;gap:1px;text-align:left;padding:8px 10px;
  border-radius:9px;cursor:pointer;border:1px solid rgba(128,128,128,.35);
  background:rgba(255,255,255,.04);color:inherit;font-family:inherit;min-height:44px;
  justify-content:center;transition:background .12s,border-color .12s}
.sb-btn:hover{background:rgba(255,255,255,.09)}
.sb-btn.on{border-color:#4ade80;background:rgba(74,222,128,.16);
  box-shadow:0 0 0 2px rgba(74,222,128,.28)}
.sb-chi{font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:.06em;
  color:#4ade80}
.sb-frase{font-size:13.5px;font-weight:600;line-height:1.25}
.sb-vuoto{opacity:.6;font-size:14px}
"""

_JS = """
const SUONI = __SUONI__;
// Un solo lettore: far partire un audio ferma automaticamente il precedente,
// che e' quello che serve quando si preme un pulsante dopo l'altro.
const lettore = new Audio();
let acceso = null;

// Su Streamlit Cloud l'app non sta sulla radice del dominio: il prefisso si
// ricava dalla pagina che ospita il componente.
const base = (() => {
  try {
    const p = window.parent.location.pathname;
    return p.slice(0, p.lastIndexOf("/") + 1);
  } catch (e) {
    return "";
  }
})();

function spegni() {
  if (acceso !== null) {
    const b = document.querySelector(`[data-i="${acceso}"]`);
    if (b) b.classList.remove("on");
    acceso = null;
  }
}

function suona(i) {
  const era = acceso;
  lettore.pause();
  spegni();
  if (era === i) return;  // secondo clic sullo stesso pulsante: si ferma
  lettore.src = base + SUONI[i].url;
  lettore.currentTime = 0;
  lettore.play().catch(() => {});
  acceso = i;
  const b = document.querySelector(`[data-i="${i}"]`);
  if (b) {
    b.classList.add("on");
    b.scrollIntoView({block: "nearest", behavior: "smooth"});
  }
}

lettore.addEventListener("ended", spegni);
document.querySelectorAll("[data-i]").forEach((b) => {
  b.addEventListener("click", () => suona(Number(b.dataset.i)));
});
const dado = document.getElementById("sb-dado");
if (dado) {
  dado.addEventListener("click", () => {
    if (SUONI.length === 0) return;
    let i = Math.floor(Math.random() * SUONI.length);
    if (SUONI.length > 1 && i === acceso) i = (i + 1) % SUONI.length;
    suona(i);
  });
}

// Si misura il contenitore, non il documento: l'altezza del documento non
// scende mai sotto quella dell'iframe, quindi ogni ritocco ne chiederebbe uno
// piu' grande e la pagina crescerebbe all'infinito.
"""


def soundbar_html(sezioni: list[tuple[str, tuple[Sound, ...]]]) -> str:
    """HTML completo della soundbar: pulsanti, stile e script.

    Funzione pura, cosi' si puo' verificare senza avviare Streamlit.
    """
    suoni: list[Sound] = [s for _, gruppo in sezioni for s in gruppo]
    if not suoni:
        return f"<style>{_CSS}</style><p class='sb-vuoto'>Nessun audio disponibile.</p>"

    indice = {id(s): i for i, s in enumerate(suoni)}
    pezzi = [
        "<button class='sb-dado' id='sb-dado'>🎲 Uno a caso</button>",
    ]
    for titolo, gruppo in sezioni:
        pezzi.append(f"<div class='sb-titolo'>{escape(titolo)}</div><div class='sb-griglia'>")
        for suono in gruppo:
            chi = f"<span class='sb-chi'>{escape(suono.speaker)}</span>" if suono.speaker else ""
            pezzi.append(
                f"<button class='sb-btn' data-i='{indice[id(suono)]}' "
                f"title='{escape(suono.label)}'>{chi}"
                f"<span class='sb-frase'>{escape(suono.title)}</span></button>"
            )
        pezzi.append("</div>")

    dati = json.dumps([{"url": s.url} for s in suoni], ensure_ascii=False)
    # "</script>" dentro i dati chiuderebbe il blocco in anticipo.
    dati = dati.replace("<", "\u003c")
    script = _JS.replace("__SUONI__", dati)
    return f"<style>{_CSS}</style><div class='sb'>{''.join(pezzi)}</div><script>{script}</script>"


def render_sidebar() -> None:
    """Disegna la soundbar nella barra laterale, su tutte le pagine.

    Sta li' e non su una pagina sua perche' il tormentone si fa partire
    *mentre* si guarda il tabellone o si cerca un calciatore: cambiare pagina
    per premere un pulsante e poi tornare indietro non lo farebbe partire mai.
    La barra parte chiusa (``initial_sidebar_state`` in ``app.py``) e si apre
    con la freccia, quindi chi non la usa non se la trova fra i piedi.
    """
    with st.sidebar:
        st.subheader("🔊 Soundbar")
        sezioni = load_sounds()
        if not sezioni:
            st.info("Nessun audio in `static/audio/`.")
            return
        st.caption("Un tocco per far partire, un altro per fermare.")
        # height="content": e' Streamlit a misurare il contenuto dell'iframe e
        # a dargli l'altezza giusta, anche quando la griglia cambia colonne.
        st.iframe(soundbar_html(sezioni), height="content")
