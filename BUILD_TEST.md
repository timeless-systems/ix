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

## New connector

### Add connector
factory.py

```python
from danswer.connectors.file_ng.connector import LocalFileNGConnector

.
.
.

DocumentSource.FILE_NG: LocalFileNGConnector,

```

constants.py

```python
class DocumentSource(str, Enum):
.
.
.

FILE_NG = "file_ng"

```

### WEB Api

### WEB UI

new folder in web/src/app/admin/connectors/xxxxx

page.tx

``` file_ng
documents : [Document(id='/home/file_connector_storage/2025.txt', sections=[Section(link='', text='2025 wird Bayern Muenchen Meister und nicht der BVB aus Dortmund')], source=<DocumentSource.FILE_NG: 'file_ng'>, semantic_identifier='/home/file_connector_storage/2025.txt', metadata={})]
```

``` file
documents : [Document(id='2024.txt', sections=[Section(link='', text='2024 wird Bayern Muenchen Meister und nicht der BVB aus Dortmund')], source=<DocumentSource.FILE: 'file'>, semantic_identifier='2024.txt', metadata={})]
```
