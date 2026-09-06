"""Entrypoint dell'app Streamlit.

Avvio locale::

    streamlit run app.py

L'app espone cinque pagine pubbliche — **Tabellone**, **Listone**,
**Aggiudicazioni**, **Formazioni** e **Portieri** — da condividere con i
partecipanti, piu' **Gestione asta**, protetta da password, da cui si conduce
l'asta. La **Soundbar** non e' una pagina: sta nella barra laterale, quindi
si apre da qualsiasi pagina senza perdere di vista l'asta.
"""

from __future__ import annotations

import sys
from pathlib import Path

# I moduli vivono in src/: cosi' l'app parte senza doversi installare come
# pacchetto, anche su Streamlit Community Cloud. La radice serve a sua volta,
# perche' il caricamento del listone importa ``scripts.build_players``: di
# norma Streamlit ce la mette da sola, ma dipende da come viene avviata e
# scoprirlo in produzione costerebbe caro.
RADICE = Path(__file__).resolve().parent
for cartella in (RADICE / "src", RADICE):
    if str(cartella) not in sys.path:
        sys.path.insert(0, str(cartella))

import streamlit as st  # noqa: E402

st.set_page_config(
    page_title="Asta Fantacalcio",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from asta.ui import admin, soundbar, viewer  # noqa: E402

# Le pagine pubbliche le vede chiunque abbia il link; Gestione asta e'
# elencata per tutti ma chiede la password.
pages = [
    # La pagina di default vive sulla radice: darle un url_path prometterebbe
    # una rotta che poi risponde "page not found".
    st.Page(viewer.board_page, title="Tabellone", icon="🏆", default=True),
    st.Page(viewer.listone_page, title="Listone", icon="🔎", url_path="listone"),
    st.Page(viewer.formations_page, title="Formazioni", icon="📋", url_path="formazioni"),
    st.Page(viewer.keepers_page, title="Portieri", icon="🧤", url_path="portieri"),
    # Le aggiudicazioni si guardano a cose fatte, non mentre si chiama: stanno
    # in fondo, appena prima dell'area riservata.
    st.Page(viewer.sales_page, title="Aggiudicazioni", icon="📜", url_path="aggiudicazioni"),
    # Il percorso resta ``/admin``: e' il link che sta nei segnalibri, e
    # cambiarlo romperebbe quello che si e' gia' salvato chi conduce.
    st.Page(admin.render, title="Gestione asta", icon="🎛️", url_path="admin"),
]

# La soundbar si disegna prima della pagina: e' la stessa barra laterale su
# tutte, e sta fuori dai frammenti che si auto-aggiornano - un iframe audio
# ridisegnato ogni due secondi taglierebbe il suono a meta'.
soundbar.render_sidebar()
st.navigation(pages, position="top").run()
