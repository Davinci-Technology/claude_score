# Operator scoring reference — MovieDeck

**Operator-only.** The candidate-facing README in the
[movie_deck](https://github.com/Davinci-Technology/movie_deck) repo describes
the same expectations as user-journey prose, with no point values and no
implementation hints. This file is the version operators use when filling in
the Progress component of the rubric (see [`../SCORING.md`](../SCORING.md)).

## Menu total

**~53 points.** Progress mark = `min(35, points × 35 / 53)`.

## Items

Each item shows the point value and, in parentheses, the typical
implementation a candidate would reach for. The typicals are *not*
requirements — credit the item if the behaviour exists, regardless of
how it's built.

### Foundation
| # | Pts | Behaviour at submission time | Typical |
|---|---:|---|---|
| F1 | 3 | User can search the catalog and see results in the UI | direct TMDB call from backend |
| F2 | 2 | User can open a movie and see its metadata (poster, year, overview, rating) | detail endpoint + page |

### Backend
| # | Pts | Behaviour at submission time | Typical |
|---|---:|---|---|
| B1 | 3 | User can save a movie to their deck and remove it later; persists across reload | `Deck` model + CRUD endpoints |
| B2 | 3 | User can rate movies (1–5) and attach a short note; persists | rating field + serializer |
| B3 | 3 | User can slice their deck by some sensible attribute(s) | query params on list endpoint |
| B4 | 4 | App stays fast / resilient when TMDB is rate-limited or flaky | server-side response cache |
| B5 | 2 | API is discoverable without source-diving | drf-spectacular OpenAPI |
| B6 | 2 | List endpoint stays performant past ~100 items | server-side pagination |

### Frontend
| # | Pts | Behaviour at submission time | Typical |
|---|---:|---|---|
| UI1 | 3 | List view looks like a real product, not a debug page | grid with posters + metadata |
| UI2 | 3 | Controls let the user slice without page reloads | client-side filter UI wired to API |
| UI3 | 3 | Actions feel instant — no waiting on the network to react | optimistic updates |
| UI4 | 2 | Loading / empty / error states are handled gracefully | proper state handling per request |
| UI5 | 2 | Usable at phone-width | responsive CSS |

### Stretch
| # | Pts | Behaviour at submission time | Typical |
|---|---:|---|---|
| S1 | 5 | Multiple users; each has their own private deck | Django auth + per-user filtering |
| S2 | 4 | App suggests movies based on what's in the deck | naïve similarity over genres/decades |
| S3 | 3 | User can see the history of changes to their deck | activity log model |
| S4 | 5 | Two browsers on the same deck stay in sync without refresh | WebSockets / SSE / polling |
| S5 | 3 | Someone else can bring up the whole app with a single command | full Dockerization |
| S6 | 3 | Core flows protected against regression | backend tests |

## Scoring notes

- An item counts if the **behaviour** works end-to-end at submission time —
  not if the candidate mentioned doing it or started a branch for it. Use
  the running app + `solution.patch` as evidence.
- Partial credit is allowed but should be the exception (e.g. add works but
  delete is broken → 2/3 on B1). When in doubt, ask "would I merge this
  into a teammate's PR as-is?" — if yes, full credit.
- TypeScript strict mode is **not** here. It lives in
  [`../HIDDEN_RUBRIC.md`](../HIDDEN_RUBRIC.md) as a code-quality signal, not
  a feature on the menu.
- The candidate's README contains no points and no library names. They
  arrived at their feature list by reading the prose user journeys and
  forming their own. Score the behaviour they shipped against this menu;
  do not penalise them for choosing different language than ours.
