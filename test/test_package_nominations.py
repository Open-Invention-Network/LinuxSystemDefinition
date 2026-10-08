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
TABLE_CSV = TEST_DIR / 'table-13_2026-08-18.csv'

TABLE_HEADER = 'package_version,description,download_url,version_url,name,project_url,purl\n'


def run(listing, listing_type, table_csv=TABLE_CSV, output_type='json'):
    with tempfile.TemporaryDirectory() as tmp:
        listing_path = pathlib.Path(tmp) / 'listing'
        listing_path.write_text(listing, encoding='utf-8')
        result = subprocess.run([sys.executable, str(SCRIPT), '-l', str(listing_path),
                                 '-c', str(table_csv), '-t', listing_type,
                                 '--output-type', output_type],
                                capture_output=True, text=True, check=True)
    return result.stdout


def run_json(listing, listing_type, **kwargs):
    return {p['package']: p for p in json.loads(run(listing, listing_type, **kwargs))}


def rpm_record(name, version, release, source_rpm, license='MIT', url='https://example.org/',
               description='A package.'):
    return (f"Name        : {name}\n"
            f"Version     : {version}\n"
            f"Release     : {release}\n"
            f"Architecture: x86_64\n"
            f"License     : {license}\n"
            f"Source RPM  : {source_rpm}\n"
            f"URL         : {url}\n"
            f"Summary     : Summary\n"
            f"Description :\n{description}\n")


class RpmTest(unittest.TestCase):

    def test_description_does_not_override_fields(self):
        listing = rpm_record('oin-test-pkg', '1.0', '1.fc39', 'oin-test-pkg-1.0-1.fc39.src.rpm',
                             license='GPLv2+',
                             description='License for binaries is BSD\nVersion control helper\n'
                                         'URL handling\nName System) lookups\n')
        listing += rpm_record('oin-other-pkg', '2.0', '1.fc39', 'oin-other-pkg-2.0-1.fc39.src.rpm',
                              license='Apache-2.0')
        found = run_json(listing, 'rpm')
        self.assertEqual(found['oin-test-pkg']['license'], 'GPLv2+')
        self.assertEqual(found['oin-test-pkg']['version'], '1.0')
        self.assertEqual(found['oin-test-pkg']['url'], 'https://example.org/')
        self.assertEqual(found['oin-other-pkg']['license'], 'Apache-2.0')
        self.assertEqual(len(found), 2)

    def test_license_does_not_leak_between_packages(self):
        listing = rpm_record('oin-test-pkg', '1.0', '1', 'oin-test-pkg-1.0-1.src.rpm', license='GPLv2+')
        listing += ("Name        : oin-nolicense\nVersion     : 1.0\nRelease     : 1\n"
                    "Source RPM  : oin-nolicense-1.0-1.src.rpm\nDescription :\nNone\n")
        found = run_json(listing, 'rpm')
        self.assertEqual(found['oin-nolicense']['license'], '')

    def test_subpackage_with_different_version_uses_source_rpm(self):
        # device-mapper is built from lvm2 but has its own version
        listing = rpm_record('device-mapper', '1.02.197', '1.fc39', 'lvm2-2.03.23-1.fc39.src.rpm')
        listing += rpm_record('oin-sub', '0.1', '3.fc39', 'oin-source-pkg-9.9-3.fc39.src.rpm')
        found = run_json(listing, 'rpm')
        self.assertNotIn('lvm', found)
        self.assertNotIn('lvm2', found)  # in Table 13
        self.assertEqual(found['oin-source-pkg']['version'], '9.9')

    def test_no_source_rpm_is_skipped(self):
        listing = ("Name        : gpg-pubkey\nVersion     : 18b8e74c\nRelease     : 62f2920f\n"
                   "Source RPM  : (none)\nDescription :\nkey\n")
        self.assertEqual(run_json(listing, 'rpm'), {})


class DebTest(unittest.TestCase):

    def test_last_package_source_is_cleaned_up(self):
        listing = ("Package: oin-first\nVersion: 1.0\nHomepage: https://example.org/\n\n"
                   "Package: bind9-host\nSource: bind9 (1:9.18.28-1)\nVersion: 1:9.18.28-1\n\n"
                   "Package: oin-last-bin\nSource: oin-last (2.0-1)\nVersion: 2.0-1\n")
        found = run_json(listing, 'deb')
        self.assertIn('oin-first', found)
        self.assertIn('oin-last', found)
        self.assertNotIn('bind9', found)
        self.assertNotIn('oin-last (2.0-1)', found)


class PipTest(unittest.TestCase):

    def test_name_normalization_and_license(self):
        listing = ("Name: Typing-Extensions\nVersion: 4.12.2\n\n"
                   "Name: Oin_Test.Pkg\nVersion: 1.0\nLicense: Apache License\n"
                   "License-Expression: Apache-2.0\n\n"
                   "Name: oin-test-pkg\nVersion: 1.0\n")
        found = run_json(listing, 'pip')
        self.assertNotIn("Typing-Extensions", found)  # typing_extensions in Table 13
        self.assertEqual(list(found), ['Oin_Test.Pkg'])
        self.assertEqual(found['Oin_Test.Pkg']['license'], 'Apache-2.0')


class OptionsTest(unittest.TestCase):

    def test_output_type_is_case_insensitive(self):
        listing = "Name: oin-test-pkg\nVersion: 1.0\n"
        self.assertIn('oin-test-pkg', run(listing, 'pip', output_type='JSON'))
        self.assertIn('oin-test-pkg', run(listing, 'pip', output_type='Csv'))
        self.assertIn('Name: oin-test-pkg', run(listing, 'pip', output_type='TXT'))

    def test_table_column_order_does_not_matter(self):
        with tempfile.TemporaryDirectory() as tmp:
            table_csv = pathlib.Path(tmp) / 'table.csv'
            table_csv.write_text('name,purl\noin-covered,pkg:generic/oin-covered\n', encoding='utf-8')
            listing = "Name: oin-covered\nVersion: 1.0\n\nName: oin-not-covered\nVersion: 1.0\n"
            found = run_json(listing, 'pip', table_csv=table_csv)
        self.assertEqual(list(found), ['oin-not-covered'])


if __name__ == '__main__':
    unittest.main()
