#!/usr/bin/env python3
import os
import threading
import sys
import glob
from pathlib import Path
from typing import List
from multiprocessing import Pool
from tqdm import tqdm
import shutil
from typing import Any
from datetime import datetime
from datetime import datetime
from langchain.document_loaders import (
    CSVLoader,
    EverNoteLoader,
    PDFMinerLoader,
    TextLoader,
    GCSFileLoader,
    GCSDirectoryLoader,
    UnstructuredEmailLoader,
    UnstructuredEPubLoader,
    UnstructuredHTMLLoader,
    UnstructuredMarkdownLoader,
    UnstructuredODTLoader,
    UnstructuredPowerPointLoader,
    UnstructuredWordDocumentLoader,
)

from danswer.connectors.models import Document
from danswer.connectors.models import Section
from danswer.configs.app_configs import INDEX_BATCH_SIZE

from danswer.configs.app_configs import DOCS_SOURCE_DIRECTORY
from danswer.configs.app_configs import DOCS_PROCESSED_DIRECTORY
from danswer.connectors.interfaces import LoadConnector
from danswer.connectors.interfaces import GenerateDocumentsOutput
from danswer.connectors.file_ng.utils import check_folder

from danswer.utils.logger import setup_logger

_METADATA_FLAG = "#DANSWER_METADATA="

logger = setup_logger()

# Usage without socket connection (optional)
#  Load environment variables
# Custom document loaders

class MyElmLoader(UnstructuredEmailLoader):
    """Wrapper to fallback to text/plain whe/Users/ts1/development/vianai/HilaEnterprise/kombucha-backend/backend/utilsn default does not work"""

    def load(self) -> List[Document]:
        """Wrapper adding fallback for elm without html"""
        try:
            try:
                doc = UnstructuredEmailLoader.load(self)
            except ValueError as e:
                if 'text/html content not found in email' in str(e):
                    # Try plain text
                    self.unstructured_kwargs["content_source"] = "text/plain"
                    doc = UnstructuredEmailLoader.load(self)
                else:
                    raise
        except Exception as e:
            # Add file_path to exception message
            raise type(e)(f"{self.file_path}: {e}") from e

        return doc


class LangchainFileConnector(LoadConnector):
    def __init__(self,
                 file_locations: list[Path | str],
                 batch_size: int = INDEX_BATCH_SIZE,) -> None:

        folder_names_to_check = [
            DOCS_SOURCE_DIRECTORY,
            DOCS_PROCESSED_DIRECTORY,
        ]

        # Create a lock for thread-safe access to results list
        self.results_lock = threading.Lock()

        check_folder(folder_names_to_check)

# Map file extensions to document loaders and their arguments
        self.LOADER_MAPPING = {
            ".csv": (CSVLoader, {}),
            # ".docx": (Docx2txtLoader, {}),
            ".doc": (UnstructuredWordDocumentLoader, {}),
            ".docx": (UnstructuredWordDocumentLoader, {}),
            ".enex": (EverNoteLoader, {}),
            ".eml": (MyElmLoader, {}),
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

        documents = self._process_documents()

        # persist data
        if documents:
            logger.info('#######')
            logger.info(f"documents_langchain : {documents}")
            logger.info('#######')
            yield documents

    def _load_single_document_from_filesystem(self, file_path: str, results: List[Document]) -> None:
        logger.info(f"Loading {file_path}")
        
        try:
            ext = "." + file_path.rsplit(".", 1)[-1]
            if ext in self.LOADER_MAPPING:
                loader_class, loader_args = self.LOADER_MAPPING[ext]
                loader = loader_class(file_path, **loader_args)
                loaded_document = loader.load()[0]

                metadata = {}

                document = Document(
                    id=file_path,
                    sections=[Section(link=metadata.get("link", ""), text=loaded_document)],
                    source=file_path,
                    semantic_identifier=file_path,
                    metadata={},
                )

                timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
                original_file_name = os.path.basename(file_path)
                new_file_name = f"{timestamp}_{original_file_name}"
                destination_path = os.path.join(
                    DOCS_PROCESSED_DIRECTORY, new_file_name)

                shutil.move(file_path, destination_path)

                with self.results_lock:
                    results.append(document)

                logger.info(f"results {results}")

            else:
                raise ValueError(f"Unsupported file extension '{ext}'")
        except Exception as e:
            logger.error(f"An error occurred while loading {file_path}: {e}")
            

    def _load_documents_from_filesystem(self, source_dir: str, ignored_files: List[str] = []) -> List[Document]:
        """
        Loads all documents from the source documents directory, ignoring specified files
        """
        all_files = []
        for ext in self.LOADER_MAPPING:
            all_files.extend(
                glob.glob(os.path.join(
                    source_dir, f"**/*{ext}"), recursive=True)
            )
        filtered_files = [
            file_path for file_path in all_files if file_path not in ignored_files]

        logger.info(f"Found {len(filtered_files)} documents to be processed")

        results = []
        threads = []

        with tqdm(total=len(filtered_files), desc='Loading new documents ', ncols=80) as pbar:
            for file_path in filtered_files:
                logger.info(f"1")
                thread = threading.Thread(target=self._load_single_document_from_filesystem, args=(file_path, results))
                logger.info(f"2")
                thread.start()
                logger.info(f"3")

            # Wait for all threads to finish
            for thread in threading.enumerate():
                logger.info(f"4")
                if thread != threading.current_thread():
                    logger.info(f"5")
                    thread.join(timeout=30)   
                    logger.info(f"5")

        logger.info(f"6")
        logger.info(f"final results : {results}")
        return results

    def _process_documents(self, ignored_files: List[str] = []) -> List[Document]:
        """
        Load documents and split in chunks
        """

        logger.info(f"Loading documents from {DOCS_SOURCE_DIRECTORY}")
        documents = self._load_documents_from_filesystem(
            DOCS_SOURCE_DIRECTORY, ignored_files)

        logger.info(
            f"Loaded {len(documents)} documents from {DOCS_SOURCE_DIRECTORY}")

        if documents:
            print(f"documents : {documents}")
            return documents
        else:
            print(f"NOTHING")
            return None


if __name__ == "__main__":
    credentials = {}
    connector = LangchainFileConnector(file_locations=[
                                       '/Users/ts1/development/backend/utils/test_data'])
    connector.load_credentials(credentials)
    document_batches = connector.load_from_state()
    if document_batches:
        print("Documents found")
        print(next(document_batches))
    else:
        print("No documents found")
