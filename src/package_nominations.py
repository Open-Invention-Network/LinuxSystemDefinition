#!/usr/bin/env python

# A small script that processes output of various package managers
# and compares it to the Open Invention Network Linux System Definition.
#
# SPDX-License-Identifier: Apache-2.0


import argparse
import csv
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

    args = parser.parse_args()

    if not args.listing:
        parser.error("File listing missing")

    if not args.table_csv:
        parser.error("Linux System Definition CSV missing")

    if not args.listing_type:
        parser.error("File listing type not provided")

    if args.listing_type.lower() not in ['rpm', 'deb', 'pip']:
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

    if args.listing_type.lower() == 'rpm':
        # walk the RPM listing. Use the "Source RPM" attribute to filter
        # duplicates and to determine the package name. The "URL" attribute
        # is stored to assist with the comparison.
        rpm_packages_seen = set()

        with open(listing, 'r', encoding='utf-8') as rpm_file:
            package = ''
            version = ''
            release = ''
            rpm_license = ''
            url = ''
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
                    rpm_license = line.split(':', maxsplit=1)[-1].strip()
                elif line.startswith('URL'):
                    url = line.split(':', maxsplit=1)[-1].strip()
                elif line.startswith('Name'):
                    if package:
                        if package not in rpm_packages_seen:
                            if package.lower() not in oin_packages:
                                print(f'Name: {package}')
                                print(f'Version: {version}')
                                print(f'License: {rpm_license}')
                                print(f'URL: {url}\n')
                        rpm_packages_seen.add(package)
                    package = ''
                    version = ''
                    release = ''
                    rpm_license = ''
                    url = ''
            if package not in rpm_packages_seen:
                if package.lower() not in oin_packages:
                    print(f'Name: {package}')
                    print(f'Version: {version}')
                    print(f'License: {rpm_license}')
                    print(f'URL: {url}\n')

    elif args.listing_type.lower() == 'deb':
        # walk the Deb listing. Use the "Package" attribute to determine
        # the package name. In case there is a "Source" attribute use that
        # instead.
        deb_packages_seen = set()

        with open(listing, 'r', encoding='utf-8') as deb_file:
            package = ''
            version = ''
            url = ''
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
                                print(f'Name: {package}')
                                print(f'Version: {version}')
                                print(f'URL: {url}\n')
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
                    print(f'Name: {package}')
                    print(f'Version: {version}')
                    print(f'URL: {url}')
    elif args.listing_type.lower() == 'pip':
        with open(listing, 'r', encoding='utf-8') as pip_file:
            package = ''
            version = ''
            pip_license = ''
            url = ''
            for line in pip_file:
                if line.startswith('Name:'):
                    if package:
                        if package.lower() not in oin_packages:
                            # try 'python-{package}' as well
                            if f'python-{package.lower()}' not in oin_packages:
                                print(f'Name: {package}')
                                print(f'Version: {version}')
                                print(f'License: {pip_license}')
                                print(f'URL: {url}\n')

                    # parse the package name, reset everything
                    package = line.split(':', maxsplit=1)[-1].strip()
                    version = ''
                    pip_license = ''
                    url = ''
                elif line.startswith('Home-page:'):
                    url = line.split(':', maxsplit=1)[-1].strip()
                elif line.startswith('License'):
                    pip_license = line.split(':', maxsplit=1)[-1].strip()
                elif line.startswith('Version:'):
                    version = line.split(':', maxsplit=1)[-1].strip()
            if package:
                if package.lower() not in oin_packages:
                    if f'python-{package.lower()}' not in oin_packages:
                        print(f'Name: {package}')
                        print(f'Version: {version}')
                        print(f'License: {pip_license}')
                        print(f'URL: {url}')

if __name__ == "__main__":
    main(sys.argv)
