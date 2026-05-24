# Geotab integration

Centralized wrapper for Geotab API access. Today this re-exports the existing
`backend/geotab_client.py` module unchanged — no behavior change.

## Usage

```python
from integrations.geotab import client as geotab_client
```

## Future moves

When safe, move `backend/geotab_client.py` into this package as `client.py`
and update top-level imports via a compatibility shim. Not done in this
restructure pass to keep risk low.
