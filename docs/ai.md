# AI & ML in Hisaab (all free, open source and local)

| Piece | What it does | Technology | Needs installing? |
|---|---|---|---|
| Entity extraction ("NER") | Reads bank narrations: mode, UPI id, reference/UTR, payee, bank, card digits, note, and a clean merchant name | Rule-based patterns (`services/extraction.py`) | No |
| ML categoriser | Picks a category for each transaction and learns from your corrections | scikit-learn: TF-IDF char + word n-grams → logistic regression (`services/ml.py`) | No (pip) |
| OCR | Reads scanned PDFs and photos of statements | RapidOCR (ONNX runtime, Apache-2.0) | No (pip) |
| Free-text statement parser | Finds transactions in PDF/DOCX/OCR text; decides debit vs credit from the running balance | `services/statement_text.py` | No |
| Local LLM (optional) | Answers "Ask your money" questions and categorises what ML is unsure about | Any OpenAI-compatible local server: **Ollama** (default), LM Studio, llama.cpp | Yes, optional |

## Why rules for extraction but ML for categories?

Indian bank narrations follow a handful of rigid formats (`UPI/DR/<ref>/<payee>/<bank>/<vpa>/<note>`,
`NEFT CR-<IFSC>-<name>-<note>-<UTR>`…). Explicit patterns are more accurate than a statistical NER model
here, need no training data, and are easy to debug. Categories depend on *you* (is "Rajesh Kumar"
rent or a friend?), which is what a model trained on your own choices is good at.

Example:

```
UPI/DR/425167812345/SWIGGY LIMITED/YESB/swiggy8@ybl/Food order
→ mode UPI · app PhonePe · vpa swiggy8@ybl · ref 425167812345 · note "Food order" · merchant Swiggy
→ category Food › Food delivery (ML 0.9)
```

## How categorisation decides

1. Your **rules** (Categories & rules → Smart rules)
2. The **merchant's default** (learned the first time you categorise a merchant)
3. The **ML model**: applied automatically at ≥ 55% confidence; between 30% and 55% it's shown as a
   suggestion chip
4. Built-in **keyword hints** for common Indian merchants
5. The **local LLM** (Settings → AI → "Categorise uncategorised"), only for items still uncertain, and only
   allowed to choose one of *your* categories

Every transaction records the winner (`category_source`) and confidence. The list shows "ML 87%",
"AI", or "rule". Imported and synced rows stay "to review" until you confirm them, and each
confirmation becomes training data.

**Training:** seeded with built-in examples, so it works from day one; retrained by the worker when you've
added 10+ new labels (or weekly), or on demand in Settings → AI. With 40+ of your own examples it reports
accuracy on your most recent 20%, measured honestly on data it didn't train on.

## Optional local LLM (Ollama)

1. Install Ollama from https://ollama.com (free). On a work laptop this may need IT approval.
2. `ollama pull qwen2.5:3b`. Around 2 GB. Qwen2.5 3B is Apache-2.0 licensed and handles tool calling.
   Alternatives: `llama3.2:3b`, `phi3.5`.
3. Keep Ollama running. Hisaab detects it (Settings → AI shows "Connected").

Settings in `backend/.env`: `LLM_ENABLED`, `LLM_BASE_URL` (default `http://localhost:11434/v1`), `LLM_MODEL`.

**Grounding:** in the assistant, the model can only *call tools* (spending, income, compare, top
merchants, subscriptions, budgets, net worth…). Every figure it states comes from those tool results,
and an answer that used no tool is rejected in favour of the rules engine. Without an LLM, the rules
engine answers the same common questions.

**Privacy:** by default the LLM runs on localhost, so nothing leaves your computer. If you point
`LLM_BASE_URL` at a remote server, Settings warns you, and transaction text would be sent there.

## Supported import formats

CSV · TSV · TXT (table or free text) · XLS · XLSX · HTML-as-XLS · OFX/QFX · JSON · DOCX (tables or
paragraphs) · PDF (tables → text → OCR, password-protected supported) · PNG/JPG/WEBP (OCR).
Old binary `.doc` isn't supported; save it as DOCX or PDF.

If a real statement parses badly, share a redacted copy (replace names and amounts, keep the layout) and
the parser can be tuned for it.
