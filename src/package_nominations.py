#!/usr/bin/env python

# A small script that processes output of various package managers
# and compares it to the Open Invention Network Linux System Definition.
#
# SPDX-License-Identifier: Apache-2.0


import argparse
import csv
import json
import pathlib
import re
import sys

# RPM header lines look like "Name        : bash". Matching on the
# padded key and colon avoids picking up Description text such as
# "License for binaries is ..." as a field.
RPM_FIELD = re.compile(r'^(Name|Version|Release|License|Source RPM|URL|Description)\s*:\s?(.*)$')

def normalize_pip_name(name):
    '''Normalize a Python package name as per PEP 503'''
    return re.sub(r'[-_.]+', '-', name).lower()

ALIASES = {'bind9': 'bind',
           'chardet': 'python-chardet',
           'gnupg2': 'gpg2',
           'grub2': 'grub',
           'gtkmm3.0': 'gtkmm',
           'gtkmm4.0': 'gtkmm',
           'iproute': 'iproute2',
           'libcap2': 'libcap',
           'libonig': 'oniguruma',
           'python3.12': 'python',
           'requests': 'python-requests',
          }

def main(argv):
    parser = argparse.ArgumentParser()

    # the following options are provided on the commandline
    parser.add_argument("-l", "--listing", action="store", dest="listing",
                        help="RPM/DEB/PIP listing", metavar="FILE")

    parser.add_argument("-c", "--csv", action="store", dest="table_csv",
                        help="OIN Linux System Definition table in CSV",
                        metavar="CSV")

    parser.add_argument("-t", "--type", action="store", dest="listing_type",
                        help="File listing type (RPM, DEB, PIP), case insensitive")

    parser.add_argument("-o", "--out", action="store", dest="out_path",
                        help="Output file (or stdout)")

    parser.add_argument("--output-type", action="store", dest="out_type",
                        help="Output type (TXT, JSON, CSV), case insensitive, default: TXT")

    args = parser.parse_args()

    if not args.listing:
        parser.error("File listing missing")

    if not args.table_csv:
        parser.error("Linux System Definition CSV missing")

    if not args.listing_type:
        parser.error("File listing type not provided")

    if not args.out_type:
        args.out_type = 'txt'

    if args.listing_type.lower() not in ['rpm', 'deb', 'pip']:
        parser.error("Unsupported file listing type")

    args.out_type = args.out_type.lower()
    if args.out_type not in ['txt', 'json', 'csv']:
        parser.error("Unsupported output type")

    if args.out_path:
        out = pathlib.Path(args.out_path)
        if out.exists():
            parser.error(f"Path '{out}' already exists")

    # checks for the listing file
    listing = pathlib.Path(args.listing)
    if not listing.exists():
        print(f"Path '{listing}' does not exist", file=sys.stderr)
        sys.exit(1)
    if not listing.is_file():
        print(f"Path '{listing}' is not a file", file=sys.stderr)
        sys.exit(1)

    # checks for the CSV
    table_csv = pathlib.Path(args.table_csv)
    if not table_csv.exists():
        print(f"Path '{table_csv}' does not exist", file=sys.stderr)
        sys.exit(1)
    if not table_csv.is_file():
        print(f"Path '{table_csv}' is not a file", file=sys.stderr)
        sys.exit(1)

    # read the CSV
    oin_packages = {}
    with open(table_csv, encoding='utf-8') as csv_file:
        # use the header row rather than relying on the column order,
        # which depends on the export tool
        csv_reader = csv.DictReader(csv_file)
        if not csv_reader.fieldnames or 'name' not in csv_reader.fieldnames:
            print(f"CSV '{table_csv}' has no 'name' column", file=sys.stderr)
            sys.exit(1)
        for line in csv_reader:
            oin_packages[line['name'].lower()] = {'version': line.get('package_version', ''),
                                                  'dl_url': line.get('download_url', ''),
                                                  'version_url': line.get('version_url', ''),
                                                  'project_url': line.get('project_url', ''),
                                                  'package_url': line.get('purl', '')}

    # Python package names in the table are also matched after
    # PEP 503 normalization (e.g. "typing_extensions" and "typing-extensions")
    oin_pip_packages = {normalize_pip_name(name) for name in oin_packages}

    not_found_packages = []

    if args.listing_type.lower() == 'rpm':
        # walk the RPM listing. Use the "Source RPM" attribute to filter
        # duplicates and to determine the package name. The "URL" attribute
        # is stored to assist with the comparison.
        rpm_packages_seen = set()

        with open(listing, 'r', encoding='utf-8') as rpm_file:
            package = ''
            version = ''
            release = ''
            package_license = ''
            url = ''
            package_type = 'rpm'
            in_description = False
            for line in rpm_file:
                match = RPM_FIELD.match(line)
                if not match:
                    continue
                field, value = match.group(1), match.group(2).strip()

                # The Description is free text and is always the last
                # field of a package, so skip everything until the next
                # package starts.
                if in_description and field != 'Name':
                    continue

                if field == 'Version':
                    version = value
                elif field == 'Release':
                    release = value
                elif field == 'Source RPM':
                    # The source RPM is "name-version-release.src.rpm".
                    # Version and release cannot contain '-', and can
                    # differ from those of a subpackage (for example
                    # device-mapper is built from lvm2), so use the
                    # source RPM's own version. Packages without a source
                    # RPM (such as gpg-pubkey) report "(none)" and are skipped.
                    if value.endswith('.src.rpm') and value.count('-') >= 2:
                        package, version, release = value[:-len('.src.rpm')].rsplit('-', maxsplit=2)
                        if package in ALIASES:
                            package = ALIASES[package]
                elif field == 'License':
                    package_license = value
                elif field == 'URL':
                    url = value
                elif field == 'Description':
                    in_description = True
                elif field == 'Name':
                    if package:
                        if package not in rpm_packages_seen:
                            if package.lower() not in oin_packages:
                                not_found_packages.append({'package': package, 'version': version, 'license': package_license, 'type': package_type, 'url': url})
                        rpm_packages_seen.add(package)
                    package = ''
                    version = ''
                    release = ''
                    package_license = ''
                    url = ''
                    in_description = False
            if package and package not in rpm_packages_seen:
                if package.lower() not in oin_packages:
                    not_found_packages.append({'package': package, 'version': version, 'license': package_license, 'type': package_type, 'url': url})

    elif args.listing_type.lower() == 'deb':
        # walk the Deb listing. Use the "Package" attribute to determine
        # the package name. In case there is a "Source" attribute use that
        # instead.
        deb_packages_seen = set()

        def add_deb_package(package, version, url):
            if '(' in package:
                # sometimes some package names include a version
                # number in brackets that should be cleaned up first
                package = package.split('(')[0].strip()
            if package in ALIASES:
                package = ALIASES[package]
            if package and package not in deb_packages_seen:
                if package.lower() not in oin_packages:
                    not_found_packages.append({'package': package, 'version': version, 'license': '', 'type': 'deb', 'url': url})
                deb_packages_seen.add(package)

        with open(listing, 'r', encoding='utf-8') as deb_file:
            package = ''
            version = ''
            url = ''
            for line in deb_file:
                if line.startswith('Package:'):
                    add_deb_package(package, version, url)

                    # parse the package name, reset all other fields
                    # for a new packages.
                    package = line.split(':', maxsplit=1)[-1].strip()
                    version = ''
                    url = ''
                elif line.startswith('Homepage:'):
                    url = line.split(':', maxsplit=1)[-1].strip()
                elif line.startswith('Version:'):
                    version = line.split(':', maxsplit=1)[-1].strip()
                elif line.startswith('Source:'):
                    package = line.split(':', maxsplit=1)[-1].strip()
            add_deb_package(package, version, url)
    elif args.listing_type.lower() == 'pip':
        pip_packages_seen = set()

        def add_pip_package(package, version, package_license, url):
            name = normalize_pip_name(package)
            if not package or name in pip_packages_seen:
                return
            pip_packages_seen.add(name)
            # try 'python-{package}' as well
            if name not in oin_pip_packages and f'python-{name}' not in oin_pip_packages:
                not_found_packages.append({'package': package, 'version': version, 'license': package_license, 'type': 'pip', 'url': url})

        with open(listing, 'r', encoding='utf-8') as pip_file:
            package = ''
            version = ''
            package_license = ''
            url = ''
            for line in pip_file:
                if line.startswith('Name:'):
                    add_pip_package(package, version, package_license, url)

                    # parse the package name, reset everything
                    package = line.split(':', maxsplit=1)[-1].strip()
                    version = ''
                    package_license = ''
                    url = ''
                elif line.startswith('Home-page:'):
                    url = line.split(':', maxsplit=1)[-1].strip()
                elif line.startswith('License-Expression:'):
                    # an SPDX expression is preferred over the free text License field
                    package_license = line.split(':', maxsplit=1)[-1].strip()
                elif line.startswith('License:') and not package_license:
                    package_license = line.split(':', maxsplit=1)[-1].strip()
                elif line.startswith('Version:'):
                    version = line.split(':', maxsplit=1)[-1].strip()
            add_pip_package(package, version, package_license, url)

    if args.out_type == 'txt':
        if args.out_path:
            try:
                with open(args.out_path, 'w', encoding='utf-8') as out_file:
                    for p in sorted(not_found_packages, key=lambda x: x['package']):
                        out_file.write(f"Name: {p['package']}")
                        out_file.write('\n')
                        out_file.write(f"Version: {p['version']}")
                        out_file.write('\n')
                        out_file.write(f"License: {p['license']}")
                        out_file.write('\n')
                        out_file.write(f"URL: {p['url']}")
                        out_file.write('\n')
                        out_file.write(f"Package type: {p['type']}\n\n")
            except Exception as e:
                print(f'{e}, exiting.', file=sys.stderr)
                sys.exit(1)
        else:
            for p in sorted(not_found_packages, key=lambda x: x['package']):
                print(f"Name: {p['package']}")
                print(f"Version: {p['version']}")
                print(f"License: {p['license']}")
                print(f"URL: {p['url']}")
                print(f"Package type: {p['type']}\n")
    elif args.out_type == 'json':
        if args.out_path:
            try:
                with open(args.out_path, 'w', encoding='utf-8') as out_file:
                    out_file.write(json.dumps(not_found_packages, indent=4))
            except Exception as e:
                print(f'{e}, exiting.', file=sys.stderr)
                sys.exit(1)
        else:
            print(json.dumps(not_found_packages, indent=4))
    elif args.out_type == 'csv':
        if args.out_path:
            try:
                with open(args.out_path, 'w', newline='', encoding='utf-8') as csvfile:
                    csv_writer = csv.writer(csvfile, quoting=csv.QUOTE_MINIMAL)
                    csv_writer.writerow(['Name', 'Version', 'License', 'URL', 'Type'])
                    for p in sorted(not_found_packages, key=lambda x: x['package']):
                        csv_writer.writerow([p['package'], p['version'], p['license'],
                                             p['url'], p['type']])
            except Exception as e:
                print(f'{e}, exiting.', file=sys.stderr)
                sys.exit(1)
        else:
            csv_writer = csv.writer(sys.stdout, quoting=csv.QUOTE_MINIMAL)
            csv_writer.writerow(['Name', 'Version', 'License', 'URL', 'Type'])
            for p in sorted(not_found_packages, key=lambda x: x['package']):
                csv_writer.writerow([p['package'], p['version'], p['license'],
                                     p['url'], p['type']])

if __name__ == "__main__":
    main(sys.argv)
