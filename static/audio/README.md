# Audio della Soundbar

I file di questa cartella diventano i pulsanti della **Soundbar**, nella barra laterale
dell'app. Per aggiungerne uno
basta lasciarlo qui: non c'è niente da modificare nel codice.

## Dove metterlo

| Cartella | Cosa contiene |
|---|---|
| `calcio/` | calciatori e allenatori |
| `amici/` | voci del gruppo |

## Come chiamarlo

Trattini al posto degli spazi, tutto minuscolo, e **il nome di chi parla davanti**: diventa
l'etichetta verde sopra la frase, uguale nelle due cartelle.

```
calcio/allegri-buona-giornata.mp3   →   ALLEGRI  ·  Buona giornata
amici/carlo-passa-la-palla.m4a      →   CARLO    ·  Passa la palla
amici/fischio.m4a                   →   Fischio          (una parola sola: nessuna etichetta)
```

Il nome è **sempre la prima parola**: un file di più parole senza un nome davanti si prende
comunque la prima come etichetta (`che-bella-giornata.m4a` diventa «CHE · Bella giornata»).
Per un pulsante senza etichetta verde, tieni il titolo in una parola sola.

Il resto tiene la sola iniziale maiuscola: `carlo-passa-la-palla` dà «Passa la palla», non «Passa La
Palla». Gli accenti si possono scrivere nel nome del file (`domani-è-impossibile.mp3`) e vengono
conservati.

Formati riconosciuti: `.mp3`, `.m4a`, `.wav`, `.ogg`, `.opus`.

## Peso

I file si scaricano **solo quando si preme il pulsante**, uno alla volta, e restano nella cache
del browser. Chi guarda l'asta senza toccare la Soundbar non ne scarica nemmeno uno: conta,
visto che tutti sono in rete dati. Tienili comunque corti — sono battute, non podcast.
