from collections.abc import Callable
from datetime import datetime
from datetime import timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from danswer.background.celery.celery_redis import RedisConnectorDeletion
from danswer.configs.app_configs import MAX_PRUNING_DOCUMENT_RETRIEVAL_PER_MINUTE
from danswer.configs.app_configs import MULTI_TENANT
from danswer.configs.constants import TENANT_ID_PREFIX
from danswer.connectors.cross_connector_utils.rate_limit_wrapper import (
    rate_limit_builder,
)
from danswer.connectors.interfaces import BaseConnector
from danswer.connectors.interfaces import LoadConnector
from danswer.connectors.interfaces import PollConnector
from danswer.connectors.interfaces import SlimConnector
from danswer.connectors.models import Document
from danswer.db.connector_credential_pair import get_connector_credential_pair
from danswer.db.engine import get_session_with_tenant
from danswer.db.enums import TaskStatus
from danswer.db.models import TaskQueueState
from danswer.redis.redis_pool import get_redis_client
from danswer.server.documents.models import DeletionAttemptSnapshot
from danswer.utils.logger import setup_logger


logger = setup_logger()


def _get_deletion_status(
    connector_id: int, credential_id: int, db_session: Session
) -> TaskQueueState | None:
    """We no longer store TaskQueueState in the DB for a deletion attempt.
    This function populates TaskQueueState by just checking redis.
    """
    cc_pair = get_connector_credential_pair(
        connector_id=connector_id, credential_id=credential_id, db_session=db_session
    )
    if not cc_pair:
        return None

    rcd = RedisConnectorDeletion(cc_pair.id)

    r = get_redis_client()
    if not r.exists(rcd.fence_key):
        return None

    return TaskQueueState(
        task_id="", task_name=rcd.fence_key, status=TaskStatus.STARTED
    )


def get_deletion_attempt_snapshot(
    connector_id: int, credential_id: int, db_session: Session
) -> DeletionAttemptSnapshot | None:
    deletion_task = _get_deletion_status(connector_id, credential_id, db_session)
    if not deletion_task:
        return None

    return DeletionAttemptSnapshot(
        connector_id=connector_id,
        credential_id=credential_id,
        status=deletion_task.status,
    )


def document_batch_to_ids(
    doc_batch: list[Document],
) -> set[str]:
    return {doc.id for doc in doc_batch}


def extract_ids_from_runnable_connector(
    runnable_connector: BaseConnector,
    progress_callback: Callable[[int], None] | None = None,
) -> set[str]:
    """
    If the PruneConnector hasnt been implemented for the given connector, just pull
    all docs using the load_from_state and grab out the IDs.

    Optionally, a callback can be passed to handle the length of each document batch.
    """
    all_connector_doc_ids: set[str] = set()

    if isinstance(runnable_connector, SlimConnector):
        for metadata_batch in runnable_connector.retrieve_all_slim_documents():
            all_connector_doc_ids.update({doc.id for doc in metadata_batch})

    doc_batch_generator = None

    if isinstance(runnable_connector, LoadConnector):
        doc_batch_generator = runnable_connector.load_from_state()
    elif isinstance(runnable_connector, PollConnector):
        start = datetime(1970, 1, 1, tzinfo=timezone.utc).timestamp()
        end = datetime.now(timezone.utc).timestamp()
        doc_batch_generator = runnable_connector.poll_source(start=start, end=end)
    else:
        raise RuntimeError("Pruning job could not find a valid runnable_connector.")

    doc_batch_processing_func = document_batch_to_ids
    if MAX_PRUNING_DOCUMENT_RETRIEVAL_PER_MINUTE:
        doc_batch_processing_func = rate_limit_builder(
            max_calls=MAX_PRUNING_DOCUMENT_RETRIEVAL_PER_MINUTE, period=60
        )(document_batch_to_ids)
    for doc_batch in doc_batch_generator:
        if progress_callback:
            progress_callback(len(doc_batch))
        all_connector_doc_ids.update(doc_batch_processing_func(doc_batch))

    return all_connector_doc_ids


def celery_is_listening_to_queue(worker: Any, name: str) -> bool:
    """Checks to see if we're listening to the named queue"""

    # how to get a list of queues this worker is listening to
    # https://stackoverflow.com/questions/29790523/how-to-determine-which-queues-a-celery-worker-is-consuming-at-runtime
    queue_names = list(worker.app.amqp.queues.consume_from.keys())
    for queue_name in queue_names:
        if queue_name == name:
            return True

    return False


def celery_is_worker_primary(worker: Any) -> bool:
    """There are multiple approaches that could be taken to determine if a celery worker
    is 'primary', as defined by us. But the way we do it is to check the hostname set
    for the celery worker, which can be done either in celeryconfig.py or on the
    command line with '--hostname'."""
    hostname = worker.hostname
    if hostname.startswith("primary"):
        return True

    return False


def get_all_tenant_ids() -> list[str] | list[None]:
    if not MULTI_TENANT:
        return [None]
    with get_session_with_tenant(tenant_id="public") as session:
        result = session.execute(
            text(
                """
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name NOT IN ('pg_catalog', 'information_schema', 'public')"""
            )
        )
        tenant_ids = [row[0] for row in result]

    valid_tenants = [
        tenant
        for tenant in tenant_ids
        if tenant is None or tenant.startswith(TENANT_ID_PREFIX)
    ]

    return valid_tenants
