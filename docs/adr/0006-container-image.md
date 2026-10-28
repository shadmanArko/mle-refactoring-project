# ADR-0006 · Train the model inside the image build; run it with almost no privileges

Status: accepted

## Context

The service needs a model file. Where it comes from decides whether the deployed model
can drift from the deployed code, and how reproducible a release is.

## Options

```mermaid
flowchart TD
    Q[Where does the model come from?] --> A[Copy a file from a laptop]
    Q --> B[Download from storage at start-up]
    Q --> C[Train inside the image build]
    A --> A1[Fast, but untracked: nobody can say<br/>which code and data made it]
    B --> B1[Needs storage, credentials and a slower cold start]
    C --> C1[Slower build, but the image is self-contained<br/>and provably matches its code]
```

## Decision

Train inside the build (option C), in its own stage, and copy **only the model files**
into the runtime image. Training is seeded, so the same inputs produce the same model;
the in-image run reproduced the local metrics exactly.

Run the container as a non-root user, with a read-only filesystem, no Linux
capabilities and no new privileges. The database is reachable only on the Compose
network.

## Consequences

- (+) One immutable artefact per commit; the commit is recorded in the model metadata.
- (+) No model storage, no credentials, no download at cold start. This matters on
  AWS Lambda.
- (-) A source change retrains (about three minutes). Acceptable at this size; revisit
  with a model registry if training grows.
- (-) The image is 805 MB. Fine for Lambda container images (limit 10 GB).
