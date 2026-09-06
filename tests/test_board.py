"""Test della griglia delle squadre.

``teams_board_html`` e' una funzione pura: si puo' verificare l'HTML prodotto
senza avviare Streamlit.
"""

from __future__ import annotations

import re
from dataclasses import replace

from asta.data.repository import InMemoryRepository
from asta.domain.events import EventType
from asta.domain.models import Listone, Player, Role, Settings
from asta.domain.reducer import build_state
from asta.service import AuctionService
from asta.ui.board import ROLE_COLOR, club_breakdown_html, club_counts, teams_board_html

VUOTO = '<div class="tb-slot"></div>'


def regola_css(html: str, selettore: str) -> str:
    """Corpo della regola CSS con *quel* selettore.

    Ancorata a inizio riga: cercare la sottostringa becherebbe anche le regole
    piu' specifiche che contengono lo stesso selettore (``.tb-card.me .tb-name``
    contiene ``.tb-name``).
    """
    match = re.search(rf"(?m)^{re.escape(selettore)}\{{(.*?)\}}", html, re.S)
    assert match, f"regola CSS {selettore!r} non trovata"
    return match.group(1)


def test_una_colonna_per_squadra(service):
    html = teams_board_html(service.state())
    assert "Ajax" in html
    assert "Bayern" in html
    assert "grid-template-columns:repeat(2,minmax(140px,1fr))" in html


def test_le_squadre_seguono_l_ordine_di_configurazione(service):
    html = teams_board_html(service.state())
    assert html.index(">Ajax<") < html.index(">Bayern<")


def test_crediti_e_offerta_massima_in_card(service):
    html = teams_board_html(service.state())
    assert '<div class="tb-credits">100<small>' in html
    assert "max <b>97</b>" in html  # 100 crediti - 3 slot residui


def test_slot_vuoti_pari_ai_limiti_di_reparto(service):
    # 2 squadre x 4 slot (1 per ruolo) = 8 slot vuoti.
    assert teams_board_html(service.state()).count(VUOTO) == 8


def test_uno_slot_pieno_mostra_nome_e_prezzo(service):
    service.record(EventType.PLAYER_ASSIGNED, {"player_id": 103, "team": "Ajax", "price": 25})
    html = teams_board_html(service.state())

    assert "Buffon" in html
    assert ">25</b>" in html
    assert html.count(VUOTO) == 7
    assert '<div class="tb-credits">75<small>' in html


def test_percentuale_di_budget_speso_nel_reparto(service):
    service.record(EventType.PLAYER_ASSIGNED, {"player_id": 103, "team": "Ajax", "price": 25})
    # 25 crediti su 100 investiti fra i portieri.
    assert '<span class="tb-pct">25%</span>' in teams_board_html(service.state())


def test_percentuale_arrotondata_e_per_reparto(service):
    service.record(EventType.PLAYER_ASSIGNED, {"player_id": 103, "team": "Ajax", "price": 33})
    html = teams_board_html(service.state())
    assert '<span class="tb-pct">33%</span>' in html
    # Gli altri reparti restano a zero.
    assert html.count('<span class="tb-pct">0%</span>') == 7


def test_barra_crediti_proporzionale(service):
    service.record(EventType.PLAYER_ASSIGNED, {"player_id": 103, "team": "Ajax", "price": 40})
    assert 'style="width:60.0%"' in teams_board_html(service.state())


def test_slot_rimanenti_per_ruolo_in_card(service):
    html = teams_board_html(service.state())
    # Con limiti 1/1/1/1 ogni squadra parte con un solo slot per reparto.
    assert f'<i style="color:{ROLE_COLOR[Role.P]}">1</i>' in html

    service.record(EventType.PLAYER_ASSIGNED, {"player_id": 103, "team": "Ajax", "price": 5})
    html = teams_board_html(service.state())
    # A reparto completo lo zero resta, ma smorzato.
    assert f'<i style="color:{ROLE_COLOR[Role.P]}">0</i>' not in html
    assert '<i style="color:rgba(128,128,128,.6)">0</i>' in html
    # Il Bayern non ha ancora comprato: il suo contatore e' ancora acceso.
    assert f'<i style="color:{ROLE_COLOR[Role.P]}">1</i>' in html


def test_tutti_i_reparti_sono_presenti_per_ogni_squadra(service):
    html = teams_board_html(service.state())
    for role in Role:
        # Una barra di reparto per squadra.
        assert html.count(f'<summary style="background:{ROLE_COLOR[role]}"') == 2


def test_evidenziazione_della_propria_squadra(service):
    html = teams_board_html(service.state(), highlight="Bayern")
    assert html.count('class="tb-card me"') == 1
    assert html.count('class="tb-card"') == 1
    assert html.count('<span class="tb-me">TU</span>') == 1

    # La card evidenziata e' colorata, non solo bordata: e' il segnale che si
    # coglie a colpo d'occhio in mezzo a otto colonne.
    assert "background:" in regola_css(html, ".tb-card.me")


def test_nessuna_evidenziazione_di_default(service):
    assert "tb-card me" not in teams_board_html(service.state())


def test_nomi_in_maiuscolo_grassetto(service):
    service.record(EventType.PLAYER_ASSIGNED, {"player_id": 103, "team": "Ajax", "price": 25})
    html = teams_board_html(service.state())

    # Nel markup i nomi restano come nel listone: e' il CSS a renderli
    # maiuscoli, cosi' il tooltip mostra il nome vero quando va in ellissi.
    assert "Buffon" in html
    assert 'title="Buffon"' in html
    assert "Ajax" in html

    for selettore in (".tb-name", ".tb-slot.full em"):
        regola = regola_css(html, selettore)
        assert "text-transform:uppercase" in regola, selettore
        assert "font-weight:700" in regola, selettore


def test_il_maiuscolo_non_tocca_il_riquadro_in_asta_ora(service, listone):
    """La card del calciatore in asta ha un formato suo, che resta invariato."""
    from asta.ui.board import _CSS

    assert "tb-" in _CSS
    # Nessuna regola della griglia puo' applicarsi fuori dalle sue classi.
    for riga in _CSS.strip().splitlines():
        if riga.startswith("."):
            assert riga.startswith((".tb{", ".tb-")), riga


def test_asta_non_configurata(listone):
    assert "Nessuna squadra." in teams_board_html(build_state(listone, []))


def test_i_nomi_delle_squadre_sono_sanificati():
    listone = Listone(
        players=(Player(id=1, role=Role.P, name="Tizio", team="X", quotation=1, fvm=1),)
    )
    cfg = Settings(
        teams=('<img src=x onerror="alert(1)">',), roster_size=1, role_limits=((Role.P, 1),)
    )
    svc = AuctionService(repo=InMemoryRepository(), listone=listone)
    svc.record(EventType.AUCTION_CONFIGURED, cfg.to_payload())

    html = teams_board_html(svc.state())
    assert "<img src=x" not in html
    assert "&lt;img src=x" in html


def test_i_nomi_dei_calciatori_sono_sanificati():
    listone = Listone(
        players=(Player(id=1, role=Role.P, name="<b>Hack</b>", team="X", quotation=1, fvm=1),)
    )
    cfg = Settings(teams=("Ajax",), credits=50, roster_size=1, role_limits=((Role.P, 1),))
    svc = AuctionService(repo=InMemoryRepository(), listone=listone)
    svc.record(EventType.AUCTION_CONFIGURED, cfg.to_payload())
    svc.record(EventType.PLAYER_ASSIGNED, {"player_id": 1, "team": "Ajax", "price": 5})

    html = teams_board_html(svc.state())
    assert "<b>Hack</b>" not in html
    assert "&lt;b&gt;Hack&lt;/b&gt;" in html


def test_reparti_ordinati_per_prezzo_decrescente(listone, settings):
    grande = Settings(teams=("Ajax",), credits=100, roster_size=3, role_limits=((Role.P, 3),))
    svc = AuctionService(repo=InMemoryRepository(), listone=listone)
    svc.record(EventType.AUCTION_CONFIGURED, grande.to_payload())
    for pid, prezzo in ((101, 10), (102, 30), (103, 20)):
        svc.record(EventType.PLAYER_ASSIGNED, {"player_id": pid, "team": "Ajax", "price": prezzo})

    html = teams_board_html(svc.state())
    assert html.index("Amelia") < html.index("Buffon") < html.index("Abbiati")


# ------------------------------------------------- composizione per club


def _rosa(service: AuctionService, *coppie: tuple[int, str]) -> None:
    """Aggiudica ad Ajax i calciatori indicati, dando a ognuno il suo club di A.

    Il listone sintetico ha tutti i calciatori nella stessa squadra: qui serve
    il contrario, perche' e' proprio la provenienza che si vuole vedere.
    """
    club_di = dict(coppie)
    service.listone = Listone(
        players=tuple(
            replace(p, team=club_di[p.id]) if p.id in club_di else p
            for p in service.listone.players
        )
    )
    for pid, _ in coppie:
        service.record(EventType.PLAYER_ASSIGNED, {"player_id": pid, "team": "Ajax", "price": 1})


def test_i_club_si_ordinano_per_gol_subiti(service):
    """Stessa fila della pagina portieri: dalla difesa meno battuta in giu'."""
    _rosa(service, (101, "Inter"), (201, "Inter"), (301, "Milan"))
    html = club_breakdown_html(
        service.state(), "Ajax", conceded={"Milan": 35, "Inter": 40, "Testalonga": 61}
    )

    assert html.index("Milan") < html.index("Inter") < html.index("Testalonga")
    assert '<b class="cb-n">2</b>' in html
    assert '<b class="cb-n">1</b>' in html


def test_le_squadre_senza_gol_subiti_chiudono_la_fila(service):
    """Le neopromosse non hanno un numero: uno zero le metterebbe in testa."""
    _rosa(service, (101, "Inter"), (301, "Monza"))
    html = club_breakdown_html(service.state(), "Ajax", conceded={"Inter": 40})

    assert html.index("Inter") < html.index("Monza")


def test_i_gol_subiti_spiegano_la_fila_nel_tooltip(service):
    _rosa(service, (101, "Inter"))
    html = club_breakdown_html(service.state(), "Ajax", conceded={"Inter": 40})

    # L'apostrofo esce dall'escape come entita', come per i nomi delle squadre.
    assert 'title="Inter: Abbiati - 40 gol subiti l&#x27;anno scorso"' in html


def test_i_nomi_dei_calciatori_stanno_nel_tooltip(service):
    _rosa(service, (101, "Inter"), (201, "Inter"))
    html = club_breakdown_html(service.state(), "Ajax", conceded={})

    assert 'title="Inter: Abbiati, Bonucci"' in html


def test_i_club_a_zero_ci_sono_col_pallino_rosso(service):
    _rosa(service, (101, "Inter"))
    html = club_breakdown_html(service.state(), "Ajax")

    # Il listone di prova ha due club: l'Inter appena assegnata e quello di
    # tutti gli altri calciatori, che resta a zero.
    assert '<b class="cb-n">1</b>' in html
    assert '<b class="cb-n zero">0</b>' in html
    assert 'title="Testalonga: nessun calciatore"' in html


def test_ogni_club_del_listone_ha_la_sua_casella(service):
    _rosa(service, (101, "Inter"), (201, "Milan"))
    html = club_breakdown_html(service.state(), "Ajax")

    club = {p.team for p in service.listone.players}
    assert html.count('class="cb-item"') == len(club)


def test_senza_aggiudicazioni_i_club_sono_tutti_a_zero(service):
    html = club_breakdown_html(service.state(), "Ajax")

    assert '<b class="cb-n zero">0</b>' in html
    assert '<b class="cb-n">' not in html.replace('<b class="cb-n zero">', "")


def test_una_squadra_inesistente_non_rompe_la_pagina(service):
    assert club_breakdown_html(service.state(), "Squadra Fantasma") == ""


def test_la_copertura_ha_titolo_e_riquadro(service):
    """L'etichetta sta dentro il riquadro: sotto la griglia delle squadre,
    senza un bordo, sembrerebbe la coda di quella."""
    html = club_breakdown_html(service.state(), "Ajax")

    assert "<div class='cb-box'>" in html
    assert "<div class='cb-titolo'>Copertura squadra</div>" in html
    assert "non ha ancora calciatori" in html, "la riga di riepilogo sta nel riquadro"


def test_senza_stemma_resta_la_sigla_del_club(service):
    _rosa(service, (101, "Club Inventato"))
    html = club_breakdown_html(service.state(), "Ajax")

    assert '<span class="cb-sigla">CLU</span>' in html
    assert "<img" not in html


def test_il_club_conta_i_calciatori_non_le_squadre(service):
    _rosa(service, (101, "Inter"), (201, "Inter"), (301, "Milan"))
    conteggi = club_counts(service.state(), "Ajax")

    assert {club: len(nomi) for club, nomi in conteggi.items()} == {"Inter": 2, "Milan": 1}
