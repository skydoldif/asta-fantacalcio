"""Test delle regole d'asta: crediti, riserva slot, limiti di ruolo, coerenza."""

from __future__ import annotations

from asta.domain.events import EventType
from asta.domain.models import Mode, Role, Settings
from asta.domain.rules import (
    blocking_reason,
    max_bid,
    next_role,
    role_progress,
    validate_assignment,
    validate_settings,
)


def assign(service, player_id, team, price):
    return service.record(
        EventType.PLAYER_ASSIGNED, {"player_id": player_id, "team": team, "price": price}
    )


# --------------------------------------------------------------- riserva slot


def test_offerta_massima_riserva_un_credito_per_slot(service):
    # 100 crediti, 4 slot da riempire -> si puo' offrire 97 e restare con 3.
    assert max_bid(service.state(), "Ajax") == 97


def test_prezzo_al_limite_della_riserva_accettato(service, listone):
    state = service.state()
    assert validate_assignment(state, listone.get(103), "Ajax", 97) is None


def test_prezzo_oltre_la_riserva_rifiutato(service, listone):
    state = service.state()
    rejection = validate_assignment(state, listone.get(103), "Ajax", 98)
    assert rejection is not None
    assert rejection.code == "reserve"
    assert "97" in rejection.message


def test_la_riserva_si_riduce_man_mano_che_la_rosa_si_riempie(service):
    assign(service, 103, "Ajax", 50)
    # Restano 50 crediti e 3 slot: massimo 48.
    assert max_bid(service.state(), "Ajax") == 48


def test_ultimo_slot_puo_usare_tutti_i_crediti(service):
    assign(service, 103, "Ajax", 40)
    service.record(EventType.ROLE_PHASE_STARTED, {"role": Role.D.value})
    assign(service, 201, "Ajax", 20)
    service.record(EventType.ROLE_PHASE_STARTED, {"role": Role.C.value})
    assign(service, 301, "Ajax", 20)
    service.record(EventType.ROLE_PHASE_STARTED, {"role": Role.A.value})

    state = service.state()
    assert state.teams["Ajax"].credits_left == 20
    assert max_bid(state, "Ajax") == 20


def test_prezzo_oltre_i_crediti_residui(service, listone):
    assign(service, 103, "Ajax", 97)
    service.record(EventType.ROLE_PHASE_STARTED, {"role": Role.D.value})
    rejection = validate_assignment(service.state(), listone.get(201), "Ajax", 50)
    assert rejection is not None
    assert rejection.code == "no_credits"


# --------------------------------------------------------------- limiti e ruoli


def test_reparto_pieno(service, listone):
    assign(service, 103, "Ajax", 10)
    rejection = validate_assignment(service.state(), listone.get(104), "Ajax", 5)
    assert rejection is not None
    assert rejection.code == "role_full"


def test_ruolo_sbagliato_per_la_fase_in_corso(service, listone):
    rejection = validate_assignment(service.state(), listone.get(201), "Ajax", 5)
    assert rejection is not None
    assert rejection.code == "wrong_role"


def test_ruolo_sbagliato_ammesso_se_il_vincolo_e_disattivato(listone, settings):
    from asta.data.repository import InMemoryRepository
    from asta.service import AuctionService

    libera = Settings(
        teams=settings.teams,
        credits=settings.credits,
        roster_size=settings.roster_size,
        role_limits=settings.role_limits,
        mode=Mode.FREE,
        active_role_only=False,
    )
    svc = AuctionService(repo=InMemoryRepository(), listone=listone)
    svc.record(EventType.AUCTION_CONFIGURED, libera.to_payload())
    svc.record(EventType.ROLE_PHASE_STARTED, {"role": Role.P.value})
    assert validate_assignment(svc.state(), listone.get(201), "Ajax", 5) is None


def test_calciatore_gia_venduto(service, listone):
    assign(service, 103, "Ajax", 10)
    rejection = validate_assignment(service.state(), listone.get(103), "Bayern", 20)
    assert rejection is not None
    assert rejection.code == "already_sold"
    assert "Ajax" in rejection.message


def test_prezzo_minimo(service, listone):
    rejection = validate_assignment(service.state(), listone.get(103), "Ajax", 0)
    assert rejection is not None
    assert rejection.code == "price_too_low"


def test_squadra_inesistente(service, listone):
    rejection = validate_assignment(service.state(), listone.get(103), "Fantasma", 5)
    assert rejection is not None
    assert rejection.code == "unknown_team"


def test_rosa_completa(service, listone):
    assign(service, 103, "Ajax", 10)
    service.record(EventType.ROLE_PHASE_STARTED, {"role": Role.D.value})
    assign(service, 201, "Ajax", 10)
    service.record(EventType.ROLE_PHASE_STARTED, {"role": Role.C.value})
    assign(service, 301, "Ajax", 10)
    service.record(EventType.ROLE_PHASE_STARTED, {"role": Role.A.value})
    assign(service, 401, "Ajax", 10)

    state = service.state()
    assert state.teams["Ajax"].is_complete
    assert state.teams["Ajax"].max_bid == 0
    rejection = validate_assignment(state, listone.get(402), "Ajax", 5)
    assert rejection is not None
    assert rejection.code in {"roster_full", "role_full"}


# --------------------------------------------------------------- correzioni


def test_la_correzione_non_conta_se_stessa(service, listone):
    event = assign(service, 103, "Ajax", 90)
    state = service.state()
    # Senza ignore_seq il reparto risulta pieno e i crediti esauriti...
    assert validate_assignment(state, listone.get(103), "Ajax", 95) is not None
    # ...ma correggendo *quella* aggiudicazione il posto e i crediti tornano liberi.
    assert validate_assignment(state, listone.get(103), "Ajax", 95, ignore_seq=event.seq) is None


def test_correzione_verso_altra_squadra(service, listone):
    event = assign(service, 103, "Ajax", 90)
    state = service.state()
    assert validate_assignment(state, listone.get(103), "Bayern", 90, ignore_seq=event.seq) is None


def test_motivo_di_blocco_ignora_il_prezzo(service, listone):
    assign(service, 103, "Ajax", 10)
    assert blocking_reason(service.state(), listone.get(104), "Ajax") is not None
    assert blocking_reason(service.state(), listone.get(104), "Bayern") is None


# --------------------------------------------------------------- impostazioni


def test_impostazioni_valide(settings, real_listone):
    assert validate_settings(settings, real_listone) == []


def test_somma_limiti_diversa_dalla_rosa(real_listone):
    bad = Settings(
        teams=("A", "B"),
        credits=500,
        roster_size=25,
        role_limits=((Role.P, 3), (Role.D, 8), (Role.C, 8), (Role.A, 5)),
    )
    errors = validate_settings(bad, real_listone)
    assert any("somma dei limiti" in e for e in errors)


def test_nomi_duplicati(real_listone):
    bad = Settings(teams=("Ajax", "ajax"), credits=500, roster_size=25)
    assert any("duplicati" in e for e in validate_settings(bad, real_listone))


def test_nome_con_virgola_rifiutato(real_listone):
    bad = Settings(teams=("Ajax, il vero", "Bayern"), credits=500, roster_size=25)
    assert any("virgole" in e for e in validate_settings(bad, real_listone))


def test_crediti_insufficienti_per_la_rosa(real_listone):
    bad = Settings(teams=("A", "B"), credits=10, roster_size=25)
    assert any("crediti" in e for e in validate_settings(bad, real_listone))


def test_listone_troppo_corto_per_il_numero_di_squadre(real_listone):
    # 16 squadre x 6 attaccanti = 96 > 89 attaccanti disponibili.
    bad = Settings(teams=tuple(f"S{i}" for i in range(16)), credits=500, roster_size=25)
    assert any("Attaccanti".lower() in e.lower() for e in validate_settings(bad, real_listone))


def test_almeno_due_squadre(real_listone):
    assert any(
        "almeno 2" in e
        for e in validate_settings(
            Settings(teams=("Solo",), credits=500, roster_size=25), real_listone
        )
    )


# --------------------------------------------------------------- avanzamento


def test_avanzamento_di_fase(service):
    assert role_progress(service.state(), Role.P) == (0, 2)
    assign(service, 103, "Ajax", 10)
    assert role_progress(service.state(), Role.P) == (1, 2)


def test_sequenza_dei_ruoli():
    assert next_role(None) is Role.P
    assert next_role(Role.P) is Role.D
    assert next_role(Role.D) is Role.C
    assert next_role(Role.C) is Role.A
    assert next_role(Role.A) is None
