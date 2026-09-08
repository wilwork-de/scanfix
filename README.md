# scanfix

Strumenti da riga di comando per rimettere in ordine i documenti PDF: pulire la foto
di un foglio, aggiungere data e firma, e **verificare se un oscuramento regge davvero**.

*English: command-line tools for fixing up PDF documents — clean a phone photo of a
sheet of paper into something that looks scanned, add a date and signature block, and
check whether a redaction actually removed the content or merely drew a box over it.
Code and docs are in Italian; the tools are self-contained and the `--help` of each
one explains its flags.*

**Sito con il controllo redazione interattivo:** https://wilwork-de.github.io/scanfix/ —
gira interamente nel browser, il documento non viene caricato da nessuna parte.

---

## Il controllo della redazione

Un PDF non è un'immagine appiattita: è una pila di oggetti disegnati uno sull'altro.
Mettere un rettangolo nero sopra un nome **aggiunge** un oggetto, non ne toglie uno.
Il nome resta nel file, sotto, e si rilegge selezionandolo col mouse o con tre righe
di codice. È così che sono usciti atti giudiziari e documenti governativi che si
credevano censurati, e vale identico per i rettangoli di Word, per gli evidenziatori
e per i tool online che promettono di censurare un PDF.

```console
$ python3 tools/controlla_redazione.py documento.pdf
SOSPETTO  documento.pdf — 3 forme opache sopra contenuto ancora estraibile
  pagina 1  disegno  riquadro [56.0, 148.0, 156.3, 164.0]
     testo leggibile sotto: 'Nome: Mario Rossi'
  pagina 1  disegno  riquadro [56.0, 182.0, 244.8, 198.0]
     testo leggibile sotto: 'Codice fiscale: RSSMRA80A01H501U'
  pagina 1  disegno  riquadro [56.0, 216.0, 250.7, 232.0]
     testo leggibile sotto: 'IBAN: IT60X0542811101000000123456'
```

Esce con codice `1` quando trova una possibile fuga e `0` quando non trova niente,
quindi si può mettere in una pipeline o in un hook pre-commit.

### Perché mostra il testo invece di dare solo un verdetto

Un rettangolo pieno sopra del testo non è sempre una censura: una fascia colorata di
intestazione con la scritta bianca sopra, vista dal file, è la stessa identica cosa.
Mostrando *cosa* c'è sotto, la distinzione la fa una persona in un secondo — se è un
IBAN è una fuga, se è il titolo del documento è grafica. Distinguerle da sole
vorrebbe dire indovinare l'intenzione di chi ha impaginato, e lo strumento non ci
prova: fra i campioni di collaudo c'è anche il falso positivo, dichiarato.

### Come si oscura davvero

1. **Rimuovere invece di coprire**: `page.add_redact_annot(rect)` seguito da
   `page.apply_redactions()`.
2. **Oppure appiattire**: renderizzare la pagina in immagine, coprire, riesportare.
   Grezzo ma efficace, perché ricostruisce i pixel da zero.
3. **Ricontrollare il file finito.** Non è facoltativo, ed è il passaggio che salta
   chiunque abbia pubblicato un documento mal censurato.

---

## Gli strumenti

| Strumento | Cosa fa |
|---|---|
| `controlla_redazione.py` | Verifica se le coperture di un PDF nascondono davvero |
| `pulisci_scansione.py` | Da foto di un foglio a scansione pulita: toglie l'ombra, raddrizza la prospettiva, riporta su A4 |
| `estrai_firma.py` | Ritaglia una firma da una foto e la salva come PNG trasparente |
| `aggiungi_data_firma.py` | Aggiunge luogo, data e riga della firma in fondo a un PDF esistente |
| `foto_in_pdf.py` | Da una o più foto a un PDF A4 leggero, sotto un limite di peso |
| `genera_cv.py` | Genera un CV italiano in PDF da un dizionario di dati |

### Due cose che valgono più del codice

**La luce non uniforme si toglie dividendo, non schiarendo.** Fotografando un foglio
una metà prende luce e l'altra resta in ombra. Alzare la luminosità peggiora le cose,
perché schiarisce anche il testo. La *flat-field correction* sfoca via il contenuto
per ricavare la mappa della luce, poi ci divide sopra l'originale: correzione locale,
ogni zona trattata secondo la luce che ha ricevuto.

**Un foglio fotografato di sbieco è un trapezio, non un rettangolo ruotato.** Su un
caso reale l'inclinazione delle righe passava da 0.00° in cima a 1.00° in fondo:
nessuna rotazione singola può sistemarlo. `pulisci_scansione.py` misura due angoli,
costruisce il trapezio e lo rimanda a rettangolo con una trasformazione proiettiva,
iterando finché il residuo scende sotto 0.15° (misurato: 1.05° → 0.25° → 0.00°). Non
usa il bordo del foglio, che spesso non è rilevabile: ricava la geometria dal testo.

---

## Installazione

```bash
git clone https://github.com/wilwork-de/scanfix.git && cd scanfix
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python tools/controlla_redazione.py documento.pdf
```

L'ambiente virtuale non è pignoleria: su Debian e Ubuntu il Python di sistema è
protetto (PEP 668) e `pip install` diretto viene rifiutato, perché gli strumenti del
sistema operativo dipendono da quei pacchetti.

## Collaudo

```bash
PY=.venv/bin/python bash tests/prova.sh    # 10 asserzioni, versione Python
npm install && node tests/prova_js.mjs     # 10 asserzioni, versione JavaScript
```

I campioni di prova sono **generati**, non raccolti: `tests/genera_campioni.py`
costruisce cinque PDF con nomi e numeri inventati. Nessun documento reale, di
nessuno, entra in questo repository.

Le due suite girano sugli stessi campioni e devono dare gli **stessi verdetti**: il
file `docs/redaction-check.js` che gira nel sito è lo stesso collaudato da Node, non
una riscrittura parallela che può divergere in silenzio.

## Licenza

MIT.
