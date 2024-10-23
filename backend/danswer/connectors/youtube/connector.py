import io
import ipaddress
import socket
from datetime import datetime
from datetime import timezone
from enum import Enum
from typing import Any
from typing import cast
from typing import Tuple
from urllib.parse import urljoin
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from oauthlib.oauth2 import BackendApplicationClient
from playwright.sync_api import BrowserContext
from playwright.sync_api import Playwright
from playwright.sync_api import sync_playwright
from requests_oauthlib import OAuth2Session
from urllib3.exceptions import MaxRetryError
from pytube import YouTube

from danswer.configs.app_configs import INDEX_BATCH_SIZE
from danswer.configs.app_configs import WEB_CONNECTOR_OAUTH_CLIENT_ID
from danswer.configs.app_configs import WEB_CONNECTOR_OAUTH_CLIENT_SECRET
from danswer.configs.app_configs import WEB_CONNECTOR_OAUTH_TOKEN_URL
from danswer.configs.app_configs import WEB_CONNECTOR_VALIDATE_URLS
from danswer.configs.constants import DocumentSource
from danswer.connectors.interfaces import GenerateDocumentsOutput
from danswer.connectors.interfaces import LoadConnector
from danswer.connectors.models import Document
from danswer.connectors.models import Section
from danswer.file_processing.extract_file_text import read_pdf_file
from danswer.file_processing.html_utils import web_html_cleanup
from danswer.utils.logger import setup_logger
from danswer.utils.sitemap import list_pages_for_site

logger = setup_logger()

class WEB_CONNECTOR_VALID_SETTINGS(str, Enum):
    RECURSIVE = "recursive"
    SINGLE = "single"
    SITEMAP = "sitemap"
    UPLOAD = "upload"

def protected_url_check(url: str) -> None:
    if not WEB_CONNECTOR_VALIDATE_URLS:
        return
    parse = urlparse(url)
    if parse.scheme != "http" and parse.scheme != "https":
        raise ValueError("URL must be of scheme https?://")
    if not parse.hostname:
        raise ValueError("URL must include a hostname")
    try:
        info = socket.getaddrinfo(parse.hostname, None)
    except socket.gaierror as e:
        raise ConnectionError(f"DNS resolution failed for {parse.hostname}: {e}")
    for address in info:
        ip = address[4][0]
        if not ipaddress.ip_address(ip).is_global:
            raise ValueError(
                f"Non-global IP address detected: {ip}, skipping page {url}. "
                f"The Web Connector is not allowed to read loopback, link-local, or private ranges"
            )

def check_internet_connection(url: str) -> None:
    try:
        response = requests.get(url, timeout=3)
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code if e.response is not None else -1
        error_msg = {
            400: "Bad Request",
            401: "Unauthorized",
            403: "Forbidden",
            404: "Not Found",
            500: "Internal Server Error",
            502: "Bad Gateway",
            503: "Service Unavailable",
            504: "Gateway Timeout",
        }.get(status_code, "HTTP Error")
        raise Exception(f"{error_msg} ({status_code}) for {url} - {e}")
    except requests.exceptions.SSLError as e:
        cause = (
            e.args[0].reason
            if isinstance(e.args, tuple) and isinstance(e.args[0], MaxRetryError)
            else e.args
        )
        raise Exception(f"SSL error {str(cause)}")
    except (requests.RequestException, ValueError) as e:
        raise Exception(f"Unable to reach {url} - check your internet connection: {e}")

def is_valid_url(url: str) -> bool:
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

def download_youtube_video(url: str, output_path: str) -> None:
    try:
        yt = YouTube(url)
        stream = yt.streams.get_highest_resolution()
        stream.download(output_path=output_path)
        print(f"视频已下载到 {output_path}")
    except Exception as e:
        print(f"下载视频时出错: {e}")

def fetch_youtube_metadata(url: str) -> dict:
    metadata = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.goto(url)
        
        metadata['title'] = page.title()
        metadata['description'] = page.query_selector("meta[name='description']")?.get_attribute("content")
        metadata['favico'] = page.query_selector("link[rel='icon']")?.get_attribute("href")
        
        browser.close()
    return metadata

class YoutubeConnector(LoadConnector):
    def __init__(
        self,
        base_url: str,
        web_connector_type: str = WEB_CONNECTOR_VALID_SETTINGS.RECURSIVE.value,
        mintlify_cleanup: bool = True,
        batch_size: int = INDEX_BATCH_SIZE,
    ) -> None:
        self.mintlify_cleanup = mintlify_cleanup
        self.batch_size = batch_size
        self.recursive = False

        if web_connector_type == WEB_CONNECTOR_VALID_SETTINGS.RECURSIVE.value:
            self.recursive = True
            self.to_visit_list = [_ensure_valid_url(base_url)]
            return

        elif web_connector_type == WEB_CONNECTOR_VALID_SETTINGS.SINGLE.value:
            self.to_visit_list = [_ensure_valid_url(base_url)]

        elif web_connector_type == WEB_CONNECTOR_VALID_SETTINGS.SITEMAP:
            self.to_visit_list = extract_urls_from_sitemap(_ensure_valid_url(base_url))

        elif web_connector_type == WEB_CONNECTOR_VALID_SETTINGS.UPLOAD:
            logger.warning(
                "This is not a UI supported Web Connector flow, "
                "are you sure you want to do this?"
            )
            self.to_visit_list = _read_urls_file(base_url)

        else:
            raise ValueError(
                "Invalid Web Connector Config, must choose a valid type between: " ""
            )

    def load_credentials(self, credentials: dict[str, Any]) -> dict[str, Any] | None:
        if credentials:
            logger.warning("Unexpected credentials provided for Web Connector")
        return None

    def load_from_state(self) -> GenerateDocumentsOutput:
        """Traverses through all pages found on the website
        and converts them into documents"""
        visited_links: set[str] = set()
        to_visit: list[str] = self.to_visit_list

        if not to_visit:
            raise ValueError("No URLs to visit")

        base_url = to_visit[0]  # For the recursive case
        doc_batch: list[Document] = []

        # Needed to report error
        at_least_one_doc = False
        last_error = None

        playwright, context = start_playwright()
        restart_playwright = False
        while to_visit:
            current_url = to_visit.pop()
            if current_url in visited_links:
                continue
            visited_links.add(current_url)

            try:
                protected_url_check(current_url)
            except Exception as e:
                last_error = f"Invalid URL {current_url} due to {e}"
                logger.warning(last_error)
                continue

            logger.info(f"Visiting {current_url}")

            try:
                check_internet_connection(current_url)
                if restart_playwright:
                    playwright, context = start_playwright()
                    restart_playwright = False

                if current_url.split(".")[-1] == "pdf":
                    # PDF files are not checked for links
                    response = requests.get(current_url)
                    page_text, metadata = read_pdf_file(
                        file=io.BytesIO(response.content)
                    )
                    last_modified = response.headers.get("Last-Modified")

                    doc_batch.append(
                        Document(
                            id=current_url,
                            sections=[Section(link=current_url, text=page_text)],
                            source=DocumentSource.WEB,
                            semantic_identifier=current_url.split("/")[-1],
                            metadata=metadata,
                            doc_updated_at=_get_datetime_from_last_modified_header(
                                last_modified
                            )
                            if last_modified
                            else None,
                        )
                    )
                    continue

                page = context.new_page()
                page_response = page.goto(current_url)
                last_modified = (
                    page_response.header_value("Last-Modified")
                    if page_response
                    else None
                )
                final_page = page.url
                if final_page != current_url:
                    logger.info(f"Redirected to {final_page}")
                    protected_url_check(final_page)
                    current_url = final_page
                    if current_url in visited_links:
                        logger.info("Redirected page already indexed")
                        continue
                    visited_links.add(current_url)

                content = page.content()
                soup = BeautifulSoup(content, "html.parser")

                if self.recursive:
                    internal_links = get_internal_links(base_url, current_url, soup)
                    for link in internal_links:
                        if link not in visited_links:
                            to_visit.append(link)

                if page_response and str(page_response.status)[0] in ("4", "5"):
                    last_error = f"Skipped indexing {current_url} due to HTTP {page_response.status} response"
                    logger.info(last_error)
                    continue

                parsed_html = web_html_cleanup(soup, self.mintlify_cleanup)

                doc_batch.append(
                    Document(
                        id=current_url,
                        sections=[
                            Section(link=current_url, text=parsed_html.cleaned_text)
                        ],
                        source=DocumentSource.WEB,
                        semantic_identifier=parsed_html.title or current_url,
                        metadata={},
                        doc_updated_at=_get_datetime_from_last_modified_header(
                            last_modified
                        )
                        if last_modified
                        else None,
                    )
                )

                page.close()
            except Exception as e:
                last_error = f"Failed to fetch '{current_url}': {e}"
                logger.exception(last_error)
                playwright.stop()
                restart_playwright = True
                continue

            if len(doc_batch) >= self.batch_size:
                playwright.stop()
                restart_playwright = True
                at_least_one_doc = True
                yield doc_batch
                doc_batch = []

        if doc_batch:
            playwright.stop()
            at_least_one_doc = True
            yield doc_batch

        if not at_least_one_doc:
            if last_error:
                raise RuntimeError(last_error)
            raise RuntimeError("No valid pages found.")


if __name__ == "__main__":
    connector = WebConnector("https://docs.danswer.dev/")
    document_batches = connector.load_from_state()
    print(next(document_batches))
