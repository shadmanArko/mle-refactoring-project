# 00 · Problem

## Who hurts, and why

A person moving to the Seattle area wants to know **what a house is worth**
before negotiating. Today the only working answer is a Jupyter notebook that:

- mixes exploration, cleaning, features and modeling in one linear script,
- can only be run by someone who understands pandas,
- leaks information between train and test (see below),
- cannot be called by an app, so nobody else can use the model.

```mermaid
flowchart LR
    A[Notebook] -->|only a data scientist can run it| B[(Nobody else benefits)]
    A -.->|hidden leakage, hard-coded row ids| C[Numbers you can't fully trust]
```

## What we found in the notebook

| Finding | Why it matters | Our answer |
|---|---|---|
| `water_distance` is computed from every waterfront house, test rows included, before the split | Test data influences a training feature (leakage) | Fitted transformer: learns waterfront points from training rows only |
| A row is dropped by position (`drop(15856)`) | Breaks on any other dataset | Drop by rule: `bedrooms == 33` (training only) |
| Python loops over 21k rows (and 21k x 146 pairs) | Slow, hard to test | Vectorised code and a spatial index |
| Text says the target is price per sqft; code predicts `price` | Reader is misled | Follow the code: target is `price` |
| 177 house ids appear twice | A random split can put one house in train and test | Keep the notebook's split for parity, also report a split grouped by `id` |
| Model needs ~19 inputs | A person can't type that | A smaller "estimate" model with 6 plain questions |

## Product idea

One public link. A visitor answers six everyday questions and gets an
estimated price. The same page links to the code and to a short presentation
explaining how it was built.

```mermaid
flowchart LR
    V[Visitor] --> UI[One-page tester]
    UI -->|6 answers| API[FastAPI on AWS Lambda]
    API --> M[Model pipeline]
    M --> API -->|price + honest caveat| UI
    UI --- G[GitHub link]
    UI --- P[Presentation]
```

## Success criteria (how we will prove it)

| Question | Proof |
|---|---|
| Is the refactor faithful? | Pipeline output matches the notebook's frozen numbers (`tests/golden/`) |
| Is it leak-free? | A test shows test rows cannot change any fitted value |
| Is the model honest? | Metrics, baselines and the accuracy lost by the 6-question model are published |
| Can a non-technical person use it? | The deployed link works end to end from a phone |
| Is it safe to be public? | Input validation, throttling, no open write endpoints |

## Out of scope

Neural networks (a linear model with 19 tabular features does not need one),
live data refresh, user accounts.
