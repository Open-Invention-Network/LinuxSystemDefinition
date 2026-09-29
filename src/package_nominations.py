#!/usr/bin/env python

# A small script that processes output of various package managers
# and compares it to the Open Invention Network Linux System Definition.
#
# SPDX-License-Identifier: Apache-2.0


import argparse
import csv
import json
import pathlib
import sys

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

    if args.out_type.lower() not in ['txt', 'json', 'csv']:
        parser.error("Unsupported file listing type")

    # sanity checks for the listing file
    listing = pathlib.Path(args.listing)
    if not listing.exists():
        print(f"Path '{listing}' does not exist", file=sys.stderr)
        sys.exit(1)
    if not listing.is_file():
        print(f"Path '{listing}' is not a file", file=sys.stderr)
        sys.exit(1)

    # sanity checks for the CSV
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
        csv_reader = csv.reader(csv_file)
        is_first = True
        for line in csv_reader:
            if is_first:
                is_first = False
                continue
            package_version, description, download_url, version_url, name, project_url, purl = line
            oin_packages[name.lower()] = {'version': package_version, 'dl_url': download_url,
                                          'version_url': version_url, 'project_url': project_url,
                                          'package_url': purl}

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
            for line in rpm_file:
                if line.startswith('Version'):
                    version = line.split(':', maxsplit=1)[-1].strip()
                elif line.startswith('Release'):
                    release = line.split(':', maxsplit=1)[-1].strip()
                elif line.startswith('Source RPM'):
                    avr = f'-{version}-{release}'
                    package = line.split(':', maxsplit=1)[-1].strip()[:-8 - len(avr)]
                    if package in ALIASES:
                        package = ALIASES[package]
                elif line.startswith('License'):
                    package_license = line.split(':', maxsplit=1)[-1].strip()
                elif line.startswith('URL'):
                    url = line.split(':', maxsplit=1)[-1].strip()
                elif line.startswith('Name'):
                    if package:
                        if package not in rpm_packages_seen:
                            if package.lower() not in oin_packages:
                                not_found_packages.append({'package': package, 'version': version, 'license': package_license, 'type': package_type, 'url': url})
                        rpm_packages_seen.add(package)
                    package = ''
                    version = ''
                    release = ''
                    package__license = ''
                    url = ''
            if package not in rpm_packages_seen:
                if package.lower() not in oin_packages:
                    not_found_packages.append({'package': package, 'version': version, 'license': package_license, 'type': package_type, 'url': url})

    elif args.listing_type.lower() == 'deb':
        # walk the Deb listing. Use the "Package" attribute to determine
        # the package name. In case there is a "Source" attribute use that
        # instead.
        deb_packages_seen = set()

        with open(listing, 'r', encoding='utf-8') as deb_file:
            package = ''
            version = ''
            url = ''
            package_license = ''
            package_type = 'deb'
            for line in deb_file:
                if line.startswith('Package:'):
                    if '(' in package:
                        # sometimes some package names include a version
                        # number in brackets that should be cleaned up first
                        package = package.split('(')[0].strip()
                    if package in ALIASES:
                        package = ALIASES[package]
                    if package:
                        if package not in deb_packages_seen:
                            if package.lower() not in oin_packages:
                                not_found_packages.append({'package': package, 'version': version, 'license': package_license, 'type': package_type, 'url': url})
                        deb_packages_seen.add(package)

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
            if package and package not in deb_packages_seen:
                if package.lower() not in oin_packages:
                    not_found_packages.append({'package': package, 'version': version, 'license': package_license, 'type': package_type, 'url': url})
    elif args.listing_type.lower() == 'pip':
        with open(listing, 'r', encoding='utf-8') as pip_file:
            package = ''
            version = ''
            package_license = ''
            url = ''
            package_type = 'pip'
            for line in pip_file:
                if line.startswith('Name:'):
                    if package:
                        if package.lower() not in oin_packages:
                            # try 'python-{package}' as well
                            if f'python-{package.lower()}' not in oin_packages:
                                not_found_packages.append({'package': package, 'version': version, 'license': package_license, 'type': package_type, 'url': url})

                    # parse the package name, reset everything
                    package = line.split(':', maxsplit=1)[-1].strip()
                    version = ''
                    package_license = ''
                    url = ''
                elif line.startswith('Home-page:'):
                    url = line.split(':', maxsplit=1)[-1].strip()
                elif line.startswith('License'):
                    package_license = line.split(':', maxsplit=1)[-1].strip()
                elif line.startswith('Version:'):
                    version = line.split(':', maxsplit=1)[-1].strip()
            if package:
                if package.lower() not in oin_packages:
                    if f'python-{package.lower()}' not in oin_packages:
                        not_found_packages.append({'package': package, 'version': version, 'license': package_license, 'type': package_type, 'url': url})


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
                with open(args.out_path, 'w', newline='') as csvfile:
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
