# Tests for package_nominations.py
#
# Run with: python -m unittest discover -s test
#
# SPDX-License-Identifier: Apache-2.0

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

TEST_DIR = pathlib.Path(__file__).resolve().parent
SCRIPT = TEST_DIR.parent / 'src' / 'package_nominations.py'

TABLE_HEADER = 'package_version,description,download_url,version_url,name,project_url,purl\n'


def table_row(name, version='1.0', description='In the table'):
    return f'{version},{description},,,{name},,\n'


def run(listing, listing_type, table, *extra, check=True):
    '''Run the script on a listing and a table (both given as text)'''
    with tempfile.TemporaryDirectory() as tmp:
        listing_path = pathlib.Path(tmp) / 'listing'
        listing_path.write_text(listing, encoding='utf-8')
        table_path = pathlib.Path(tmp) / 'table.csv'
        table_path.write_text(table, encoding='utf-8')
        return subprocess.run([sys.executable, str(SCRIPT), '-l', str(listing_path),
                               '-c', str(table_path), '-t', listing_type,
                               '--output-type', 'json', *extra],
                              capture_output=True, text=True, check=check)


def run_json(listing, listing_type, table, *extra):
    result = run(listing, listing_type, table, *extra)
    return {p['package']: p for p in json.loads(result.stdout)}


class TableCsvTest(unittest.TestCase):
    '''Issue #16: the table is read by its header, not by column position'''

    LISTING = 'Name: oin-covered\nVersion: 1.0\n\nName: oin-not-covered\nVersion: 1.0\n'

    def test_column_order_does_not_matter(self):
        table = 'name,purl,package_version\noin-covered,pkg:generic/oin-covered,1.0\n'
        self.assertEqual(list(run_json(self.LISTING, 'pip', table)), ['oin-not-covered'])

    def test_extra_columns_are_ignored(self):
        table = ('package_version,description,download_url,version_url,name,project_url,purl,license\n'
                 + '1.0,Covered,,,oin-covered,,,MIT\n')
        self.assertEqual(list(run_json(self.LISTING, 'pip', table)), ['oin-not-covered'])

    def test_no_name_column_is_an_error(self):
        result = run(self.LISTING, 'pip', 'package,version\noin-covered,1.0\n', check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("no 'name' column", result.stderr)


class DebTest(unittest.TestCase):
    '''Issue #24: the last package of a DEB listing is cleaned up like the others'''

    def test_last_package_version_in_brackets_is_removed(self):
        listing = ('Package: oin-first\nVersion: 1.0\n\n'
                   'Package: oin-last-bin\nSource: oin-last (2.0-1)\nVersion: 2.0-1\n')
        found = run_json(listing, 'deb', TABLE_HEADER)
        self.assertEqual(sorted(found), ['oin-first', 'oin-last'])

    def test_last_package_is_aliased(self):
        # bind9 is listed as bind in the table
        listing = ('Package: oin-first\nVersion: 1.0\n\n'
                   'Package: bind9-host\nSource: bind9 (1:9.18.28-1)\nVersion: 1:9.18.28-1\n')
        found = run_json(listing, 'deb', TABLE_HEADER + table_row('bind', '9.18.0'))
        self.assertEqual(list(found), ['oin-first'])


class PipTest(unittest.TestCase):

    def test_names_are_matched_after_normalization(self):
        listing = 'Name: Typing_Extensions\nVersion: 4.12.2\n\nName: oin-new\nVersion: 1.0\n'
        found = run_json(listing, 'pip', TABLE_HEADER + table_row('typing-extensions', '4.12.2'))
        self.assertEqual(list(found), ['oin-new'])

    def test_python_prefix_is_matched_after_normalization(self):
        listing = 'Name: Oin.Lib\nVersion: 1.0\n'
        self.assertEqual(run_json(listing, 'pip', TABLE_HEADER + table_row('python-oin-lib')), {})

    def test_exact_name_is_preferred_to_a_normalized_one(self):
        # both forms are in the table; the listed name matches the second exactly
        listing = 'Name: charset-normalizer\nVersion: 3.3.2\n'
        table = TABLE_HEADER + table_row('charset_normalizer', '2.1.0') + table_row('python-charset-normalizer', '3.4.0')
        self.assertEqual(run_json(listing, 'pip', table, '--new-versions'), {})

    def test_duplicates_are_reported_once(self):
        listing = 'Name: oin-test-pkg\nVersion: 1.0\n\nName: OIN_Test.Pkg\nVersion: 1.0\n'
        self.assertEqual(len(run_json(listing, 'pip', TABLE_HEADER)), 1)

    def test_license_expression_is_preferred(self):
        for fields in ['License: Apache License\nLicense-Expression: Apache-2.0\n',
                       'License-Expression: Apache-2.0\nLicense: Apache License\n']:
            listing = f'Name: oin-new\nVersion: 1.0\n{fields}'
            self.assertEqual(run_json(listing, 'pip', TABLE_HEADER)['oin-new']['license'], 'Apache-2.0')
        listing = 'Name: oin-new\nVersion: 1.0\nLicense: MIT\n'
        self.assertEqual(run_json(listing, 'pip', TABLE_HEADER)['oin-new']['license'], 'MIT')

    def test_update_of_the_last_package(self):
        # the last package used to fail with a NameError when it was in the table
        listing = 'Name: oin-first\nVersion: 2.0\n\nName: oin-last\nVersion: 2.0\n'
        table = TABLE_HEADER + table_row('oin-first') + table_row('oin-last', description='From the table')
        found = run_json(listing, 'pip', table, '--new-versions')
        self.assertEqual(sorted(found), ['oin-first', 'oin-last'])
        self.assertEqual(found['oin-last']['status'], 'update')
        self.assertEqual(found['oin-last']['description'], 'From the table')


if __name__ == '__main__':
    unittest.main()
