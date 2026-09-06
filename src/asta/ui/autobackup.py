"""Download automatico del backup nei momenti critici dell'asta.

Il backup manuale c'e' gia' nella scheda Export, ma va ricordato: questo
modulo lo fa partire da solo quando il rischio di perdere qualcosa e' piu'
alto - la rete che cade, un reparto che si chiude, l'asta che finisce.

Come si fa partire un download senza un click: Streamlit non ha un'API per
farlo, quindi si stampa un componente HTML minuscolo con dentro il JSON e uno
``<a download>`` cliccato via JavaScript. L'iframe dei componenti nasce con
``allow-downloads`` e ``allow-same-origin`` nel sandbox, quindi il browser lo
consente; il download parte comunque subito dopo un click dell'admin (il
pulsante che cambia reparto), cioe' con l'attivazione utente ancora valida.

Ogni momento scarica **una volta sola** per sessione del browser: i momenti
gia' passati quando si apre la pagina vengono segnati come fatti, altrimenti
riaprire l'admin a meta' asta scaricherebbe i backup dei reparti chiusi
un'ora prima.
"""

from __future__ import annotations

import json

import streamlit as st

from asta.domain.export import backup_json, export_filename
from asta.domain.models import (
    BACKUP_TRIGGER_LABEL,
    BACKUP_TRIGGER_SLUG,
    END_OF_PHASE,
    ROLE_ORDER,
    BackupTrigger,
    Role,
)
from asta.domain.reducer import AuctionState
from asta.service import AuctionService

#: Chiave di sessione con i momenti gia' scaricati. Dentro ci stanno i
#: *valori* dei momenti, non i membri dell'enum: quello che finisce in
#: ``st.session_state`` sopravvive al ricaricamento dei moduli di Streamlit e
#: si ritroverebbe a confrontare due classi ``BackupTrigger`` diverse.
DONE_KEY = "backup_scaricati"


def phase_over(state: AuctionState, role: Role) -> bool:
    """True se la fase di quel ruolo e' finita, cioe' se ne e' iniziata una dopo."""
    if state.closed:
        return True
    if state.current_role is None:
        return False
    return ROLE_ORDER.index(state.current_role) > ROLE_ORDER.index(role)


def fired_triggers(state: AuctionState, synced: bool) -> tuple[BackupTrigger, ...]:
    """Momenti scattati adesso, gia' filtrati sulle impostazioni dell'asta.

    E' una fotografia della situazione, non un elenco di cose da fare: dice
    quali momenti *valgono* ora, non quali sono nuovi. A distinguere i nuovi
    ci pensa :func:`auto_backup` con l'elenco dei gia' scaricati.

    Args:
        state: stato corrente dell'asta.
        synced: False se ci sono scritture in coda verso il database.
    """
    settings = state.settings
    if settings is None:
        return ()
    scattati: set[BackupTrigger] = set()
    if not synced:
        scattati.add(BackupTrigger.OFFLINE)
    for role, trigger in END_OF_PHASE.items():
        if phase_over(state, role):
            scattati.add(trigger)
    if state.closed:
        scattati.add(BackupTrigger.END_AUCTION)
    return tuple(t for t in BackupTrigger if t in scattati and settings.backs_up(t))


def download_html(filename: str, content: str) -> str:
    """Componente che fa partire il download del backup appena viene caricato.

    Il JSON viaggia dentro la pagina come stringa JavaScript: ``json.dumps``
    si occupa di virgolette e a capo, e ``</`` va spezzato a mano perche' un
    ``</script>`` dentro un nome di squadra chiuderebbe il tag.

    Il link si attacca a ``documentElement`` e non a ``document.body``: qui lo
    script gira mentre la pagina e' ancora in ``<head>``, e il body non
    esiste ancora (``appendChild`` di ``null`` e il download non parte).
    Serve comunque attaccarlo da qualche parte, altrimenti Firefox ignora il
    click.
    """
    dati = json.dumps(content).replace("</", "<\\/")
    return f"""<script>
const blob = new Blob([{dati}], {{type: "application/json"}});
const url = URL.createObjectURL(blob);
const a = document.createElement("a");
a.href = url;
a.download = {json.dumps(filename)};
document.documentElement.appendChild(a);
a.click();
// L'oggetto resta vivo finche' il browser non ha finito di scrivere il file.
setTimeout(() => URL.revokeObjectURL(url), 30000);
</script>"""


def auto_backup(service: AuctionService, state: AuctionState) -> None:
    """Scarica il backup se e' appena scattato un momento fra quelli scelti.

    Scarica un file per volta: i browser bloccano i download automatici a
    raffica, e comunque due momenti insieme non capitano (ogni click
    dell'admin ne fa scattare al massimo uno).
    """
    scattati = fired_triggers(state, service.synced)
    if DONE_KEY not in st.session_state:
        st.session_state[DONE_KEY] = {t.value for t in scattati}
        return
    fatti: set[str] = st.session_state[DONE_KEY]

    # La connessione tornata ricarica la molla: la prossima caduta e' un altro
    # momento, e merita il suo backup.
    if service.synced:
        fatti.discard(BackupTrigger.OFFLINE.value)

    nuovo = next((t for t in scattati if t.value not in fatti), None)
    if nuovo is None:
        return
    fatti.add(nuovo.value)

    nome = export_filename(f"backup_{BACKUP_TRIGGER_SLUG[nuovo]}", "json")
    st.iframe(download_html(nome, backup_json(service.events)), height=1)
    st.toast(f"💾 Backup scaricato: {BACKUP_TRIGGER_LABEL[nuovo].lower()}.")
