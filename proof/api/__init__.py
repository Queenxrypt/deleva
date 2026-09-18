"""DELEVA backend API. Thin FastAPI layer over the deleva/ package -- every
route delegates to an existing Phase 1/2 service; no business logic,
strategy constants, risk math, or KeeperHub/Almanak request construction is
duplicated here."""
