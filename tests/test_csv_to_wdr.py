"""Run with: python -m unittest discover -s tests -v"""

import configparser
import contextlib
import csv
from decimal import Decimal
import io
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import csv_to_wdr as converter


def driver(**changes):
    row = {"line": 2, "manufacturer": "Example", "model": "Test",
           "fs_hz": Decimal("40"), "qts": Decimal("0.4"), "vas_l": Decimal("50")}
    row.update({key: (None if value is None else Decimal(str(value)))
                for key, value in changes.items()})
    return row


def parameters(content):
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    parser.read_string(content.decode("ascii") if isinstance(content, bytes) else content)
    return dict(parser["Driver"])


class ConversionTests(unittest.TestCase):
    def test_filtered_tweeter_power_and_wright_model_stay_separate(self):
        row = driver(power_continuous_iec268_5_w=50, power_test_highpass_hz=2000,
                     power_test_highpass_slope_db_per_oct=12, krm_microohm=67,
                     erm=.91, kxm_mh=5.1, exm=.56, power_peak_w=70)
        data = parameters(converter.to_wdr(row))
        self.assertEqual(data['Pe'], '0')
        self.assertEqual(data['KLe'], '0')
        self.assertEqual(data['Le'], '0')

    def test_physical_dimensions_are_distinct_and_converted_to_metres(self):
        row = driver(nominal_diameter_mm=165, overall_diameter_mm=182.2,
                     effective_diaphragm_diameter_mm=142, voice_coil_diameter_mm=38,
                     voice_coil_height_mm=18, gap_height_mm=5, flange_thickness_mm=6,
                     magnet_diameter_mm=110, magnet_depth_mm=30, overall_depth_mm=80,
                     mounting_depth_mm=74, cutout_diameter_mm=156, bolt_circle_diameter_mm=168)
        data = parameters(converter.to_wdr(row))
        expected = {'Outer': '0.1822', 'Dd': '0.142', 'Vcd': '0.038', 'Hc': '0.018',
                    'Hg': '0.005', 'Thick': '0.006', 'Magnet': '0.11', 'MagDepth': '0.03'}
        for key, value in expected.items():
            self.assertEqual(Decimal(data[key]), Decimal(value), key)
        self.assertEqual(data['Dia'], '0')
        self.assertEqual(data['Basket'], '0')
        self.assertEqual(data['Depth'], '0')

    def test_nominal_and_component_sizes_do_not_supply_frame_or_piston_diameter(self):
        data = parameters(converter.to_wdr(driver(nominal_diameter_in=6.5,
                          nominal_diameter_mm=165.1, cone_dome_diameter_mm=25,
                          tweeter_voice_coil_diameter_mm=26, overall_dimension_1_mm=180)))
        for key in ('Outer', 'Dd', 'Vcd', 'Dia'):
            self.assertEqual(data[key], '0')

    def test_si_units_and_explicit_reference_conditions(self):
        row = driver(impedance_ohm=8, fs_hz=40, qts="0.4", qes="0.45", qms=5,
                     vas_l=50, re_ohm="6.2", le_mh="0.8", le_frequency_hz=1000,
                     sd_cm2=330, mms_g=60, cms_mm_per_n="0.25", rms_ns_per_m="1.2",
                     bl_tm=12, xmax_mm=6, vd_cm3=198, eta0_percent="0.7", ebp_hz=89,
                     power_rms_w=150, sensitivity_1w_1m_db=91, sensitivity_2v83_1m_db=92)
        actual = parameters(converter.to_wdr(row))
        expected = {"Znom": "8", "Fs": "40", "Qts": "0.4", "Qes": "0.45", "Qms": "5",
                    "Vas": "0.05", "Re": "6.2", "Le": "0.0008", "fLe": "1000",
                    "Sd": "0.033", "Mms": "0.06", "Cms": "0.00025", "Rms": "1.2",
                    "BL": "12", "Xmax": "0.006", "Vd": "0.000198", "no": "0.007",
                    "EBP": "89", "Pe": "150", "SPL": "91", "USPL": "92"}
        for key, value in expected.items():
            with self.subTest(key=key):
                self.assertEqual(Decimal(actual[key]), Decimal(value))

    def test_ambiguous_fields_are_not_guessed(self):
        data = parameters(converter.to_wdr(driver(sensitivity_db=95, power_handling_w=200,
                           nominal_diameter_in=12, xlin_mm=8, xmech_mm=20, mmd_g=30,
                           qa_as_printed=7)))
        for key in ("SPL", "USPL", "Pe", "Dia", "Dd", "Xmax", "Mms", "Qms"):
            self.assertEqual(data[key], "0", key)

    def test_peak_to_peak_excursion_fallback_and_explicit_zero(self):
        for xmax, expected in ((None, "0.005"), (0, "0"), (6, "0.006")):
            data = parameters(converter.to_wdr(driver(xmax_mm=xmax, linear_travel_pp_mm=10)))
            self.assertEqual(data["Xmax"], expected)

    def test_minimum_parameters_and_incomplete_option(self):
        rows = [driver(), driver(qts=None), driver(vas_l=0)]
        files, counts, _ = converter.compile_files(rows)
        self.assertEqual(len(files), 1)
        self.assertEqual(counts["incomplete"], 2)
        files, counts, _ = converter.compile_files(rows, include_incomplete=True)
        self.assertEqual(len(files), 3)
        self.assertEqual(counts["partial_files"], 2)

    def test_missing_identity_is_skipped(self):
        row = driver()
        row["manufacturer"] = ""
        self.assertEqual(converter.compile_files([row])[1]["missing_identity"], 1)

    def test_distinct_parameter_sets_survive_case_insensitive_collisions(self):
        one, two, three = driver(), driver(fs_hz=42), driver(fs_hz=45)
        two["model"] = "test"
        three["model"] = "Test"
        files, counts, _ = converter.compile_files([one, two, three, one.copy()])
        self.assertEqual(len(files), 3)
        self.assertEqual(counts["duplicates"], 1)
        self.assertEqual(len({name.casefold() for name in files}), 3)
        self.assertEqual({parameters(data)["Fs"] for data in files.values()}, {"40", "42", "45"})
        self.assertEqual(files, converter.compile_files([three, two, one])[0])

    def test_windows_safe_names_and_legacy_encoding(self):
        row = driver()
        row.update(manufacturer="Müller", model='../../A: B Ω\n[Injected]')
        files, _, _ = converter.compile_files([row])
        name, content = next(iter(files.items()))
        self.assertFalse(any(char in name for char in '<>:"/\\|?*'))
        self.assertNotIn(b"\n", content.replace(b"\r\n", b""))
        self.assertTrue(content.endswith(b"\r\n"))
        values = parameters(content)
        self.assertEqual(values["Brand"], "Muller")
        self.assertIn("ohm", values["Model"])
        self.assertFalse({"ProvidedBy", "Comment", "DateAdded", "DateModified"} & values.keys())
        self.assertEqual(converter.safe_stem("CON.txt"), "_CON.txt")

    def test_consistency_screen_preserves_input(self):
        row = driver(qts="0.8", qes="0.4", qms=4)
        files, counts, details = converter.compile_files([row])
        self.assertEqual(counts["consistency_warnings"], 1)
        self.assertEqual(parameters(next(iter(files.values())))["Qts"], "0.8")
        self.assertIn("Qts differs", details[0])

    def test_csv_blanks_zero_and_quoted_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.csv"
            path.write_text('manufacturer,model,fs_hz,qts,vas_l,xmax_mm,le_mh\n'
                            'Example,"Name, with comma",40,0.4,50,0,\n', encoding="utf-8")
            row = converter.read_csv(path)[0]
            self.assertEqual(row["model"], "Name, with comma")
            self.assertEqual(row["xmax_mm"], Decimal(0))
            self.assertIsNone(row["le_mh"])

    def test_bad_csv_cannot_delete_existing_files(self):
        header = "manufacturer,model,fs_hz,qts,vas_l\n"
        malformed = [header + f"Example,Test,{value},0.4,50\n" for value in ("NaN", "inf", "-1", "word")]
        malformed += [header + "Example,Test,40,0.4\n", header + 'Example,"unclosed,40,0.4,50\n',
                      "manufacturer,model,fs_hz,qts,qts,vas_l\nExample,Test,40,0.4,0.4,50\n"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "WDR"
            output.mkdir()
            sentinel = output / "existing.wdr"
            sentinel.write_bytes(b"Keep this")
            for content in malformed:
                with self.subTest(content=content):
                    path = root / "bad.csv"
                    path.write_text(content, encoding="utf-8")
                    with contextlib.redirect_stderr(io.StringIO()):
                        result = converter.main([str(path), "-o", str(output), "--clean"])
                    self.assertEqual(result, 1)
                    self.assertEqual(sentinel.read_bytes(), b"Keep this")

    def test_regeneration_and_clean_scope(self):
        files, _, _ = converter.compile_files([driver()])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            converter.write_files(files, root)
            before = {path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in root.iterdir()}
            converter.write_files(files, root)
            after = {path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in root.iterdir()}
            self.assertEqual(before, after)
            (root / "stale.wdr").write_bytes(b"old")
            (root / "notes.txt").write_bytes(b"keep")
            (root / "subdir").mkdir()
            (root / "subdir" / "keep.wdr").write_bytes(b"keep")
            converter.write_files(files, root, clean=True)
            self.assertFalse((root / "stale.wdr").exists())
            self.assertTrue((root / "notes.txt").exists())
            self.assertTrue((root / "subdir" / "keep.wdr").exists())

    def test_check_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "input.csv"
            path.write_text("manufacturer,model,fs_hz,qts,vas_l\nExample,Test,40,0.4,50\n")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(converter.main([str(path), "-o", str(root / "WDR"), "--check"]), 0)
            self.assertFalse((root / "WDR").exists())


if __name__ == "__main__":
    unittest.main()
