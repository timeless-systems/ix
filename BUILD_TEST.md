## Build

```bash
docker compose -f docker-compose.dev.yml -p danswer-stack up -d --pull always --force-recreate
docker compose -f docker-compose.dev.yml -p danswer-stack up -d --build --force-recreate
```

```bash
docker compose -f docker-compose.dev.yml -p danswer-stack down -v
```

## Test

cd backend

```bash
PYTHONPATH=. python3 danswer/connectors/langchain/connector.py
```