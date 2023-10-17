import json
import os
import zipfile
from collections.abc import Generator
from pathlib import Path
from typing import Any
from typing import IO

from danswer.configs.app_configs import INDEX_BATCH_SIZE
from danswer.configs.constants import DocumentSource
from danswer.connectors.file_ng.utils import get_file_ext
from danswer.connectors.interfaces import GenerateDocumentsOutput
from danswer.connectors.interfaces import LoadConnector
from danswer.connectors.models import Document
from danswer.connectors.models import Section
from danswer.utils.logger import setup_logger
from langchain.document_loaders import (
    CSVLoader,
    EverNoteLoader,
    PDFMinerLoader,
    TextLoader,
    UnstructuredEPubLoader,
    UnstructuredHTMLLoader,
    UnstructuredMarkdownLoader,
    UnstructuredODTLoader,
    UnstructuredPowerPointLoader,
    UnstructuredWordDocumentLoader,
)

logger = setup_logger()

_METADATA_FLAG = "#DANSWER_METADATA="

def _process_file(self, file_name: str) -> list[Document]:
    logger.info(f"file_name : {file_name}")
    extension = get_file_ext(file_name)

    logger.debug(f"self.LOADER_MAPPING : {self.LOADER_MAPPING}")
    if extension in self.LOADER_MAPPING:
        loader_class, loader_args = self.LOADER_MAPPING[extension]
        loader = loader_class(file_name, **loader_args)
        loaded_document = loader.load()[0]

        if loaded_document:
            logger.info(f"loaded_document : {loaded_document}")
        else:
            logger.error (f"Nothing loaded")    

        metadata = {}

        return [
            Document(
                id=file_name,
                sections=[Section(link=metadata.get("link", ""), text=loaded_document.page_content)],
                source=DocumentSource.FILE_NG,
                semantic_identifier=file_name,
                metadata={},
            )
        ]

    else:
        logger.error(f"File extension {extension} not supported")
        logger.error(f"File name {file_name}")

class LocalFileNGConnector(LoadConnector):
    def __init__(
        self,
        file_locations: list[Path | str],
        batch_size: int = INDEX_BATCH_SIZE,
    ) -> None:
        self.file_locations = [Path(file_location) for file_location in file_locations]
        self.batch_size = batch_size

# Map file extensions to document loaders and their arguments
        self.LOADER_MAPPING = {
            ".csv": (CSVLoader, {}),
            # ".docx": (Docx2txtLoader, {}),
            ".doc": (UnstructuredWordDocumentLoader, {}),
            ".docx": (UnstructuredWordDocumentLoader, {}),
            ".enex": (EverNoteLoader, {}),
            ".epub": (UnstructuredEPubLoader, {}),
            ".html": (UnstructuredHTMLLoader, {}),
            ".md": (UnstructuredMarkdownLoader, {}),
            ".odt": (UnstructuredODTLoader, {}),
            ".pdf": (PDFMinerLoader, {}),
            ".ppt": (UnstructuredPowerPointLoader, {}),
            ".pptx": (UnstructuredPowerPointLoader, {}),
            ".txt": (TextLoader, {"encoding": "utf8"}),
            # Add more mappings for other file extensions and loaders as needed
        }

    def load_credentials(self, credentials: dict[str, Any]) -> dict[str, Any] | None:
        pass

    def load_from_state(self) -> GenerateDocumentsOutput:
        documents: list[Document] = []
        logger.info(f"file_name : {self.file_locations}")

        for file_location in self.file_locations:

# Convert PosixPath object to string
            file_location_str = str(file_location)

            logger.info(f"file_location : {file_location_str}")

            documents.extend(_process_file(self, file_location_str))

            logger.info(f"documents : {documents}")
            logger.info(f"len documents : {len(documents)}")
            logger.info(f"self.batch_size : {self.batch_size}")

            if len(documents) >= self.batch_size:
                yield documents
                documents = []

        if documents:
            logger.info('*****')
            logger.info(f"documents : {documents}")
            logger.info('*****')
            yield documents

if __name__ == "__main__":
    credentials = {}
    connector = LocalFileNGConnector(file_locations=[
                                       '/Users/ts1/development/ts/ix/test/docs/2023.txt'])
    connector.load_credentials(credentials)
    document_batches = connector.load_from_state()
    if document_batches:
        print("Documents found")
        print(next(document_batches))
    else:
        print("No documents found")
