"""Test della modalita "lettera random"."""

from __future__ import annotations

from asta.domain.events import EventType
from asta.domain.letters import (
    current_player,
    draw_letter,
    eligible_letters,
    letter_exhausted,
    letter_queue,
    phase_exhausted,
    skipped_in_letter,
    upcoming,
)
from asta.domain.models import Role


def draw(service, letter, seed=1, reopen=False):
    return service.record(
        EventType.LETTER_DRAWN,
        {
            "role": service.state().current_role.value,
            "letter": letter,
            "seed": seed,
            "reopen": reopen,
        },
    )


def test_lettere_ammissibili_solo_quelle_con_portieri(service):
    # Portieri di prova: Abbiati, Amelia, Buffon, Consigli.
    assert eligible_letters(service.state()) == ("A", "B", "C")


def test_una_lettera_estratta_non_esce_piu(service):
    draw(service, "A")
    assert eligible_letters(service.state()) == ("B", "C")


def test_estrazione_ripetuta_esaurisce_le_lettere_senza_ripetizioni(service):
    estratte = []
    for _ in range(10):
        result = draw_letter(service.state())
        if result is None:
            break
        letter, seed = result
        estratte.append(letter)
        draw(service, letter, seed)
    assert sorted(estratte) == ["A", "B", "C"]
    assert draw_letter(service.state()) is None


def test_estrazione_deterministica_a_parita_di_seme(service):
    state = service.state()
    assert draw_letter(state, seed=42) == draw_letter(state, seed=42)


def test_lettera_senza_calciatori_disponibili_non_e_estraibile(service):
    # Si aggiudicano entrambi i portieri con la A.
    service.record(EventType.PLAYER_ASSIGNED, {"player_id": 101, "team": "Ajax", "price": 5})
    service.record(EventType.PLAYER_ASSIGNED, {"player_id": 102, "team": "Bayern", "price": 5})
    assert eligible_letters(service.state()) == ("B", "C")


def test_coda_in_ordine_alfabetico(service):
    draw(service, "A")
    assert [p.name for p in letter_queue(service.state())] == ["Abbiati", "Amelia"]


def test_il_calciatore_corrente_e_il_primo_della_coda(service):
    draw(service, "A")
    assert current_player(service.state()).name == "Abbiati"


def test_il_saltato_esce_dalla_coda_ma_resta_nel_listone(service):
    draw(service, "A")
    service.record(EventType.PLAYER_SKIPPED, {"player_id": 101})
    state = service.state()

    assert [p.name for p in letter_queue(state)] == ["Amelia"]
    assert current_player(state).name == "Amelia"
    assert not state.is_taken(101)
    assert [p.name for p in skipped_in_letter(state)] == ["Abbiati"]


def test_riapertura_lettera_recupera_i_saltati(service):
    draw(service, "A")
    service.record(EventType.PLAYER_SKIPPED, {"player_id": 101})
    service.record(EventType.PLAYER_SKIPPED, {"player_id": 102})
    assert letter_exhausted(service.state())

    draw(service, "A", reopen=True)
    state = service.state()
    assert [p.name for p in letter_queue(state)] == ["Abbiati", "Amelia"]
    assert state.drawn_letters == ("A",)


def test_riapertura_non_tocca_i_salti_delle_altre_lettere(service):
    draw(service, "A")
    service.record(EventType.PLAYER_SKIPPED, {"player_id": 101})
    draw(service, "B")
    service.record(EventType.PLAYER_SKIPPED, {"player_id": 103})
    draw(service, "B", reopen=True)

    state = service.state()
    assert 101 in state.skipped
    assert 103 not in state.skipped


def test_coda_esaurita_dopo_le_aggiudicazioni(service):
    draw(service, "A")
    service.record(EventType.PLAYER_ASSIGNED, {"player_id": 101, "team": "Ajax", "price": 5})
    service.record(EventType.PLAYER_ASSIGNED, {"player_id": 102, "team": "Bayern", "price": 5})
    assert letter_exhausted(service.state())
    assert not phase_exhausted(service.state())


def test_fase_esaurita_quando_non_restano_lettere_ne_calciatori(service):
    for pid in (101, 102, 103, 104):
        service.record(EventType.PLAYER_ASSIGNED, {"player_id": pid, "team": "Ajax", "price": 1})
    assert phase_exhausted(service.state())


def test_le_lettere_si_azzerano_al_cambio_ruolo(service):
    draw(service, "A")
    draw(service, "B")
    service.record(EventType.ROLE_PHASE_STARTED, {"role": Role.D.value})
    state = service.state()
    assert state.drawn_letters == ()
    # Difensori di prova: Bonucci, Cannavaro, Chiellini, Zambrotta.
    assert eligible_letters(state) == ("B", "C", "Z")


def test_nessuna_lettera_senza_fase_avviata(listone, settings):
    from asta.data.repository import InMemoryRepository
    from asta.service import AuctionService

    svc = AuctionService(repo=InMemoryRepository(), listone=listone)
    svc.record(EventType.AUCTION_CONFIGURED, settings.to_payload())
    assert eligible_letters(svc.state()) == ()
    assert letter_queue(svc.state()) == ()
    assert current_player(svc.state()) is None


def test_chiamata_libera_ha_la_precedenza_sulla_coda(service):
    draw(service, "A")
    service.record(EventType.PLAYER_NOMINATED, {"player_id": 104})
    assert current_player(service.state()).name == "Consigli"


# ---------------------------------------------------- i prossimi della lettera


def test_i_prossimi_escludono_chi_e_in_asta_ora(service):
    draw(service, "A")
    state = service.state()
    assert current_player(state).name == "Abbiati"
    assert [p.name for p in upcoming(state)] == ["Amelia"]


def test_i_prossimi_sono_tutta_la_coda_non_i_primi_pochi(service):
    """La colonna nella card scorre: non serve tagliarla a monte."""
    draw(service, "A")
    state = service.state()
    assert len(upcoming(state)) == len(letter_queue(state)) - 1


def test_dopo_una_chiamata_manuale_i_prossimi_restano_quelli_della_coda(service):
    """Il chiamato a mano puo' non essere in testa: si toglie per Id, non per posizione."""
    draw(service, "A")
    service.record(EventType.PLAYER_NOMINATED, {"player_id": 102})  # Amelia
    state = service.state()
    assert current_player(state).name == "Amelia"
    assert [p.name for p in upcoming(state)] == ["Abbiati"]


def test_in_chiamata_libera_non_c_e_nessuna_coda(service):
    """Senza lettera estratta la colonna resta vuota, senza controlli di modalita'."""
    assert upcoming(service.state()) == ()
