"""Protect completeness, schema compatibility and stable published WDR paths."""
from collections import Counter
import csv
from decimal import Decimal
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import csv_to_wdr as converter

ROOT = Path(__file__).resolve().parents[1]


class CompletenessTests(unittest.TestCase):
    def complete(self):
        row = {key: Decimal('1') for key in converter.COMPLETE_PARAMETERS}
        row.update(manufacturer='Example', model='Driver')
        return row

    def test_each_required_field_is_required(self):
        complete = self.complete()
        self.assertEqual(converter.missing_full_parameters(complete), [])
        for field in ('manufacturer', 'model', *converter.COMPLETE_PARAMETERS):
            with self.subTest(field=field):
                row = complete.copy()
                row[field] = '' if field in ('manufacturer', 'model') else None
                self.assertEqual(converter.missing_full_parameters(row), [field])

    def test_zero_inductance_valid_but_missing_and_nonfinite_are_not(self):
        row = self.complete()
        row['le_mh'] = Decimal('0')
        self.assertEqual(converter.missing_full_parameters(row), [])
        for value in [None, Decimal('-1'), Decimal('NaN'), Decimal('Infinity')]:
            row['le_mh'] = value
            self.assertIn('le_mh', converter.missing_full_parameters(row))
        row = self.complete()
        row['xmax_mm'] = Decimal('0')
        self.assertIn('xmax_mm', converter.missing_full_parameters(row))

    def test_minimum_parameters_and_excursion_fallback_do_not_mean_full(self):
        row = {'manufacturer':'Example', 'model':'Driver', 'fs_hz':Decimal('40'),
               'qts':Decimal('.4'), 'vas_l':Decimal('50'), 'linear_travel_pp_mm':Decimal('10')}
        self.assertIn('xmax_mm', converter.missing_full_parameters(row))
        self.assertIn('re_ohm', converter.missing_full_parameters(row))
        self.assertEqual(converter.missing_full_parameters(self.complete()), [])

    def test_default_reads_both_feeds_but_explicit_path_reads_only_that_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            header = 'manufacturer,model,fs_hz,qts,vas_l\n'
            full = root / 'drivers.csv'
            partial = root / 'drivers_partial.csv'
            full.write_text(header+'Example,Complete,40,.4,50\n')
            partial.write_text(header+'Example,Partial,50,.5,60\n')
            with patch.object(converter, 'HERE', root):
                self.assertEqual([r['model'] for r in converter.read_inputs()], ['Complete','Partial'])
                self.assertEqual([r['model'] for r in converter.read_inputs(full)], ['Complete'])
                partial.unlink()
                self.assertEqual([r['model'] for r in converter.read_inputs()], ['Complete'])


class PublishedFeedTests(unittest.TestCase):
    def test_feeds_use_the_same_numeric_schema_and_correct_partition(self):
        headers = []
        records = []
        for filename, expect_full in [('drivers.csv', True), ('drivers_partial.csv', False)]:
            with (ROOT/filename).open(newline='', encoding='utf-8') as stream:
                reader = csv.DictReader(stream)
                headers.append(reader.fieldnames)
                raw = list(reader)
            parsed = converter.read_csv(ROOT/filename)
            self.assertTrue(parsed)
            self.assertEqual(len(raw),len(parsed))
            for row in parsed:
                self.assertEqual(not converter.missing_full_parameters(row),expect_full,
                                 f"{filename}: {row['manufacturer']} {row['model']}")
            records.append(Counter(tuple(r[k] for k in reader.fieldnames) for r in raw))
        self.assertEqual(headers[0],headers[1])
        self.assertEqual(headers[0][:2],['manufacturer','model'])
        self.assertEqual(len(headers[0]),76)
        self.assertEqual(set(headers[0][2:]),converter.NUMERIC_COLUMNS)
        self.assertFalse(records[0] & records[1])

    def test_combined_feeds_reproduce_every_published_wdr_filename_and_byte(self):
        expected, _, _ = converter.compile_files(converter.read_inputs())
        actual = {p.name:p.read_bytes() for p in (ROOT/'WDR').glob('*.wdr')}
        self.assertEqual(set(actual),set(expected))
        for name, data in expected.items():
            self.assertEqual(actual[name],data,name)


if __name__ == '__main__':
    unittest.main()
