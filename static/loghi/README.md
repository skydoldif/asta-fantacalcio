# Stemmi delle squadre di Serie A

Un file per squadra, più `serie-a.svg` (il logo della lega, usato come filigrana
nel riquadro "in asta ora"). Il nome del file è il nome della squadra come
compare nel listone, **minuscolo e senza spazi, accenti o punteggiatura**:

| Squadra nel listone | File |
|---|---|
| Como | `como.svg` |
| Inter | `inter.svg` |
| Hellas Verona | `hellasverona.svg` |

Formati accettati: `.svg`, `.png`, `.webp`, `.jpg`. A parità di nome vince l'SVG.

L'app li serve come file statici, quindi il browser li scarica una volta sola e
li tiene in cache: non appesantiscono gli aggiornamenti automatici delle pagine.
Se manca il file di una squadra non succede niente: resta il nome scritto.

## Dopo averne aggiunti di nuovi

```bash
python scripts/optimize_crests.py
```

Toglie metadati e commenti, riduce i decimali delle coordinate e **aggiunge il
`viewBox` se manca** — senza, l'SVG non si ridimensiona e nella pagina esce con
la sua dimensione nativa.

Per rigenerare l'elenco dei nomi attesi dal listone corrente:

```bash
.venv/bin/python -c "
import sys; sys.path.insert(0, 'src')
from asta.data.players import load_listone
from asta.domain.models import sort_key
for s in sorted({p.team for p in load_listone().players}):
    print(f'{s:<14} -> {sort_key(s).lower()}.svg')
"
```
