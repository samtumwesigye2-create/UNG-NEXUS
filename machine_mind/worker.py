from __future__ import annotations
import threading
import storage
import transport

_stop=threading.Event()
_thread=None

def _loop():
    while not _stop.is_set():
        try:
            rows=storage.pending_outbox(20)
            for row in rows:
                result=transport.send(
                    row["target_system"],
                    row["message_type"],
                    dict(row["payload_json"] or {}),
                    row.get("correlation_id"),
                    row["outbox_id"],
                )
                storage.mark_outbox(row["outbox_id"],bool(result.get("sent")),result.get("reason"))
        except Exception as exc:
            print(f"MACHINE_MIND_OUTBOX_ERROR {type(exc).__name__}",flush=True)
        _stop.wait(2.0)

def start():
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread=threading.Thread(target=_loop,name="machine-mind-outbox",daemon=True)
    _thread.start()

def stop():
    _stop.set()
