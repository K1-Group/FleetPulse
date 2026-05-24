# QuickBooks Online (QBO) integration

Centralized re-exports of QBO ingest/snapshot services.

## Usage

```python
from integrations.qbo import financial_snapshot, financial_feed_import
```

These re-export the modules at `services/qbo_*`. No behavior change vs the
existing services.
