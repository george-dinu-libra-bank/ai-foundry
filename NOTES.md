# Assignment 2 — NOTES

## Chunking — același text, patru strategii (folder 1 Postman)

Input identic pentru toate cele patru cereri `POST /chunk`:

| Strategie | Chunks |
|---|---|
| static | 3 |
| sentence | 3 |
| dynamic | 2 |
| semantic | 7 |

`semantic` produce cele mai multe bucăți pentru că taie unde se schimbă sensul
(embedează fiecare propoziție), iar `dynamic` cele mai puține pentru că împachetează
propoziții întregi până la un buget de dimensiune.

---

## Cele patru întrebări de acceptare (Partea 3)

### 1. Câte dimensiuni are un embedding aici?

**1536** — câmpul `vector_dimension` din răspunsul lui `POST /ingest`, confirmat și de
`GET /collection`. Vine de la deployment-ul `text-embedding-3-small` din Foundry.

### 2. Ce scor a primit interogarea off-topic și ce îmi spune asta?

| Query | Cel mai bun scor |
|---|---|
| `my card got frozen, what do I do?` | **0.3781** |
| `what is the weather in Cluj?` | **0.0867** |

Deci: dacă întrebarea nu are legătură cu datele salvate în colecție, scorul returnat
este mult mai mic. Retrieval-ul **întoarce întotdeauna ceva** — nu spune niciodată „nu
am găsit" — așa că scorul e singurul lucru care îmi spune dacă rezultatul înseamnă
ceva. 0.3781 pe o parafrază („frozen" vs „blocked", fără nici un cuvânt comun) e un hit
real; 0.0867 e zgomot.

### 3. Ce se adaugă exact în prompt când `use_rag` este `true`?

Când folosesc chat-ul cu `use_rag: true`, răspunsul e construit pe baza a ceea ce e
salvat în embeddings: pasajele recuperate din colecție sunt inserate în `prompt_sent`,
numerotate, iar modelul e instruit să răspundă doar din ele și să citeze `[1]`, `[2]`.

Când folosesc chat-ul fără RAG, `prompt_sent` conține doar întrebarea mea — răspunsul
este generic, generat din memoria generală a modelului, fluent și plauzibil, dar
nesusținut de nici o sursă din corpusul meu.

Diferența dintre cele două valori ale `prompt_sent` *este* RAG.

### 4. Unde poate rula agentul `lyrical` și de unde știu?

Din câmpul `runs_on` al fiecărei persone în `GET /agents`, plus blocul `foundry` din
același răspuns, care spune dacă Agent Service a putut fi interogat.

- **În Docker:** Foundry apare ca `unknown` — containerul se autentifică cu cheie, iar
  Agent Service acceptă doar Microsoft Entra, deci răspunsul cinstit e „nu știu", nu
  „nu e deployat".
- **Local, după `az login`:** aplicația împrumută identitatea mea, badge-urile se
  rezolvă în *local only* / *local + Foundry*.
- După `POST /agents/lyrical/deploy` (care merge doar local, cu identitate), `lyrical`
  trece pe `runs_on: both` — adică poate rula și în procesul meu, și găzduit în Foundry.

Același cod, aceeași configurație — diferă doar banda de autentificare, în funcție de
unde rulează.
