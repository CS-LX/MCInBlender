"""Ordered, at-most-once consumption of local diagnostic actions."""
import json


def _remove_claim(path):
    try:
        path.unlink(missing_ok=True)
    except PermissionError:
        # Windows readers/antivirus may temporarily deny deletion. A claimed
        # action is never replayed, even if cleanup needs another timer tick.
        pass


def drain(inbox, consume):
    for path in inbox.glob('*.claimed'):
        _remove_claim(path)
    for path in sorted(inbox.glob('*.json')):
        claimed = path.with_suffix('.claimed')
        try:
            raw = path.read_text(encoding='utf8')
            path.rename(claimed)
        except FileNotFoundError:
            continue
        except PermissionError:
            # Preserve press/release order: do not process later actions while
            # an earlier file is temporarily unavailable.
            return
        try:
            consume(json.loads(raw))
        finally:
            # Claim before dispatch so a failed delete cannot repeat a click.
            # A crash after claiming intentionally does not replay that action.
            _remove_claim(claimed)
