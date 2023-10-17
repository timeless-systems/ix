import os

#####
# Connector Configs
#####

LANGCHAIN_CONNECTOR_TMP_STORAGE_PATH = os.environ.get(
    "LANGCHAIN_CONNECTOR_TMP_STORAGE_PATH", "/home/file_connector_storage"
)

## LANGCHAIN_FILE
DOCS_SOURCE_DIRECTORY = os.environ.get('DOCS_SOURCE_DIRECTORY', '/home/file_ng_connector_storage/source_documents')
DOCS_PROCESSED_DIRECTORY = os.environ.get('DOCS_PROCESSED_DIRECTORY', '/home/file_connector_storage/processed_documents')