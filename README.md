# Loudspeaker T/S data and WinISD drivers

`drivers.csv` contains **2,348 records** with manufacturer, model and numeric
specifications only, in **76 columns**. `WDR/` contains **1,321 generated WinISD driver files**.
The converter uses Python 3.10 or newer and has no external dependencies.

```text
drivers.csv
csv_to_wdr.py
WDR/
tests/test_csv_to_wdr.py
```

## Use and regenerate

Copy the `.wdr` files into your WinISD driver library, normally
`Documents\WinISD\drivers` on Windows, then reopen WinISD.

From this repository directory, regenerate the library with:

```sh
python csv_to_wdr.py
```

Use `python3` instead of `python` where required. To inspect skipped rows and
consistency flags without writing files:

```sh
python csv_to_wdr.py --check --verbose
```

An alternative CSV and output directory can be supplied:

```sh
python csv_to_wdr.py drivers.csv --output WDR
```

`--clean` removes existing `.wdr` files directly inside the selected output
directory before regenerating it. Use it when removing or renaming CSV records
to avoid leaving stale files. `--include-incomplete` also generates partial
records, which may need additional parameters before they can be used.

## Coverage and data limitations

The default export requires positive **Fs, Qts and Vas**, the minimum parameters
specified in WinISD's bundled help. It skips 1,015 incomplete records and 10
records without a usable manufacturer/model. All these rows remain in the CSV.
Identical WDR outputs are deduplicated; distinct parameter sets are preserved.
Two identical WDR outputs are deduplicated. The CSV retains all source records.

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
tolerance. It remains in the CSV and is skipped by the default WDR export.
Manufacturer sheets: [Wavecor TW030WA05–08](https://www.wavecor.com/Driver%20specifications%20PDF/TW030WA05_06_07_08_specifications.pdf),
[Wavecor overview](https://www.wavecor.com/Driver%20specifications%20PDF/Driver_specifications_overview.pdf),
[Dayton ME650C](https://www.daytonaudio.com/images/resources/300-430-dayton-audio-me650c-architectural-and-engineering-specification-sheet.pdf).

The consolidated values include unresolved source conflicts. The converter
preserves supplied values without averaging or forcing them to agree. Its
consistency screen flags **54 generated files**: Qts differs by more than 5%
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

The CSV has **29 dedicated dimensional fields**. **1,541 records** have at
least one populated field. All new lengths use **millimetres**; the existing
`nominal_diameter_in` column retains its original values.

| Measurement | CSV field | Records |
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
zero. The UTF-8 CSV includes selected values from the consolidated dataset plus
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
malformed input, filtered power, advanced parameters and regeneration. All 15
converter tests pass.
