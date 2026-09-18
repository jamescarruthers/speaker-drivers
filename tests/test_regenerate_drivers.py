"""Exercise editing, feed transitions and safe regeneration in disposable repos."""

from collections import Counter
import contextlib
import csv
import io
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import csv_to_wdr as converter
import regenerate_drivers as regenerate


class RegenerationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.header = ['manufacturer', 'model', *sorted(converter.NUMERIC_COLUMNS)]
        self.write('drivers.csv', [])
        self.write('drivers_partial.csv', [])

    def driver(self, model='Driver', **values):
        row = dict.fromkeys(self.header, '')
        row.update(dict.fromkeys(converter.COMPLETE_PARAMETERS, '1'))
        row.update(manufacturer='Example', model=model)
        row.update(values)
        return row

    def write(self, filename, rows, header=None):
        with (self.root / filename).open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, header or self.header, lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)

    def read(self, filename):
        with (self.root / filename).open(encoding='utf-8', newline='') as stream:
            return list(csv.DictReader(stream))

    def execute(self, *arguments):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return regenerate.main(['--root', str(self.root), *arguments])

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes()
                for p in self.root.rglob('*') if p.is_file()}

    def test_edit_promotes_complete_driver_and_demotes_newly_incomplete_driver(self):
        row = self.driver(bl_tm='')
        self.write('drivers_partial.csv', [row])
        self.assertEqual(self.execute(), 0)
        self.assertEqual(self.read('drivers.csv'), [])
        row['bl_tm'] = '3.1400'
        self.write('drivers_partial.csv', [row])
        self.assertEqual(self.execute(), 0)
        self.assertEqual(self.read('drivers.csv'), [row])
        self.assertEqual(self.read('drivers_partial.csv'), [])
        self.assertIn(b'BL=3.14\r\n', next((self.root / 'WDR').glob('*.wdr')).read_bytes())
        row['xmax_mm'] = ''
        self.write('drivers.csv', [row])
        self.assertEqual(self.execute(), 0)
        self.assertEqual(self.read('drivers.csv'), [])
        self.assertEqual(self.read('drivers_partial.csv'), [row])
        self.assertEqual(self.execute('--check'), 0)

    def test_every_cell_variant_and_duplicate_is_preserved(self):
        full = self.driver(model='Name, "quoted" Ω', manufacturer='Müller',
                           le_mh='0', fs_hz='4.000E1', overall_depth_mm=' 88.00 ')
        partial = self.driver(model='Name, "quoted" Ω', manufacturer='Müller',
                              bl_tm='', sensitivity_db='89.300', nominal_diameter_mm='165.10')
        self.write('drivers.csv', [partial])
        self.write('drivers_partial.csv', [full, full.copy(), partial.copy()])
        before = Counter(tuple(r[k] for k in self.header) for r in [partial, full, full, partial])
        self.assertEqual(self.execute(), 0)
        after = self.read('drivers.csv') + self.read('drivers_partial.csv')
        self.assertEqual(Counter(tuple(r[k] for k in self.header) for r in after), before)
        self.assertEqual(self.read('drivers.csv'), [full, full])
        self.assertEqual(self.read('drivers_partial.csv'), [partial, partial])
        self.assertEqual(len(list((self.root / 'WDR').glob('*.wdr'))), 2)

    def test_bad_input_leaves_both_feeds_and_existing_wdr_untouched(self):
        self.write('drivers.csv', [self.driver()])
        self.assertEqual(self.execute(), 0)
        for value in ['NaN', 'Infinity', '-1', 'not a number']:
            with self.subTest(value=value):
                self.write('drivers_partial.csv', [self.driver(fs_hz=value)])
                before = self.snapshot()
                self.assertEqual(self.execute(), 1)
                self.assertEqual(self.snapshot(), before)
        self.write('drivers_partial.csv', [self.driver()])
        with (self.root / 'drivers_partial.csv').open('a') as stream:
            stream.write('Example,broken,40\n')
        before = self.snapshot()
        self.assertEqual(self.execute(), 1)
        self.assertEqual(self.snapshot(), before)

    def test_missing_feed_and_changed_column_order_fail_without_writing(self):
        self.write('drivers.csv', [self.driver()])
        self.assertEqual(self.execute(), 0)
        header = self.header.copy()
        header[2], header[3] = header[3], header[2]
        self.write('drivers_partial.csv', [], header=header)
        before = self.snapshot()
        self.assertEqual(self.execute(), 1)
        self.assertEqual(self.snapshot(), before)
        (self.root / 'drivers_partial.csv').unlink()
        before = self.snapshot()
        self.assertEqual(self.execute(), 1)
        self.assertEqual(self.snapshot(), before)

    def test_removed_and_renamed_drivers_do_not_leave_stale_wdr(self):
        row = self.driver()
        self.write('drivers.csv', [row])
        self.assertEqual(self.execute(), 0)
        old = next((self.root / 'WDR').glob('*.wdr'))
        notes = self.root / 'WDR' / 'notes.txt'
        notes.write_text('keep')
        nested = self.root / 'WDR' / 'archive'
        nested.mkdir()
        (nested / 'saved.wdr').write_bytes(b'keep')
        row['model'] = 'Renamed'
        self.write('drivers.csv', [row])
        self.assertEqual(self.execute(), 0)
        self.assertFalse(old.exists())
        self.assertEqual(len(list((self.root / 'WDR').glob('*.wdr'))), 1)
        self.write('drivers.csv', [])
        self.assertEqual(self.execute(), 0)
        self.assertEqual(list((self.root / 'WDR').glob('*.wdr')), [])
        self.assertEqual(notes.read_text(), 'keep')
        self.assertEqual((nested / 'saved.wdr').read_bytes(), b'keep')

    def test_check_is_read_only_and_second_generation_changes_nothing(self):
        self.write('drivers_partial.csv', [self.driver()])
        before = self.snapshot()
        self.assertEqual(self.execute('--check'), 1)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.execute(), 0)
        before = self.snapshot()
        times = {p: p.stat().st_mtime_ns for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(self.execute('--check'), 0)
        self.assertEqual(self.execute(), 0)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual({p: p.stat().st_mtime_ns for p in times}, times)


if __name__ == '__main__':
    unittest.main()
