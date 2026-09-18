# Loudspeaker T/S data and WinISD drivers

`drivers.csv` contains records with a **complete core T/S parameter set**.
`drivers_partial.csv` retains records with missing parameters. Both files use the
same **76 columns**, containing manufacturer, model and numeric specifications
only. The initial split preserved all **2,348 original records**: 606 complete
and 1,742 partial, generating 1,321 WinISD files in `WDR/`. Current counts appear
in the latest successful [generation run](https://github.com/jamescarruthers/speaker-drivers/actions/workflows/regenerate-drivers.yml).
The scripts use Python 3.10 or newer and have no external dependencies.

```text
drivers.csv
drivers_partial.csv
csv_to_wdr.py
regenerate_drivers.py
WDR/
tests/test_csv_to_wdr.py
tests/test_csv_feeds.py
tests/test_regenerate_drivers.py
.github/workflows/regenerate-drivers.yml
```

## CSV feeds and completeness

The existing app feed remains at the same filename and URL:

- [drivers.csv](https://raw.githubusercontent.com/jamescarruthers/speaker-drivers/main/drivers.csv): complete core T/S records.
- [drivers_partial.csv](https://raw.githubusercontent.com/jamescarruthers/speaker-drivers/main/drivers_partial.csv): records missing one or more required fields.

Both files retain the existing column names, order, units and blank-cell format.
Rows are sorted by manufacturer, then model, ignoring letter case. Variants with
matching labels retain their relative order. No values are filled, calculated
or changed by the split or sort, and no metadata columns are added.

A complete record has a nonblank manufacturer and model, and published values in
all of these fields:

```text
impedance_ohm, fs_hz, qts, qes, qms, vas_l, re_ohm, le_mh,
sd_cm2, mms_g, cms_mm_per_n, bl_tm, xmax_mm
```

These numeric values must be finite and positive, except that an explicit zero
inductance is allowed. Additional fields such as Rms, Vd, sensitivity, power
ratings, dimensions and advanced model parameters are optional. They retain
their existing values or blanks. A peak-to-peak excursion value does not fill
a missing `xmax_mm` in the CSV. The rule is implemented by
`missing_full_parameters()` in `csv_to_wdr.py` and checked by the tests.

Completeness describes parameter availability, not independent validation of
every source value or resolution of existing conflicts.

## Edit a driver on GitHub

1. Find the existing row in `drivers.csv` or `drivers_partial.csv`, then use
   GitHub's pencil button to edit that CSV. Enter values in the units named by
   the column headers. Keep every column, leaving unavailable values blank.
2. Commit the change to `main`, or merge your pull request into `main`.
3. Open **Actions → Regenerate driver files** and wait for the run to succeed.
   The workflow commits any generated changes automatically.

The workflow reads both CSVs, moves complete records into `drivers.csv` and
incomplete records into `drivers_partial.csv`, regenerates `WDR/`, and runs the
tests before publishing. Existing row values, optional specifications and the
CSV schema are retained. Both feeds are sorted by manufacturer, then model,
ignoring letter case, so newly complete rows appear beside the same brand's
other drivers. Rows that become incomplete move back to the partial feed. Different parameter
sets for the same model remain separate. Edit an existing row in place rather
than copying it between files. WDR files are generated outputs; edit the CSVs
to change driver specifications.

The feed filenames and raw URLs stay the same, so an app can keep using its
existing URL. It will receive the updated complete feed on its next refresh
after the successful workflow, subject to any HTTP or app caching.

The workflow runs on pushes to `main`. You can also select **Actions →
Regenerate driver files → Run workflow**, using the `main` branch. It uses
GitHub's built-in token; no personal access token or extra secret is required.
Bot commits made with that token do not start another run. The workflow needs
permission to write repository contents. If branch protection blocks its push,
the run fails without bypassing the branch rules. Concurrent runs are queued,
and normal Git pushes prevent overwriting newer edits.

Invalid numbers or malformed CSV rows stop regeneration. In that case, open
the failed run's log, correct the indicated input and commit again. Unresolved
T/S consistency warnings are reported, with supplied values retained. A green
run can leave a driver in the partial feed when required values are still missing.

## Use and regenerate locally

Copy the `.wdr` files into your WinISD driver library, normally
`Documents\WinISD\drivers` on Windows, then reopen WinISD.

From this repository directory, repartition both feeds and regenerate the
library with the same command used by GitHub Actions:

```sh
python regenerate_drivers.py
```

Both CSV files must exist. All records are validated before writing. Stale
`.wdr` files directly inside `WDR/` are removed when drivers are renamed or
deleted. Optional values, numeric precision and duplicate CSV records are
preserved. To check for pending changes without writing anything, run
`python regenerate_drivers.py --check` (exit status 1 means regeneration is
needed or validation failed).

To regenerate only the WDR library, without repartitioning the CSVs:

```sh
python csv_to_wdr.py
```

Use `python3` instead of `python` where required. To inspect skipped rows and
consistency flags without writing files:

```sh
python csv_to_wdr.py --check --verbose
```

An explicit CSV argument selects only that file. For example, export only the
complete core T/S records to a separate directory:

```sh
python csv_to_wdr.py drivers.csv --output WDR_complete
```

Omitting the CSV argument combines both feeds before deduplication and filename
generation, preserving the existing `WDR/` filenames and contents. Passing just
one feed can change collision suffixes within that separately generated subset.

`--clean` removes existing `.wdr` files directly inside the selected output
directory before regenerating it. Use it when removing or renaming CSV records
to avoid leaving stale files. `--include-incomplete` also generates partial
records, which may need additional parameters before they can be used.

## Coverage and data limitations

The WDR converter requires positive **Fs, Qts and Vas**, the minimum parameters
specified in WinISD's bundled help. This is a less strict rule than the complete
CSV feed. In the initial snapshot, it skipped 1,015 records below this minimum and
10 records without a usable manufacturer/model. All of these rows are retained
in `drivers_partial.csv`. Two identical WDR outputs are deduplicated; distinct
parameter sets are preserved.

A missing-value recovery pass examined 1,456 retained PDFs, filled **947 numeric
cells**, recovered four manufacturer names and corrected two numeric cells in
ME650C. In total, 340 records were updated. New values require an exact model
match and compatible existing parameters. Ambiguous component tables, conflicting
revisions, unverified characters and inconsistent parameter sets are held back.
The pass does not establish that every published specification has been captured.

Both Wavecor TW030WA07 records now include the manufacturer's published T/S set,
including Vas **0.059 L**, plus the available geometry and qualified sensitivity.
Dayton Audio ME650C is a complete two-way ceiling speaker: the manufacturer
publishes system specifications, but no bare-woofer Fs/Qts/Vas set in its sheet.
Its sensitivity is corrected to **88 dB at 1 W/1 m**, with the published ±3 dB
tolerance. It remains in `drivers_partial.csv` and is skipped by the default WDR export.
Manufacturer sheets: [Wavecor TW030WA05–08](https://www.wavecor.com/Driver%20specifications%20PDF/TW030WA05_06_07_08_specifications.pdf),
[Wavecor overview](https://www.wavecor.com/Driver%20specifications%20PDF/Driver_specifications_overview.pdf),
[Dayton ME650C](https://www.daytonaudio.com/images/resources/300-430-dayton-audio-me650c-architectural-and-engineering-specification-sheet.pdf).

The consolidated values include unresolved source conflicts. The converter
preserves supplied values without averaging or forcing them to agree. Its
consistency screen initially flagged **54 generated files**: Qts differs by more than 5%
from Qes × Qms / (Qes + Qms), or Fs differs by more than 10% from the resonance
calculated using Mms and Cms. These checks do not identify every possible error.
Use `--check --verbose` to locate the flagged records.

WinISD can reject inconsistent, overdetermined parameter sets in its driver
editor. Check flagged records against the appropriate manufacturer's datasheet
before relying on a simulation. The file structure and units were checked
against driver files bundled with [WinISD 0.7.950](https://www.linearteam.org/).
**Native import into WinISD on Windows has not been tested.**

Manufacturer identifies the catalogue brand; the original equipment factory
is not independently established. A product title is used where a parsed model
code was unavailable. Coaxial component records include `(tweeter)` in their
model name. Different parameter sets for the same model remain separate;
colliding filenames receive a content hash, which is not a revision identifier.

## Driver diameter and physical dimensions

Both CSVs have **29 dedicated dimensional fields**. In the initial snapshot,
**1,541 records** have at
least one populated field. All new lengths use **millimetres**; the existing
`nominal_diameter_in` column retains its original values.

| Measurement | CSV field | Records across both CSVs |
| --- | --- | ---: |
| Advertised driver size | `nominal_diameter_mm` | 792 |
| Published outside/frame diameter | `overall_diameter_mm` | 733 |
| Baffle opening diameter | `cutout_diameter_mm` | 695 |
| Overall depth | `overall_depth_mm` | 725 |
| Depth behind the mounting surface | `mounting_depth_mm` | 9 |
| Voice-coil diameter | `voice_coil_diameter_mm` | 942 |
| Effective diaphragm diameter | `effective_diaphragm_diameter_mm` | 194 |

Nominal size is a catalogue designation, not a machining dimension. For
tweeters it often describes the dome, while the faceplate can be much larger.
Neither nominal size nor effective diaphragm diameter supplies frame diameter.

Other columns retain mounting-hole counts and diameters, bolt-circle diameter,
flange thickness, magnet dimensions, coil and gap heights, and ribbon dimensions.
Width/height/depth are assigned only when the source identifies the axes. Values
in `overall_dimension_1_mm` through `overall_dimension_3_mm`,
`cutout_dimension_1_mm`/`cutout_dimension_2_mm`, and the ribbon dimension columns
retain the published order when the axes or shape are unspecified. A single
unqualified "overall dimension" is not automatically called a diameter.
`tweeter_*` columns describe the tweeter subsystem of a coaxial driver; they do
not supply the woofer's WinISD dimensions.

Dimensions come from retained manufacturer and retailer specifications, with
reviewed manufacturer values preferred and explicit inch/cm units converted to
mm. Existing selected nominal inch values are retained and converted. Unverified
OCR, inconsistent unit pairs, ambiguous ranges, model mismatches and unresolved
source disagreements leave blanks. Near-identical values within the documented
rounding tolerance select one published value; they are never averaged. The
tolerance is the larger of 0.05 mm or 0.1%, and 0.5 mm or 1% for nominal size.
These checks do not constitute independent verification of every dimension.

## CSV and WDR units

CSV headers identify units. Blanks mean missing values; an explicit zero remains
zero. The two UTF-8 CSVs include selected values from the consolidated dataset plus
the supported recovery values and corrections described above. It contains no
source URLs, identifiers, timestamps or audit metadata.

| CSV column | WDR field | Conversion |
| --- | --- | --- |
| `impedance_ohm`, `re_ohm` | `Znom`, `Re` | Ω unchanged |
| `fs_hz`, `ebp_hz` | `Fs`, `EBP` | Hz unchanged |
| `qts`, `qes`, `qms` | `Qts`, `Qes`, `Qms` | unchanged |
| `vas_l` | `Vas` | L × 0.001 → m³ |
| `le_mh`, `le_frequency_hz` | `Le`, `fLe` | mH × 0.001 → H; Hz unchanged |
| `sd_cm2` | `Sd` | cm² × 0.0001 → m² |
| `mms_g` | `Mms` | g × 0.001 → kg |
| `cms_mm_per_n` | `Cms` | mm/N × 0.001 → m/N |
| `rms_ns_per_m`, `bl_tm` | `Rms`, `BL` | N·s/m and T·m unchanged |
| `xmax_mm` | `Xmax` | mm × 0.001 → m |
| `vd_cm3` | `Vd` | cm³ × 0.000001 → m³ |
| `eta0_percent` | `no` | percent × 0.01 → fraction |
| `power_rms_w` | `Pe` | W unchanged |
| `sensitivity_1w_1m_db` | `SPL` | dB, explicitly referenced to 1 W / 1 m |
| `sensitivity_2v83_1m_db` | `USPL` | dB, explicitly referenced to 2.83 V / 1 m |
| `overall_diameter_mm` | `Outer` | mm × 0.001 → m |
| `effective_diaphragm_diameter_mm` | `Dd` | mm × 0.001 → m |
| `voice_coil_diameter_mm` | `Vcd` | mm × 0.001 → m |
| `voice_coil_height_mm`, `gap_height_mm` | `Hc`, `Hg` | mm × 0.001 → m |
| `flange_thickness_mm` | `Thick` | mm × 0.001 → m |
| `magnet_diameter_mm`, `magnet_depth_mm` | `Magnet`, `MagDepth` | mm × 0.001 → m |

The two qualified sensitivity columns and `le_frequency_hz` are populated only
when the source text supplies an unambiguous reference condition. If `xmax_mm`
is blank, `linear_travel_pp_mm` can supply Xmax by dividing the explicitly
peak-to-peak excursion by two and converting mm to m.

Additional values stay in the CSV when no unambiguous WDR mapping is available:
`mmd_g`, `xmech_mm`, `max_travel_pp_mm`, `xlin_mm`, unqualified
`sensitivity_db`, `power_handling_w`, `nominal_diameter_in`, and `qa_as_printed`.
The printed `qa` value is retained as supplied; it is not interpreted as Qms.
Frame diameter is not treated as effective piston diameter.

The remaining dimensions stay in the CSV. In particular, this converter does
not assign cutout diameter to WinISD's `Basket` field or either CSV depth to
`Depth`: those mappings have not been established. Nominal diameter does not
populate the legacy `Dia` field.

Additional columns retain the Wright-model parameters `krm_microohm`, `erm`,
`kxm_mh` and `exm`; these do not replace conventional Le or WinISD's KLe.
Other recovered values include peak power, frequency limits, crossover frequency
and slope, unit/magnet weights, and sensitivity tolerance. Filtered continuous
power is stored in `power_continuous_iec268_5_w`, with its test high-pass frequency
and slope in separate numeric columns. It does not populate unqualified RMS
power or WinISD Pe. These 15 extra fields remain available in the CSV.

Unknown WDR numeric fields use zero, following the bundled WinISD file format;
this does not turn missing CSV data into measured zeros. WDR labels use ASCII
transliteration, filenames are Windows compatible, and line endings are CRLF.
The CSV retains Unicode labels. WDR files omit author, comments and dates.

Electrical values are exported as one equivalent connection (`numVC=1`,
`VCCon=1`). This does not establish the physical voice-coil count. For a
dual-voice-coil driver, verify that the source parameters match the wiring you
intend to simulate. Standard WinISD environmental defaults are `c=343.68 m/s`
and air density `roo=1.20095 kg/m³`.

## Converter checks

```sh
python -m unittest discover -s tests -v
```

Tests cover unit conversion, missing data, sensitivity references, excursion,
conflicting values, physical dimension conversions, filename collisions,
malformed input, filtered power, advanced parameters and regeneration. Feed
tests check completeness and reproduce every published WDR filename and byte.
Workflow tests cover promotion and demotion between feeds, preserving cell
values and duplicate records, invalid-input handling, stale WDR cleanup and
repeatable generation.
