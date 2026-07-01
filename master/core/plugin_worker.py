"""
Vigile — Plugin Worker (Isolated Child Process)

Runs a single plugin in a sandboxed subprocess.
Communicates with the Master parent process over stdin/stdout using JSON lines.
Logs and errors are output to stderr so they don't corrupt the JSON stream.
"""

import sys
import os
import json
import asyncio
import logging
import importlib.util
from typing import Any, Callable

# Configure logging to go to stderr so stdout is purely JSON-RPC messages
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (plugin-worker) %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("plugin_worker")


class CursorProxy:
    """Mock SQLite cursor returned by DatabaseProxy.execute."""
    def __init__(self, result_data: dict):
        self.rowcount = result_data.get("rowcount", -1)
        self.lastrowid = result_data.get("lastrowid")
        self._rows = result_data.get("rows", [])
        self._index = 0

    async def fetchall(self) -> list[Any]:
        return self._rows

    async def fetchone(self) -> Any | None:
        if self._index < len(self._rows):
            res = self._rows[self._index]
            self._index += 1
            return res
        return None

    def __aiter__(self):
        return self

    async def __anext__(self):
        row = await self.fetchone()
        if row is None:
            raise StopAsyncIteration
        return row


class DatabaseProxy:
    """
    Proxies database execute and commit calls back to the parent process.
    """
    def __init__(self, call_id: str, request_fn: Callable):
        self._call_id = call_id
        self._request_fn = request_fn

    async def execute(self, sql: str, params: Any = ()) -> CursorProxy:
        # If params is a tuple, convert it to a list for JSON serialization
        p = list(params) if isinstance(params, (tuple, list)) else params
        res = await self._request_fn("db_execute", sql=sql, params=p)
        return CursorProxy(res)

    async def commit(self) -> None:
        await self._request_fn("db_commit")


class WorkerPluginManager:
    """
    Local PluginManager stub passed to the plugin's register() function.
    """
    def __init__(self):
        self._hooks: dict[str, Callable] = {}

    def register(self, hook_name: str, fn: Callable, *, plugin_name: str = "anonymous") -> None:
        self._hooks[hook_name] = fn


class PluginWorker:
    def __init__(self, plugin_name: str, plugin_path: str):
        self.plugin_name = plugin_name
        self.plugin_path = plugin_path
        self.pm = WorkerPluginManager()
        self._pending_db_calls: dict[str, asyncio.Future] = {}

    def load_and_register(self) -> None:
        """Dynamically load the plugin and call its register() method."""
        logger.info("Loading plugin '%s' from %s", self.plugin_name, self.plugin_path)
        if not os.path.isfile(self.plugin_path):
            raise FileNotFoundError(f"Plugin file not found: {self.plugin_path}")

        module_name = f"vigile.plugins.{self.plugin_name}"
        spec = importlib.util.spec_from_file_location(module_name, self.plugin_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load spec for {self.plugin_path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        module.register(self.pm)
        # Send init message to parent
        hooks_list = list(self.pm._hooks.keys())
        schema = {}
        if hasattr(module, "get_config_schema"):
            try:
                schema = module.get_config_schema()
            except Exception:
                pass
        sys.stdout.write(json.dumps({"type": "init", "hooks": hooks_list, "schema": schema}) + "\n")
        sys.stdout.flush()
        logger.info("Plugin '%s' loaded and registered hooks successfully.", self.plugin_name)

    async def send_to_parent(self, msg: dict) -> None:
        """Write JSON message to stdout and flush."""
        sys.stdout.write(json.dumps(msg) + "\n")
        sys.stdout.flush()

    async def db_request(self, call_id: str, op_type: str, **kwargs: Any) -> dict:
        """Helper to send a database operation request back to the parent and await response."""
        db_call_id = str(asyncio.get_running_loop().time()) + "-" + os.urandom(4).hex()
        fut = asyncio.get_running_loop().create_future()
        self._pending_db_calls[db_call_id] = fut

        await self.send_to_parent({
            "type": op_type,
            "call_id": call_id,
            "db_call_id": db_call_id,
            **kwargs
        })

        try:
            return await fut
        finally:
            self._pending_db_calls.pop(db_call_id, None)

    async def run(self) -> None:
        """Main JSON-RPC reading loop on stdin."""
        loop = asyncio.get_running_loop()
        queue = asyncio.Queue()

        def read_stdin():
            try:
                for line in sys.stdin:
                    loop.call_soon_threadsafe(queue.put_nowait, line)
            except Exception as e:
                logger.exception("Error in stdin reader thread")
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, "")

        import threading
        reader_thread = threading.Thread(target=read_stdin, daemon=True)
        reader_thread.start()

        logger.info("Plugin worker loop started (thread-safe reader). Waiting for requests.")

        while True:
            line = await queue.get()
            if not line:
                logger.info("Stdin EOF reached. Exiting worker.")
                break

            try:
                msg = json.loads(line.strip())
                msg_type = msg.get("type")

                if msg_type == "db_result":
                    db_call_id = msg.get("db_call_id")
                    fut = self._pending_db_calls.get(db_call_id)
                    if fut and not fut.done():
                        if msg.get("status") == "success":
                            fut.set_result(msg.get("result", {}))
                        else:
                            fut.set_exception(RuntimeError(msg.get("error", "Database error")))
                    continue

                if msg_type == "call_hook":
                    asyncio.create_task(self.handle_call_hook(msg))
                    continue

                logger.warning("Unknown message type: %s", msg_type)

            except Exception as e:
                logger.exception("Failed to parse/handle message line: %r", line)

    async def handle_call_hook(self, msg: dict) -> None:
        """Invokes the requested hook callback."""
        call_id = msg.get("call_id")
        hook_name = msg.get("hook_name")
        kwargs = msg.get("kwargs", {})

        fn = self.pm._hooks.get(hook_name)
        if fn is None:
            # Hook not registered by this plugin
            await self.send_to_parent({
                "type": "response",
                "call_id": call_id,
                "status": "success",
                "result": None
            })
            return

        # If the hook expects a 'db' parameter, pass our DatabaseProxy
        import inspect
        sig = inspect.signature(fn)
        if "db" in sig.parameters:
            kwargs["db"] = DatabaseProxy(call_id, lambda op, **kw: self.db_request(call_id, op, **kw))

        try:
            if asyncio.iscoroutinefunction(fn):
                res = await fn(**kwargs)
            else:
                res = fn(**kwargs)

            await self.send_to_parent({
                "type": "response",
                "call_id": call_id,
                "status": "success",
                "result": res
            })
        except Exception as e:
            logger.exception("Exception raised during hook '%s' execution", hook_name)
            await self.send_to_parent({
                "type": "response",
                "call_id": call_id,
                "status": "error",
                "error": str(e)
            })


def main():
    if len(sys.argv) < 3:
        print("Usage: python plugin_worker.py <plugin_name> <plugin_path>", file=sys.stderr)
        sys.exit(1)

    plugin_name = sys.argv[1]
    plugin_path = sys.argv[2]

    worker = PluginWorker(plugin_name, plugin_path)
    try:
        worker.load_and_register()
    except Exception as e:
        logger.exception("Failed to initialize plugin worker")
        sys.exit(2)

    try:
        asyncio.run(worker.run())
    except KeyboardInterrupt:
        logger.info("Plugin worker interrupted.")


if __name__ == "__main__":
    main()
