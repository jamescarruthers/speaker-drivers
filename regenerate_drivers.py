#!/usr/bin/env python3
"""Repartition and sort the CSV feeds, then regenerate WDR using Python 3.10+."""

from __future__ import annotations

import argparse
import csv
import io
from pathlib import Path
import sys
import tempfile

import csv_to_wdr as converter

HERE = Path(__file__).resolve().parent
FEEDS = ("drivers.csv", "drivers_partial.csv")


def read_feed(path: Path):
    """Validate numbers while retaining the original text of every CSV cell."""
    try:
        parsed = converter.read_csv(path)
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream, strict=True)
            header = next(reader)
            raw = [row for row in reader if any(value.strip() for value in row)]
        if (header[:2] != ["manufacturer", "model"]
                or set(header[2:]) != converter.NUMERIC_COLUMNS):
            raise converter.DataError("CSV columns must match the published driver schema")
        if len(raw) != len(parsed):
            raise converter.DataError("CSV record count changed while reading")
        for row in parsed:
            row["source_file"] = path.name
        return header, list(zip(raw, parsed))
    except (converter.DataError, csv.Error) as exc:
        raise converter.DataError(f"{path.name}: {exc}") from exc


def csv_bytes(header: list[str], rows: list[list[str]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def build(root: Path):
    """Prepare all outputs before changing any files; both feeds are required."""
    headers, records = [], []
    for filename in FEEDS:
        header, rows = read_feed(root / filename)
        headers.append(header)
        records.append(rows)
    if headers[0] != headers[1]:
        raise converter.DataError("Both CSV feeds must have identical headers in the same order")

    full, partial = [], []
    promoted = demoted = 0
    for source_index, rows in enumerate(records):
        for raw, parsed in rows:
            complete = not converter.missing_full_parameters(parsed)
            (full if complete else partial).append((raw, parsed))
            promoted += int(source_index == 1 and complete)
            demoted += int(source_index == 0 and not complete)
    # Sort labels case-insensitively without changing their stored spelling.
    # Python's stable sort preserves the order of variants with matching labels.
    for rows in (full, partial):
        rows.sort(key=lambda item: (item[1]["manufacturer"].casefold(),
                                   item[1]["model"].casefold()))
    feeds = {
        filename: csv_bytes(headers[0], [raw for raw, _ in rows])
        for filename, rows in zip(FEEDS, (full, partial))
    }
    wdr, counts, _ = converter.compile_files([parsed for _, parsed in full + partial])
    summary = (
        f"drivers.csv: {len(full):,} complete records.\n"
        f"drivers_partial.csv: {len(partial):,} partial records.\n"
        f"Moved to complete: {promoted}; moved to partial: {demoted}.\n"
        f"WDR: {len(wdr):,} files from {counts['rows']:,} records.\n"
        f"Consistency warnings: {counts['consistency_warnings']} (values retained)."
    )
    return feeds, wdr, summary


def changed_paths(root: Path, feeds: dict[str, bytes], wdr: dict[str, bytes]) -> list[str]:
    expected = {**feeds, **{f"WDR/{name}": data for name, data in wdr.items()}}
    changed = [name for name, data in expected.items()
               if not (root / name).is_file() or (root / name).read_bytes() != data]
    directory = root / "WDR"
    if directory.is_dir():
        changed.extend(f"WDR/{path.name}" for path in directory.iterdir()
                       if path.suffix.lower() == ".wdr"
                       and (path.is_file() or path.is_symlink()) and path.name not in wdr)
    return sorted(changed)


def replace_csv(path: Path, content: bytes) -> None:
    if path.read_bytes() == content:
        return
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".csv-", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(content)
    try:
        temporary.chmod(path.stat().st_mode & 0o777)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=HERE, help="directory containing both CSV feeds and WDR")
    parser.add_argument("--check", action="store_true", help="exit 1 if outputs need regeneration; do not write files")
    args = parser.parse_args(argv)
    try:
        # Do not follow links while replacing the public feeds or WDR directory.
        for name in (*FEEDS, "WDR"):
            if (args.root / name).is_symlink():
                raise converter.DataError(f"Refusing to regenerate through a symbolic link: {name}")
        feeds, wdr, summary = build(args.root)
        changed = changed_paths(args.root, feeds, wdr)
        print(summary)
        if args.check:
            if changed:
                print("Files needing regeneration:\n" + "\n".join(changed))
                return 1
            print("All generated files are up to date.")
            return 0
        # The converter validates output targets before its explicit cleanup.
        # CSV input validation and WDR compilation have already succeeded.
        if changed:
            converter.write_files(wdr, args.root / "WDR", clean=True)
            for name, content in feeds.items():
                replace_csv(args.root / name, content)
        print(f"Regenerated {len(changed)} changed file(s)." if changed else "All generated files are up to date.")
        return 0
    except (converter.DataError, OSError, csv.Error) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
