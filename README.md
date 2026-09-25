# Real Estate Agents MVP

MVP autonomicznego systemu wieloagentowego do selekcji nieruchomości w Polsce. Projekt działa lokalnie na mockowanych integracjach zewnętrznych, ale ma gotowe granice modułów pod MCP, Google Maps, web search/scraping, parsery PDF, SQLite i ChromaDB.

## Uruchomienie

Wymagany Python 3.13.

```bash
pip install -e .
streamlit run app/ui/streamlit_app.py
```

Aby uruchomić MCP Web Search, to:
```bash
cd mcps\mcp-servers\web-search-mcp 
npm start
```
Opcjonalnie testy:

```bash
pip install -e ".[dev]"
pytest
```

CLI demo:

```bash
python -m app.main
```

## Architektura

Główna orkiestracja jest w `app/graph.py` i używa LangGraph. Pierwsze uruchomienie przechodzi przez:

1. `collect_criteria`
2. `researcher_discovery`
3. `logistics_filter`
4. `parallel_enrichment`
5. `hitl_checkpoint`

Checkpoint HITL kończy graf statusem `hitl_waiting`. UI zapisuje `GraphState` w sesji Streamlit. Po decyzji użytkownika graf wznawia stan:

- `accepted` → `legal_deep_dive` → `final_synthesis`
- `revise` → ponowne discovery po zmianie kryteriów
- `rejected` → zakończenie bez rankingu

Agenci:

- `Researcher` znajduje i normalizuje oferty, ekstrahuje rok budowy i stan.
- `Logistics Expert` geokoduje, znajduje najbliższą czynną stację PKP i liczy dojazd.
- `Market Analyst` liczy PLN/m2, benchmark i atrakcyjność cenową.
- `Legal & Planning Scout` robi screening MPZP oraz deep dive dokumentów PDF.
- `Environmental Auditor` ocenia zieleń i hałas.
- `Orchestrator` składa ranking i zapisuje stan.

## Persystencja

- SQLite: `app/db/sqlite.py`, snapshoty `GraphState` i oferty.
- ChromaDB: `app/db/chroma.py`, lokalne embeddingi deterministyczne bez pobierania modelu.

Domyślna baza: `real_estate_agents.db`. Domyślny katalog Chroma: `.chroma`.

## Integracje i mocki

MVP działa bez kluczy API. Abstrakcje MCP znajdują się w `app/tools/mcp_clients.py`:

- `MCPWebSearchClient`
- `MCPGoogleMapsClient`
- `MCPPDFClient`
- `MCPDatabaseClient`

Jeśli endpoint MCP albo klucz API nie jest skonfigurowany, system używa deterministycznych mocków i dopisuje ostrzeżenia do analiz.

## Zmienne środowiskowe

Skopiuj `.env.example` do `.env`, jeśli chcesz zmienić domyślne ustawienia.

- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `TAVILY_API_KEY`
- `FIRECRAWL_API_KEY`
- `GOOGLE_MAPS_API_KEY`
- `MCP_WEB_SEARCH_URL`
- `MCP_GOOGLE_MAPS_URL`
- `MCP_PDF_URL`
- `MCP_DATABASE_URL`
- `DATABASE_URL`
- `CHROMA_PERSIST_DIR`
- `REQUESTS_PER_MINUTE`
- `MAX_RETRIES`
- `ENABLE_MOCKS`

## Error handling

System zapisuje błędy w `GraphState.errors`. Brak roku budowy kończy się `Unknown`/warningiem, brak Google Maps przełącza na mock geocoder, nieczytelny PDF zostawia ostrzeżenie w analizie legalnej, a brak wyników lub shortlisty uruchamia `self_correction` z poluzowanym limitem PKP.

## Koszty i rate limiting

`CostTracker` liczy prompt/completion tokens, koszt per agent i sumę w UI. `RateLimiter` ogranicza liczbę zapytań na minutę i wykonuje retry z exponential backoff.
