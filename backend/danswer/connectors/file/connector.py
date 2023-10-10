import os
from collections.abc import Generator
from pathlib import Path
from typing import Any
from typing import IO

from PyPDF2 import PdfReader

from danswer.configs.app_configs import INDEX_BATCH_SIZE
from danswer.configs.constants import DocumentSource
from danswer.connectors.cross_connector_utils.file_utils import load_files_from_zip
from danswer.connectors.cross_connector_utils.file_utils import read_file
from danswer.connectors.file.utils import check_file_ext_is_valid
from danswer.connectors.file.utils import get_file_ext
from danswer.connectors.interfaces import GenerateDocumentsOutput
from danswer.connectors.interfaces import LoadConnector
from danswer.connectors.models import Document
from danswer.connectors.models import Section
from danswer.utils.logger import setup_logger


logger = setup_logger()


def _open_files_at_location(
    file_path: str | Path,
) -> Generator[tuple[str, IO[Any]], Any, None]:
    extension = get_file_ext(file_path)

    if extension == ".zip":
        for file_info, file in load_files_from_zip(file_path, ignore_dirs=True):
            yield file_info.filename, file
    elif extension == ".txt" or extension == ".pdf":
        mode = "r"
        if extension == ".pdf":
            mode = "rb"
        with open(file_path, mode) as file:
            yield os.path.basename(file_path), file
    else:
        logger.warning(f"Skipping file '{file_path}' with extension '{extension}'")


def _process_file(file_name: str, file: IO[Any]) -> list[Document]:
    extension = get_file_ext(file_name)
    if not check_file_ext_is_valid(extension):
        logger.warning(f"Skipping file '{file_name}' with extension '{extension}'")
        return []

    metadata: dict[str, Any] = {}
    file_content_raw = ""
    if extension == ".pdf":
        pdf_reader = PdfReader(file)
        if not pdf_reader.is_encrypted:
            file_content_raw = "\n".join(
                page.extract_text() for page in pdf_reader.pages
            )
    else:
        file_content_raw, metadata = read_file(file)

    return [
        Document(
            id=file_name,
            sections=[Section(link=metadata.get("link", ""), text=file_content_raw)],
            source=DocumentSource.FILE,
            semantic_identifier=file_name,
            metadata={},
        )
    ]


class LocalFileConnector(LoadConnector):
    def __init__(
        self,
        file_locations: list[Path | str],
        batch_size: int = INDEX_BATCH_SIZE,
    ) -> None:
        self.file_locations = [Path(file_location) for file_location in file_locations]
        self.batch_size = batch_size

    def load_credentials(self, credentials: dict[str, Any]) -> dict[str, Any] | None:
        pass

    def load_from_state(self) -> GenerateDocumentsOutput:
        documents: list[Document] = []
        for file_location in self.file_locations:
            files = _open_files_at_location(file_location)

            for file_name, file in files:
                documents.extend(_process_file(file_name, file))

                if len(documents) >= self.batch_size:
                    yield documents
                    documents = []

        if documents:
            yield documents
