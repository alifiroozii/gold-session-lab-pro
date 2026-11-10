"""Read pinned Bid/Ask archives for the separate offline XAU/USD experiment."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass
class Quotes:
    # Timestamps are UTC milliseconds. For ticks, each OHLC array aliases the tick price.
    time: np.ndarray
    bid_open: np.ndarray
    bid_high: np.ndarray
    bid_low: np.ndarray
    bid_close: np.ndarray
    ask_open: np.ndarray
    ask_high: np.ndarray
    ask_low: np.ndarray
    ask_close: np.ndarray
    is_tick: bool


def checked_files(folder):
    manifest = json.loads((folder / "manifest.json").read_text())
    files = []
    for item in manifest["files"]:
        path = folder / Path(item["path"]).name
        if not path.is_file():
            continue
        data = path.read_bytes()
        sha = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
        if len(data) != item["size"] or sha != item["sha"]:
            raise ValueError(f"Git blob verification failed for {path.name}")
        files.append((path, item["sha"]))
    if not files:
        raise ValueError("No pinned files found")
    return manifest, files


def read_minutes(files):
    sides = []
    for side in ("bid", "ask"):
        parts = [pd.read_csv(path) for path, _ in files if f"_{side}_" in path.name]
        if not parts:
            raise ValueError(f"No {side} files")
        frame = pd.concat(parts, ignore_index=True)
        if frame["timestamp"].duplicated().any():
            raise ValueError(f"Duplicate {side} minute")
        sides.append(frame)
    bid, ask = sides
    joined = bid.merge(ask, on="timestamp", validate="one_to_one", suffixes=("_b", "_a"))
    joined = joined.sort_values("timestamp", ignore_index=True)
    time = joined["timestamp"].to_numpy(dtype=np.int64)
    if np.any(time % 60000):
        raise ValueError("Minute time is not aligned to UTC")
    cols = [joined[f"{key}_{side}"].to_numpy(dtype=np.float64) for side in ("b", "a")
            for key in ("open", "high", "low", "close")]
    bo, bh, bl, bc, ao, ah, al, ac = cols
    valid = (
        np.isfinite(cols).all(axis=0) & (bl > 0) & (al > 0)
        & (bh >= np.maximum(bo, bc)) & (bl <= np.minimum(bo, bc))
        & (ah >= np.maximum(ao, ac)) & (al <= np.minimum(ao, ac))
        & (ao >= bo) & (ac >= bc)
    )
    # The mirror includes flat calendar rows. Without volume we cannot distinguish a
    # carried price from a genuine stationary quote, so neither is used to execute.
    flat = (bh == bl) & (ah == al)
    live = valid & ~flat
    quality = dict(unmatched_minutes=len(bid) + len(ask) - 2 * len(time),
                   invalid_minutes=int((~valid).sum()), flat_minutes_excluded=int((valid & flat).sum()))
    return Quotes(time[live], *(x[live] for x in cols), False), quality


def read_ticks(files):
    import pyarrow.parquet as pq

    chunks = []
    bad_quotes = 0
    for path, _ in files:
        table = pq.read_table(path)
        if not table.num_rows:
            continue
        names = {key.lower(): key for key in table.column_names}
        time_name = next((names[key] for key in ("timestamp", "time", "datetime") if key in names), None)
        if time_name is None:
            raise ValueError(f"Unknown timestamp field: {table.column_names}")
        bid_name = names.get("bid") or names.get("bid_price")
        ask_name = names.get("ask") or names.get("ask_price")
        frame = table.select([time_name, bid_name, ask_name]).to_pandas()
        stamp = frame[time_name]
        if pd.api.types.is_numeric_dtype(stamp):
            t = stamp.to_numpy(dtype=np.int64)
            if t.min() < 10**12 or t.max() >= 10**13:
                raise ValueError("Numeric tick times must be Unix milliseconds")
        else:
            t = pd.to_datetime(stamp, utc=True).to_numpy(dtype="datetime64[ms]").astype(np.int64)
        bid = frame[bid_name].to_numpy(dtype=np.float64)
        ask = frame[ask_name].to_numpy(dtype=np.float64)
        valid = np.isfinite(bid) & np.isfinite(ask) & (bid > 0) & (ask >= bid)
        bad_quotes += int((~valid).sum())
        if np.any(np.diff(t) < 0):
            raise ValueError(f"Tick file is not sorted: {path.name}")
        chunks.append((t[valid], bid[valid], ask[valid]))
    chunks = sorted((x for x in chunks if len(x[0])), key=lambda x: x[0][0])
    if not chunks:
        raise ValueError("Empty tick archives")
    if any(a[0][-1] >= b[0][0] for a, b in zip(chunks, chunks[1:])):
        raise ValueError("Overlapping tick files require independent review")
    time, bid, ask = (np.concatenate(parts) for parts in zip(*chunks))
    return Quotes(time, bid, bid, bid, bid, ask, ask, ask, ask, True), {"invalid_ticks": bad_quotes}


def grouped(quotes, seconds):
    step = seconds * 1000
    # For monotone timestamp series, search for bucket boundaries without sorting any ticks.
    labels = np.arange(quotes.time[0] // step, quotes.time[-1] // step + 2, dtype=np.int64) * step
    positions = np.searchsorted(quotes.time, labels)
    nonempty = np.diff(positions) > 0
    start, end = positions[:-1][nonempty], positions[1:][nonempty]
    frame = pd.DataFrame({
        "open": quotes.bid_open[start],
        "high": np.maximum.reduceat(quotes.bid_high, start),
        "low": np.minimum.reduceat(quotes.bid_low, start),
        "close": quotes.bid_close[end - 1],
        "count": end - start,
        "quote_start": start,
    }, index=labels[:-1][nonempty])
    return frame
