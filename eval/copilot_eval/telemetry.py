"""Explicit benchmark tracing; no ambient tracing or production capture changes."""

from contextlib import contextmanager
from uuid import UUID, uuid4

from langsmith import tracing_context
from langsmith.run_trees import RunTree
from pydantic import BaseModel

from src import observability as obs


def serial(value):
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(k): serial(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serial(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value) if type(value).__module__ == "datetime" else None


def snapshot(state):
    return {k: serial(v) for k, v in state.items() if k in obs._STATE_CONTENT_FIELDS}


@contextmanager
def graph_case(service, case, run_id, example_id=None, observer=None):
    """Graph smoke runs have the same controlled tracer as HTTP requests."""
    request_id = uuid4().hex
    root = (
        RunTree(
            id=UUID(request_id),
            name="copilot.eval",
            run_type="chain",
            project_name=service.project,
            ls_client=service.client,
            inputs={"query": case["query"], "target_date": case.get("target_date")},
            reference_example_id=example_id,
            extra={"metadata": {"case_id": case["case_id"], "evaluation_run_id": run_id}},
        )
        if service.enabled
        else None
    )
    scope = obs.RequestTelemetry(request_id, service, root=root, content_allowed=True, workflow_content=True)
    scope.metadata.update(case_id=case["case_id"], evaluation_run_id=run_id)
    if root:
        root.post()
        scope.tracer = obs.SafeTracer(scope)
    token = obs._request.set(scope)
    observer_token = obs.node_observer.set(observer)
    try:
        with tracing_context(parent=root, client=service.client, enabled=root is not None):
            yield scope
    except BaseException as exc:
        if root:
            root.end(error=type(exc).__name__)
        raise
    finally:
        if root:
            if not root.end_time:
                root.end()
            root.patch()
        obs.node_observer.reset(observer_token)
        obs._request.reset(token)
