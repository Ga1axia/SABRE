# Hosted read-only mirror

Deploy this separately. The Mac publishes outbound; nothing connects inbound to the agent host.

```bash
SABRE_MIRROR_TOKEN=... python -m core.web.mirror
```

The only write action is **kill**, which sets a flag the local watcher polls. Abuse is fail-safe: the company stops.
