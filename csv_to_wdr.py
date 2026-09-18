#!/usr/bin/env python3
"""Convert drivers.csv to WinISD .wdr files using only Python's standard library.

Usage: python3 csv_to_wdr.py [drivers.csv] --output WDR
With no CSV argument, both drivers.csv and drivers_partial.csv are loaded.
Units are explicit in CSV headers. WDR uses SI units. Source values are not
averaged or reconciled; rows below the WinISD minimum are skipped unless
--include-incomplete is requested. See README.md for field mappings and limits.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from decimal import Decimal, InvalidOperation
import hashlib
import math
from pathlib import Path
import re
import sys
import tempfile
import unicodedata

HERE = Path(__file__).resolve().parent

# CSV column: (WinISD key, multiplier converting to SI).
FIELD_MAP = {
    "impedance_ohm": ("Znom", "1"),
    "fs_hz": ("Fs", "1"),
    "qts": ("Qts", "1"),
    "qes": ("Qes", "1"),
    "qms": ("Qms", "1"),
    "vas_l": ("Vas", "0.001"),
    "re_ohm": ("Re", "1"),
    "le_mh": ("Le", "0.001"),
    "le_frequency_hz": ("fLe", "1"),
    "sd_cm2": ("Sd", "0.0001"),
    "mms_g": ("Mms", "0.001"),
    "cms_mm_per_n": ("Cms", "0.001"),
    "rms_ns_per_m": ("Rms", "1"),
    "bl_tm": ("BL", "1"),
    "xmax_mm": ("Xmax", "0.001"),
    "vd_cm3": ("Vd", "0.000001"),
    "eta0_percent": ("no", "0.01"),
    "ebp_hz": ("EBP", "1"),
    "power_rms_w": ("Pe", "1"),
    "sensitivity_1w_1m_db": ("SPL", "1"),
    "sensitivity_2v83_1m_db": ("USPL", "1"),
    "overall_diameter_mm": ("Outer", "0.001"),
    "effective_diaphragm_diameter_mm": ("Dd", "0.001"),
    "voice_coil_diameter_mm": ("Vcd", "0.001"),
    "voice_coil_height_mm": ("Hc", "0.001"),
    "gap_height_mm": ("Hg", "0.001"),
    "flange_thickness_mm": ("Thick", "0.001"),
    "magnet_diameter_mm": ("Magnet", "0.001"),
    "magnet_depth_mm": ("MagDepth", "0.001"),
}
CSV_ONLY = {
    "mmd_g", "xmech_mm", "linear_travel_pp_mm", "max_travel_pp_mm",
    "xlin_mm", "sensitivity_db", "power_handling_w", "nominal_diameter_in",
    "qa_as_printed",
    "nominal_diameter_mm", "overall_width_mm", "overall_height_mm", "overall_depth_mm",
    "mounting_depth_mm", "cutout_diameter_mm", "bolt_circle_diameter_mm",
    "mounting_hole_diameter_mm", "mounting_hole_count", "voice_coil_former_height_mm",
    "cone_dome_diameter_mm", "ribbon_dimension_1_mm", "ribbon_dimension_2_mm",
    "overall_dimension_1_mm", "overall_dimension_2_mm", "overall_dimension_3_mm",
    "cutout_dimension_1_mm", "cutout_dimension_2_mm", "tweeter_voice_coil_diameter_mm",
    "tweeter_voice_coil_height_mm", "tweeter_gap_height_mm",
    "krm_microohm", "erm", "kxm_mh", "exm", "power_peak_w",
    "frequency_min_hz", "frequency_max_hz", "crossover_frequency_hz",
    "crossover_slope_db_per_oct", "power_continuous_iec268_5_w",
    "power_test_highpass_hz", "power_test_highpass_slope_db_per_oct",
    "net_weight_kg", "magnet_weight_g", "sensitivity_tolerance_db",
}
NUMERIC_COLUMNS = set(FIELD_MAP) | CSV_ONLY
MINIMUM = ("fs_hz", "qts", "vas_l")
# Completeness of the app's primary feed, distinct from WinISD's import minimum.
# Rms, derived quantities, power ratings and physical dimensions are optional.
COMPLETE_PARAMETERS = (
    "impedance_ohm", "fs_hz", "qts", "qes", "qms", "vas_l", "re_ohm",
    "le_mh", "sd_cm2", "mms_g", "cms_mm_per_n", "bl_tm", "xmax_mm",
)

# Field names/order checked against driver files bundled with WinISD 0.7.950.
# Its legacy .wdr files omit ParState, dates and author fields are optional.
WDR_KEYS = (
    "Qts Znom Fs Pe SPL Re Le fLe KLe BL Xmax Cms Qms Qes Rms Mms Sd Vas "
    "Dia Vd no Dd EBP numVC Hc Hg SPLmax SPLmaxLF USPL alfaVC Rt Ct gamma "
    "Rme Mpow Mcost Gloss VCCon c roo Thick Depth MagDepth Magnet Basket "
    "Outer Vcd DVol"
).split()


class DataError(ValueError):
    """Invalid input; detected before output files are written."""


def decimal_value(value: str | None, column: str, line: int) -> Decimal | None:
    if value is None or not value.strip():
        return None
    try:
        number = Decimal(value.strip())
    except InvalidOperation as exc:
        raise DataError(f"CSV line {line}: {column} is not a number: {value!r}") from exc
    if not number.is_finite():
        raise DataError(f"CSV line {line}: {column} must be finite")
    if number < 0:
        raise DataError(f"CSV line {line}: {column} must not be negative")
    return number


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        header = reader.fieldnames or []
        if len(set(header)) != len(header):
            raise DataError("CSV contains duplicate column names")
        missing = {"manufacturer", "model", *MINIMUM} - set(header)
        if missing:
            raise DataError("Missing CSV columns: " + ", ".join(sorted(missing)))
        rows = []
        for line, row in enumerate(reader, 2):
            if None in row or any(value is None for value in row.values()):
                raise DataError(f"CSV line {line}: column count does not match the header")
            if not any(value.strip() for value in row.values()):
                continue
            item = {"line": line, "manufacturer": row["manufacturer"].strip(),
                    "model": row["model"].strip()}
            for column in NUMERIC_COLUMNS:
                item[column] = decimal_value(row.get(column), column, line)
            rows.append(item)
        return rows


def missing_full_parameters(row: dict) -> list[str]:
    """Missing/invalid fields for drivers.csv; no calculated substitutes.

    Numeric inputs use the Decimal values returned by read_csv. An explicit
    zero inductance is valid; other required numeric values must be positive.
    """
    missing = [key for key in ("manufacturer", "model")
               if not str(row.get(key) or "").strip()]
    for key in COMPLETE_PARAMETERS:
        value = row.get(key)
        if (value is None or not value.is_finite() or value < 0
                or (key != "le_mh" and value == 0)):
            missing.append(key)
    return missing


def read_inputs(csv_file: Path | None = None) -> list[dict]:
    """Default regeneration includes both feeds; an explicit path selects one.

    Combining the feeds before naming files preserves collision suffixes and
    deduplication across the full, previously published WDR library.
    """
    paths = [csv_file] if csv_file is not None else [HERE / "drivers.csv"]
    partial = HERE / "drivers_partial.csv"
    if csv_file is None and partial.exists():
        paths.append(partial)
    rows = []
    for path in paths:
        for row in read_csv(path):
            row["source_file"] = path.name
            rows.append(row)
    return rows


def number_text(value: Decimal) -> str:
    """Locale-independent decimal text with no unnecessary trailing zeros."""
    if value == 0:
        return "0"
    return format(value, "f").rstrip("0").rstrip(".") if "." in format(value, "f") else str(value)


def ascii_label(value: str) -> str:
    # WinISD's legacy driver library is ANSI. ASCII avoids platform code pages.
    for source, replacement in {"Ω": "ohm", "Ω": "ohm", "Ø": "O", "ø": "o",
                                "µ": "u", "μ": "u", "–": "-", "—": "-"}.items():
        value = value.replace(source, replacement)
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(value.split())


def safe_stem(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", ascii_label(value)).strip(" .")
    if not value:
        value = "driver"
    if re.fullmatch(r"CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]", value.split(".")[0], re.I):
        value = "_" + value
    return value[:150].rstrip(" .")


def to_wdr(row: dict) -> str:
    parameters = {key: Decimal(0) for key in WDR_KEYS}
    for column, (key, multiplier) in FIELD_MAP.items():
        if row.get(column) is not None:
            parameters[key] = row[column] * Decimal(multiplier)
    # Apply only an explicitly peak-to-peak linear excursion as a fallback.
    if row.get("xmax_mm") is None and row.get("linear_travel_pp_mm") is not None:
        parameters["Xmax"] = row["linear_travel_pp_mm"] * Decimal("0.0005")
    # Treat the supplied electrical values as one equivalent connection. Actual
    # voice-coil count/wiring is not reliably specified by the source CSV.
    parameters.update(numVC=Decimal(1), VCCon=Decimal(1),
                      c=Decimal("343.68"), roo=Decimal("1.20095"))
    brand, model = ascii_label(row["manufacturer"]), ascii_label(row["model"])
    lines = ["[Driver]", f"Brand={brand}", f"Model={model}", f"Manufacturer={brand}"]
    lines.extend(f"{key}={number_text(parameters[key])}" for key in WDR_KEYS)
    return "\r\n".join(lines) + "\r\n"


def consistency_warnings(row: dict) -> list[str]:
    """Small independent screens; not WinISD's native integrity checker."""
    messages = []
    if all(row.get(key) and row[key] > 0 for key in ("qts", "qes", "qms")):
        expected = row["qes"] * row["qms"] / (row["qes"] + row["qms"])
        if abs(row["qts"] - expected) / expected > Decimal("0.05"):
            messages.append("Qts differs by more than 5% from Qes/Qms")
    if all(row.get(key) and row[key] > 0 for key in ("fs_hz", "mms_g", "cms_mm_per_n")):
        expected = 1 / (2 * math.pi * math.sqrt(float(row["mms_g"] * row["cms_mm_per_n"]) * 1e-6))
        if abs(float(row["fs_hz"]) - expected) / expected > 0.1:
            messages.append("Fs differs by more than 10% from Mms/Cms")
    return messages


def compile_files(rows: list[dict], include_incomplete: bool = False):
    files, details, counts = {}, [], Counter(rows=len(rows))
    candidates = {}
    for row in rows:
        source = f"{row['source_file']}: " if row.get("source_file") else ""
        label = f"{source}line {row['line']}: {row['manufacturer']} {row['model']}".strip()
        if not ascii_label(row["manufacturer"]) or not ascii_label(row["model"]):
            counts["missing_identity"] += 1
            details.append(f"SKIP {label}: missing manufacturer or model after ASCII conversion")
            continue
        missing = [key for key in MINIMUM if row.get(key) is None or row[key] <= 0]
        if missing and not include_incomplete:
            counts["incomplete"] += 1
            details.append(f"SKIP {label}: needs positive {', '.join(missing)}")
            continue
        if not any(row.get(key) is not None for key in (*FIELD_MAP, "linear_travel_pp_mm")):
            counts["no_parameters"] += 1
            details.append(f"SKIP {label}: no supported parameters")
            continue
        text = to_wdr(row)
        digest = hashlib.sha256(text.encode("ascii")).hexdigest()
        if digest in candidates:
            counts["duplicates"] += 1
            continue
        issues = consistency_warnings(row)
        if issues:
            counts["consistency_warnings"] += 1
            details.append(f"REVIEW {label}: {'; '.join(issues)}; values retained")
        impedance = row.get("impedance_ohm")
        suffix = f" ({number_text(impedance)} ohm)" if impedance else ""
        stem = safe_stem(f"{row['manufacturer']} {row['model']}{suffix}")
        candidates[digest] = (stem, text)
        if missing:
            counts["partial_files"] += 1
    grouped = defaultdict(list)
    for digest, (stem, text) in candidates.items():
        grouped[stem.casefold()].append((digest, stem, text))
    used = set()
    for group in sorted(grouped.values(), key=lambda items: items[0][1].casefold()):
        for digest, stem, text in sorted(group):
            name = f"{stem}__{digest[:12]}.wdr" if len(group) > 1 else f"{stem}.wdr"
            # Includes case-insensitive collisions with naturally suffixed names.
            if name.casefold() in used:
                name = f"{stem}__{digest}.wdr"
            if name.casefold() in used:
                raise DataError(f"Unresolvable filename collision: {name}")
            used.add(name.casefold())
            files[name] = text.encode("ascii")
    counts["written"] = len(files)
    return files, counts, details


def write_files(files: dict[str, bytes], directory: Path, clean: bool = False) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    if not directory.is_dir():
        raise DataError(f"Output is not a directory: {directory}")
    for name in files:
        target = directory / name
        if target.is_symlink():
            raise DataError(f"Refusing to overwrite a symbolic link: {target}")
    # --clean is explicit: only WDR files in this output directory are removed.
    # Do this after preparing all data, so malformed CSV cannot erase old output.
    if clean:
        for old in directory.iterdir():
            if old.suffix.lower() == ".wdr" and (old.is_file() or old.is_symlink()):
                old.unlink()
    for name, content in files.items():
        destination = directory / name
        if destination.exists() and destination.read_bytes() == content:
            continue
        with tempfile.NamedTemporaryFile(dir=directory, prefix=".wdr-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        try:
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv_file", nargs="?", type=Path, default=None,
                        help="one CSV to convert; omitted loads drivers.csv and drivers_partial.csv")
    parser.add_argument("--output", "-o", type=Path, default=HERE / "WDR")
    parser.add_argument("--include-incomplete", action="store_true", help="also emit partial driver records; these cannot necessarily start a project")
    parser.add_argument("--clean", action="store_true", help="remove all existing .wdr files in the output directory before writing")
    parser.add_argument("--check", action="store_true", help="validate and count without writing any files")
    parser.add_argument("--verbose", "-v", action="store_true", help="show every skipped row and consistency warning")
    args = parser.parse_args(argv)
    try:
        files, counts, details = compile_files(read_inputs(args.csv_file), args.include_incomplete)
        if not args.check:
            write_files(files, args.output, args.clean)
        if args.verbose:
            print("\n".join(details), file=sys.stderr)
        action = "Would write" if args.check else "Wrote"
        print(f"{action} {counts['written']} WDR files from {counts['rows']} CSV rows.")
        print(f"Skipped: {counts['incomplete']} incomplete, {counts['missing_identity']} missing identity, "
              f"{counts['no_parameters']} without supported parameters; {counts['duplicates']} identical WDR outputs deduplicated.")
        print(f"Consistency warnings: {counts['consistency_warnings']} files (source values retained). "
              f"Partial files: {counts['partial_files']}.")
        return 0
    except (DataError, OSError, csv.Error) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
