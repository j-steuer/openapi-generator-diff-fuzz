"""File for code relating to request generation."""

import logging
import os
import subprocess
import sys
import tempfile
from abc import ABC, abstractmethod
from contextlib import ExitStack
from pathlib import Path
from time import sleep
import threading
import queue as _queue
import time

from telephuzz.constants import BASE_PATH
from telephuzz.http_message import Request, Response
from telephuzz.session.mitm_proxy.mitm_proxy import MITMProxyContainer

SCHEMATHESIS_CONFIG_PATH = BASE_PATH / "schemathesis.toml"

logger = logging.getLogger(__name__)


class RequestGenerator(ABC):
    """Abstract class for the request generator."""

    @abstractmethod
    def generate(
        self, previous_responses: list[Response] | None = None
    ) -> list[Request] | None:
        """Abstract method for generating a request chain."""
        raise NotImplementedError

    def generate_batch(
        self, max_items: int | None = None, max_seconds: float | None = None
    ) -> list[Request]:
        """Default batch generator built on top of generate().

        Backwards-compatible: concrete generators can override this with a more
        efficient implementation (e.g., deque/queue-based). If not overridden,
        this will call generate() repeatedly until limits are hit or generator
        is exhausted.
        """
        batch: list[Request] = []
        start = time.monotonic()
        while True:
            # Respect time limit
            if max_seconds is not None and time.monotonic() - start >= max_seconds:
                break

            item = self.generate()
            if item is None:
                break

            batch.extend(item)

            if max_items is not None and len(batch) >= max_items:
                break

        return batch


class OASRequestGenerator(RequestGenerator):
    """Abstract class for a request generator that takes an OpenAPI spec as input."""

    oas: Path


class FuzzerBasedGenerator(OASRequestGenerator):
    """Use an OpenAPI-based fuzzer to pre-generate a sequence of requests.

    This implementation runs the fuzzer in the background and starts a
    producer thread that watches the MITM proxy output directory. Parsed
    Request objects are placed into a bounded queue which can then be
    consumed via generate_batch or generate.
    """

    pregenerated_requests: list[Request]

    def __init__(
        self,
        oas: Path,
        base_api_url: str,
        cmd: list[str],
        proxy_port: int = 8080,
        log_fuzzer: bool = False,
        *,
        queue_maxsize: int = 1000,
        collect_batch_size: int = 500,
        producer_poll_interval: float = 0.1,
    ):
        """Pre-generate the requests using mitmproxy.

        Args:
            oas: The path to the OpenAPI specification used for generation.
            base_api_url: The base URL of the API (e.g. "http://localhost:8000")
            cmd: The cmd to be executed to start the fuzzer. Instead of the URL
                 of the API, the fuzzer should target "http://localhost:{proxy_port}"
                 WARNING: The provided cmd will be executed without sanitization.
                 Only provide trusted input.
            proxy_port: The port the mitmproxy instance (defaults to 8080)
            log_fuzzer: If true, display stdout and stderr messages produced by cmd
            queue_maxsize: Maximum number of parsed Request objects kept in memory
            collect_batch_size: Maximum number of files claimed per scan iteration
            producer_poll_interval: Sleep time when no files are found
        """
        logger.info("Setting up fuzzer-based generator.")
        self.oas = oas
        # in-memory queue of requests produced by the background producer
        self._queue: _queue.Queue[Request | None] = _queue.Queue(maxsize=queue_maxsize)
        self.pregenerated_requests: list[Request] = []  # kept for backward compat

        self.exit_stack = ExitStack()

        # temporary directory for mitmproxy output; kept for lifetime
        self.tmpdir = self.exit_stack.enter_context(tempfile.TemporaryDirectory())
        self.mitmproxy = self.exit_stack.enter_context(
            MITMProxyContainer(
                response_output=self.tmpdir, listen_port=proxy_port, target=base_api_url
            )
        )

        # spawn fuzzer as background process
        self.fuzzing_process = subprocess.Popen(
            cmd,
            stdout=sys.stdout if log_fuzzer else subprocess.DEVNULL,
            stderr=sys.stderr if log_fuzzer else subprocess.DEVNULL,
        )

        # control flags for producer thread
        self._producer_running = True
        self._producer_exhausted = False
        self._producer_poll_interval = producer_poll_interval
        self._collect_batch_size = collect_batch_size

        # start producer thread
        self._producer_thread = threading.Thread(target=self._producer_loop, daemon=True)
        self._producer_thread.start()

        # wait for at least one response to appear (best-effort)
        attempts = 100
        while len(os.listdir(self.tmpdir)) < 1:
            sleep(0.1)
            attempts -= 1
            if not attempts:
                # Attempt a graceful shutdown of the fuzzer process
                try:
                    if self.fuzzing_process.poll() is None:
                        self.fuzzing_process.terminate()
                        self.fuzzing_process.wait(timeout=3)
                except Exception:
                    pass
                raise TimeoutError(
                    "No responses were captured. "
                    "Your fuzzer needs to produce at least one request."
                )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        # stop producer and ensure subprocess is terminated
        self._producer_running = False

        # try to terminate fuzzing process gracefully
        try:
            if hasattr(self, "fuzzing_process") and self.fuzzing_process.poll() is None:
                self.fuzzing_process.terminate()
                try:
                    self.fuzzing_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.fuzzing_process.kill()
                    self.fuzzing_process.wait(timeout=5)
        except Exception:
            logger.exception("Error while terminating fuzzing subprocess")

        # join producer thread (give it some time to finish)
        if hasattr(self, "_producer_thread"):
            self._producer_thread.join(timeout=5)

        # close any resources (mitmproxy tmpdir etc.)
        try:
            self.exit_stack.close()
        except Exception:
            logger.exception("Error while closing exit stack")

    def _producer_loop(self) -> None:
        """Background producer: claim files, parse Requests, and put them into the queue.

        Producer places a sentinel `None` into the queue when the fuzzer has
        exited and no more files remain.
        """
        tmp_path = Path(self.tmpdir)
        processing_suffix = ".processing"

        # helper to try to put into queue without blocking forever
        def _put_with_shutdown(item: Request | None) -> bool:
            # try until we either succeed or producer is asked to stop
            while self._producer_running:
                try:
                    self._queue.put(item, timeout=0.5)
                    return True
                except _queue.Full:
                    continue
            return False

        try:
            while self._producer_running:
                any_work = False

                # iterate over files in tmpdir using scandir for efficiency
                try:
                    entries = list(os.scandir(self.tmpdir))
                except FileNotFoundError:
                    entries = []

                if entries:
                    # sort by modification time to process oldest first
                    entries.sort(key=lambda e: e.stat().st_mtime)

                    for entry in entries[: self._collect_batch_size]:
                        # skip already-claimed files
                        if entry.name.endswith(processing_suffix):
                            continue

                        src = entry.path
                        dst = src + processing_suffix
                        try:
                            # atomic claim
                            os.rename(src, dst)
                        except OSError:
                            # file may be in use or renamed by someone else; skip
                            continue

                        any_work = True

                        # parse request, if parsing fails drop the file
                        try:
                            req = Request.from_json(Path(dst))
                        except Exception:
                            logger.exception("Failed to parse request file %s", dst)
                            try:
                                os.remove(dst)
                            except Exception:
                                pass
                            continue

                        # enqueue with backpressure; respect shutdown
                        if not _put_with_shutdown(req):
                            # shutdown requested while queue was full
                            try:
                                os.remove(dst)
                            except Exception:
                                pass
                            break

                        # successful enqueue → remove processed file
                        try:
                            os.remove(dst)
                        except Exception:
                            pass

                # check whether the fuzzing process is still running
                proc_alive = getattr(self, "fuzzing_process", None) is not None and (
                    self.fuzzing_process.poll() is None
                )

                if not proc_alive:
                    # if process finished, also process remaining files then exit
                    # after processing remaining files, mark exhausted and insert sentinel
                    try:
                        # one final pass to claim remaining files
                        entries = list(os.scandir(self.tmpdir))
                    except FileNotFoundError:
                        entries = []

                    for entry in entries:
                        if entry.name.endswith(processing_suffix):
                            continue
                        src = entry.path
                        dst = src + processing_suffix
                        try:
                            os.rename(src, dst)
                        except OSError:
                            continue

                        try:
                            req = Request.from_json(Path(dst))
                        except Exception:
                            try:
                                os.remove(dst)
                            except Exception:
                                pass
                            continue

                        # try to put until success (but allow short timeouts)
                        try:
                            self._queue.put(req, timeout=2)
                        except _queue.Full:
                            # if queue is full and we cannot enqueue, drop the item
                            logger.warning("Dropping request during final drain due to full queue")

                        try:
                            os.remove(dst)
                        except Exception:
                            pass

                    # put sentinel to notify consumers
                    _put_with_shutdown(None)
                    self._producer_exhausted = True
                    return

                if not any_work:
                    # nothing to do right now
                    time.sleep(self._producer_poll_interval)

            # producer_running is False → shutdown requested
            # try final drain similarly
            try:
                entries = list(os.scandir(self.tmpdir))
            except FileNotFoundError:
                entries = []

            for entry in entries:
                if entry.name.endswith(processing_suffix):
                    continue
                src = entry.path
                dst = src + processing_suffix
                try:
                    os.rename(src, dst)
                except OSError:
                    continue
                try:
                    req = Request.from_json(Path(dst))
                except Exception:
                    try:
                        os.remove(dst)
                    except Exception:
                        pass
                    continue
                try:
                    self._queue.put(req, timeout=1)
                except _queue.Full:
                    logger.warning("Dropping request during shutdown due to full queue")
                try:
                    os.remove(dst)
                except Exception:
                    pass

            # signal consumer that generator is exhausted
            _put_with_shutdown(None)
            self._producer_exhausted = True

        except Exception:
            logger.exception("Unhandled exception in producer loop")
            try:
                # try to notify consumer of exhaustion to avoid deadlocks
                _put_with_shutdown(None)
            except Exception:
                pass
            self._producer_exhausted = True

    def _collect_responses(self):
        """Legacy helper retained for compatibility: drain any files into the in-memory list.

        Note: this method is not used by the new producer-based flow but kept to
        preserve backward compatibility for callers that inspect pregenerated_requests.
        """
        responses = os.listdir(self.tmpdir)
        base_response_path = Path(self.tmpdir)
        for response in responses[:1000]:
            response_path = base_response_path / response
            request_obj = Request.from_json(response_path)

            self.pregenerated_requests.append(request_obj)

            os.remove(response_path)

    def generate(
        self, previous_responses: list[Response] | None = None
    ) -> list[Request] | None:
        """Return the next pregenerated request or None when exhausted.

        This implementation is compatible with the old API but backed by the
        internal queue. It will block until one request is available or the
        generator is exhausted.
        """
        batch = self.generate_batch(max_items=1, max_seconds=None)
        if not batch:
            return None
        return [batch[0]]

    def generate_batch(
        self, max_items: int | None = None, max_seconds: float | None = None
    ) -> list[Request]:
        """Consume up to max_items requests from the internal queue.

        If max_items is None and max_seconds is None this will drain everything
        until the generator signals exhaustion.
        """
        collected: list[Request] = []
        start = time.monotonic()

        # compute remaining time helper
        def _remaining() -> float | None:
            if max_seconds is None:
                return None
            rem = max_seconds - (time.monotonic() - start)
            return max(0.0, rem)

        while True:
            # stop if we hit item limit
            if max_items is not None and len(collected) >= max_items:
                break

            # stop if time ran out
            rem = _remaining()
            if rem is not None and rem <= 0:
                break

            try:
                item = self._queue.get(timeout=rem)
            except _queue.Empty:
                # timed out waiting for an item
                break

            # sentinel -> generator exhausted
            if item is None:
                # put sentinel back for other consumers
                try:
                    self._queue.put_nowait(None)
                except Exception:
                    pass
                break

            collected.append(item)

            # continue until limits reached

        # keep backward-compatible in-memory list for callers/tests
        if collected:
            self.pregenerated_requests.extend(collected)

        # return at most max_items
        if max_items is not None:
            return collected[:max_items]
        return collected


class SchemathesisGenerator(FuzzerBasedGenerator):
    """Request generator based on Schemathesis.

    Pre-generates requests by running schemathesis and capturing requests via
    the MITM proxy. Generation runs in background — use generate_batch to
    consume requests.
    """

    def __init__(
        self,
        oas: Path,
        base_api_url: str,
        proxy_port: int = 8080,
        max_time_seconds: int = 3600,
        log_fuzzer: bool = False,
        **kwargs,
    ):
        """Initialize the SchemathesisGenerator."""
        cmd = [
            "schemathesis",
            "--config-file",
            str(SCHEMATHESIS_CONFIG_PATH),
            "fuzz",
            str(oas),
            "--url",
            f"http://localhost:{proxy_port}",
            "--max-time",
            str(max_time_seconds),
            "--continue-on-failure",
            "-m",
            "positive",
        ]
        super().__init__(
            oas=oas,
            base_api_url=base_api_url,
            cmd=cmd,
            proxy_port=proxy_port,
            log_fuzzer=log_fuzzer,
            **kwargs,
        )
