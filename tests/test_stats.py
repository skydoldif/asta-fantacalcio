"""Test delle statistiche della stagione precedente.

Coprono il join col listone (che avviene per Id ma si controlla sui nomi),
la selezione delle voci per ruolo e la resa in tabella.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from scripts.build_players import find_stats, merge_stats, parse_stats

from asta.data.players import stats_season
from asta.domain.models import ROLE_ORDER, Player, PlayerStats, Role
from asta.ui.components import (
    ROLE_VALUE,
    format_stat,
    listone_display,
    listone_table,
    stat_items,
)

STATS = find_stats()


def make_stats(**kwargs: float) -> PlayerStats:
    """Statistiche di prova: tutto a zero tranne quello che serve al test."""
    base = dict(
        matches=30,
        average=6.0,
        fanta_average=7.0,
        goals=0,
        goals_conceded=0,
        penalties_saved=0,
        penalties_taken=0,
        assists=0,
        yellow_cards=0,
        red_cards=0,
        own_goals=0,
    )
    base.update(kwargs)
    return PlayerStats(**base)  # type: ignore[arg-type]


def make_player(role: Role, stats: PlayerStats | None) -> Player:
    return Player(id=1, role=role, name="Tizio", team="Inter", quotation=10, fvm=50, stats=stats)


# ------------------------------------------------------------------ join


@pytest.mark.skipif(STATS is None, reason="file statistiche non presente")
def test_le_statistiche_si_agganciano_al_listone_giusto(real_listone):
    """I nomi devono coincidere: un Id riciclato darebbe dati di un altro."""
    stats = parse_stats(STATS)
    abbinati = [p for p in real_listone.players if p.stats is not None]
    assert abbinati, "nessun calciatore ha le statistiche"
    for player in abbinati:
        atteso = stats[player.id]["_name"]
        # Il listone aggiunge l'iniziale quando ci sono omonimi
        # (El Azzouzi -> El Azzouzi O.), il resto del nome deve combaciare.
        assert atteso.startswith(player.name[: len(atteso)]) or player.name.startswith(atteso)


@pytest.mark.skipif(STATS is None, reason="file statistiche non presente")
def test_i_portieri_hanno_gol_subiti_e_non_gol_fatti(real_listone):
    # Controllo di coerenza semantica: se le colonne fossero disallineate di
    # una posizione, i portieri risulterebbero marcatori.
    portieri = [p for p in real_listone.by_role(Role.P) if p.stats and p.stats.played]
    assert portieri
    assert all(p.stats.goals == 0 for p in portieri)
    assert any(p.stats.goals_conceded > 0 for p in portieri)

    movimento = [p for p in real_listone.players if p.role != Role.P and p.stats and p.stats.played]
    assert all(p.stats.goals_conceded == 0 for p in movimento)


@pytest.mark.skipif(STATS is None, reason="file statistiche non presente")
def test_chi_non_ha_mai_giocato_in_serie_a_resta_senza_statistiche(real_listone):
    senza = [p for p in real_listone.players if p.stats is None]
    assert senza, "il file copre tutti: sospetto"
    assert len(senza) < len(real_listone.players) / 2


def test_le_iniziali_aggiunte_dal_listone_non_sono_un_errore():
    players = [{"id": 1, "name": "El Azzouzi O.", "role": "C"}]
    stats = {1: {"_name": "El Azzouzi", "matches": 5}}
    abbinati, sospetti = merge_stats(players, stats)

    assert abbinati == 1
    assert sospetti == []
    assert players[0]["stats"] == {"matches": 5}


def test_un_nome_del_tutto_diverso_ferma_la_generazione():
    # Due file di stagioni diverse: gli Id combaciano ma i calciatori no.
    players = [{"id": i, "name": f"Giusto {i}", "role": "C"} for i in range(10)]
    stats = {i: {"_name": f"Sbagliato {i}", "matches": 1} for i in range(10)}

    with pytest.raises(ValueError, match="non corrispondono"):
        merge_stats(players, stats)


def test_senza_riga_di_statistiche_il_campo_resta_vuoto():
    players = [{"id": 1, "name": "Tizio", "role": "C", "stats": {"matches": 9}}]
    abbinati, sospetti = merge_stats(players, {})

    assert (abbinati, sospetti) == (0, [])
    assert "stats" not in players[0]


@pytest.mark.skipif(STATS is None, reason="file statistiche non presente")
def test_la_stagione_si_ricava_dal_nome_del_file():
    assert stats_season() == "2025/26"


# ------------------------------------------------------------------ resa


def voci(player: Player) -> dict[str, str]:
    """Le statistiche della card come ``{etichetta: valore}``."""
    return {label: value for label, _, value in stat_items(player)}


def test_le_voci_dipendono_dal_ruolo():
    portiere = voci(make_player(Role.P, make_stats(goals_conceded=31)))
    attaccante = voci(make_player(Role.A, make_stats(goals=17, assists=6)))

    assert "Gol subiti" in portiere and "👟" not in portiere
    assert "⚽" in attaccante and "Gol subiti" not in attaccante


def test_gli_zeri_si_mostrano():
    # Un attaccante senza assist e' un'informazione quanto uno con dieci.
    pulito = voci(make_player(Role.C, make_stats()))

    assert pulito["👟"] == "0"
    assert pulito["Rigori calciati"] == "0"


def test_gli_autogol_non_stanno_nel_riquadro():
    """Non hanno mai spostato un'offerta, e la riga si legge a voce alta."""
    tutte = voci(make_player(Role.C, make_stats(own_goals=2)))
    assert "Autogol" not in tutte


def test_gol_assist_e_cartellini_si_mostrano_col_simbolo():
    cattivo = voci(make_player(Role.C, make_stats(goals=4, assists=3, yellow_cards=9, red_cards=1)))

    assert cattivo["⚽"] == "4"
    assert cattivo["👟"] == "3"
    assert cattivo["🟨"] == "9"
    assert cattivo["🟥"] == "1"
    assert not {"Gol fatti", "Assist", "Ammonizioni", "Espulsioni"} & set(cattivo)


def test_il_simbolo_porta_con_se_il_nome_per_esteso():
    # Il tooltip della card: il simbolo si legge al volo, la parola resta
    # disponibile per chi non lo riconosce.
    titoli = {label: titolo for label, titolo, _ in stat_items(make_player(Role.C, make_stats()))}

    assert titoli["🟨"] == "Ammonizioni"
    assert titoli["🟥"] == "Espulsioni"
    assert titoli["⚽"] == "Gol fatti"
    assert titoli["👟"] == "Assist"


def test_nessuna_voce_senza_statistiche():
    assert stat_items(make_player(Role.A, None)) == []


def test_le_medie_si_leggono_con_la_virgola():
    assert format_stat("average", 6.0) == "6,00"
    assert format_stat("fanta_average", 7.643) == "7,64"
    assert format_stat("goals", 3) == "3"


COLONNE_LISTONE = [
    # Nell'ordine in cui si leggono: che ruolo fa, chi e', quanto vale,
    # com'e' andato, cosa batte, e in fondo l'infermeria. Gol subiti, rigori
    # parati e autogol restano fuori.
    "Ruolo",
    "Calciatore",
    "Squadra",
    "Fascia",
    "Titolarità",
    "Partite a voto",
    "Media voto",
    "Fantamedia",
    "⚽",
    "👟",
    "Rigori calciati",
    "🟨",
    "🟥",
    "Rigorista",
    "Corner",
    "Punizioni",
    "🚑",
]


def test_nel_listone_le_colonne_sono_per_esteso():
    tabella = listone_table((make_player(Role.A, make_stats(goals=4, assists=2)),))
    assert list(tabella.columns) == COLONNE_LISTONE


def test_le_colonne_ci_sono_tutte_qualunque_sia_il_ruolo():
    # Niente colonne che appaiono e spariscono col filtro: la tabella si
    # guarda dal computer e mostra tutto, anche quello che per un ruolo vale
    # sempre zero.
    portieri = listone_table((make_player(Role.P, make_stats(goals_conceded=20)),))
    attaccanti = listone_table((make_player(Role.A, make_stats(goals=4)),))

    assert list(portieri.columns) == list(attaccanti.columns) == COLONNE_LISTONE


def test_il_ruolo_si_mostra_con_la_sua_emoji():
    """La stessa del riquadro verde e della barra della fase."""
    tabella = listone_table((make_player(Role.P, None),))
    assert "🧤" in listone_display(tabella).to_string()


def test_il_ruolo_si_ordina_per_fase_d_asta_e_non_per_alfabeto():
    """Crescente deve dare portieri, difensori, centrocampisti, attaccanti.

    Sotto la cella c'e' un numero proprio per questo: con le sigle si
    partirebbe dagli attaccanti, che all'asta si chiamano per ultimi.
    """
    tabella = listone_table(tuple(make_player(role, None) for role in reversed(ROLE_ORDER)))
    ordinata = tabella.sort_values("Ruolo")["Ruolo"].tolist()
    assert ordinata == [ROLE_VALUE[role] for role in ROLE_ORDER]
    assert ordinata == sorted(ordinata)


def test_le_celle_senza_dati_si_mostrano_vuote():
    # Streamlit scrive "None" in ogni cella nulla, e 144 righe di "None"
    # coprirebbero i dati veri.
    tabella = listone_table((make_player(Role.A, make_stats(goals=4)), make_player(Role.A, None)))
    righe = listone_display(tabella).to_string().splitlines()

    con_dati, senza_dati = righe[1], righe[2]
    assert "None" not in senza_dati
    assert senza_dati.split()[-1] == "Inter", "dopo la squadra non deve esserci nulla"
    assert con_dati.split()[-1] == "0", "chi ha giocato mostra anche gli zeri"


def test_l_ordinamento_resta_numerico():
    # Le celle sono vuote a schermo ma sotto restano numeri: e' quello che
    # permette di ordinare per fantamedia e trovare il migliore rimasto.
    tabella = listone_table((make_player(Role.A, make_stats(fanta_average=7.5)),))
    vista = listone_display(tabella).data

    assert pd.api.types.is_numeric_dtype(vista["Fantamedia"])


def test_una_ricerca_senza_risultati_non_esplode():
    # Cercando un calciatore gia' venduto (o inesistente) la selezione resta
    # vuota: senza colonne dichiarate il DataFrame non ne avrebbe nessuna e
    # la conversione a interi cercherebbe una colonna che non c'e'.
    tabella = listone_table(())

    assert list(tabella.columns) == COLONNE_LISTONE
    assert len(tabella) == 0
    assert listone_display(tabella) is not None


def test_le_medie_hanno_la_virgola_anche_in_tabella():
    tabella = listone_table((make_player(Role.A, make_stats(average=6.5)),))
    assert "6,50" in listone_display(tabella).to_string()


def test_i_conteggi_restano_interi_anche_con_celle_vuote():
    # Con le celle vuote pandas passerebbe a float: 30 partite -> 30.0.
    tabella = listone_table((make_player(Role.A, make_stats(goals=4)), make_player(Role.A, None)))
    assert tabella["Partite a voto"].tolist() == [30, pd.NA]
    assert str(tabella["Partite a voto"].dtype) == "Int64"


def test_chi_ha_zero_partite_a_voto_resta_vuoto_in_tabella():
    tabella = listone_table((make_player(Role.C, make_stats(matches=0)),))
    assert tabella["Fantamedia"].isna().all()


def test_il_file_delle_statistiche_e_facoltativo(tmp_path: Path):
    # Senza il file l'app deve funzionare lo stesso, senza rendimenti.
    assert find_stats(tmp_path) is None
