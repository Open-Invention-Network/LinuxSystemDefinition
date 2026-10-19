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


def normalize_pip_name(name):
    '''Normalize a Python package name as in PEP 503, for example
    "Typing_Extensions" and "typing-extensions" are the same package'''
    return re.sub(r'[-_.]+', '-', name).lower()


def main(argv):
    parser = argparse.ArgumentParser()

    # the following options are provided on the commandline
    parser.add_argument("-l", "--listing", action="store", dest="listing",
                        help="RPM/DEB/PIP listing", metavar="FILE")

    parser.add_argument("-c", "--csv", action="store", dest="table_csv",
                        help="OIN Linux System Definition table in CSV",
                        metavar="CSV")

    parser.add_argument("--new-versions", action="store_true", dest="new_versions",
                        help="Report packages with newer versions")

    parser.add_argument("-t", "--type", action="store", dest="listing_type",
                        help="File listing type (RPM, DEB, PIP), case insensitive")

    parser.add_argument("-o", "--out", action="store", dest="out_path",
                        help="Output file (or stdout)")

    parser.add_argument("--output-type", action="store", dest="out_type",
                        help="Output type (TXT, JSON, CSV, OIN_CSV), case insensitive, default: TXT")

    args = parser.parse_args()

    if not args.listing:
        parser.error("File listing missing")

    if not args.table_csv:
        parser.error("Linux System Definition CSV missing")

    if not args.listing_type:
        parser.error("File listing type not provided")

    if not args.out_type:
        args.out_type = 'txt'
    args.out_type = args.out_type.lower()

    if args.listing_type.lower() not in ['rpm', 'deb', 'pip']:
        parser.error("Unsupported file listing type")

    if args.out_type not in ['txt', 'json', 'csv', 'oin_csv']:
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
        # use the header row rather than the column order, which can differ
        # between exports, and ignore any extra columns
        csv_reader = csv.DictReader(csv_file)
        if not csv_reader.fieldnames or 'name' not in csv_reader.fieldnames:
            print(f"CSV '{table_csv}' has no 'name' column", file=sys.stderr)
            sys.exit(1)
        for line in csv_reader:
            name = line['name'] or ''
            if not name:
                continue
            oin_packages[name.lower()] = {'version': line.get('package_version') or '',
                                          'dl_url': line.get('download_url') or '',
                                          'version_url': line.get('version_url') or '',
                                          'project_url': line.get('project_url') or '',
                                          'package_url': line.get('purl') or '',
                                          'description': line.get('description') or '',
                                          'name': name}

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
            summary = ''
            description = ''
            package_type = 'rpm'
            in_description = False
            for line in rpm_file:
                if re.match(r'^Version\s*:', line):
                    version = line.split(':', maxsplit=1)[-1].strip()
                elif re.match(r'^Release\s*:', line):
                    release = line.split(':', maxsplit=1)[-1].strip()
                elif re.match(r'^Source RPM\s*:', line):
                    srpm_name = line.split(':', maxsplit=1)[-1].strip()
                    if srpm_name != '(none)':
                        srpm_base = srpm_name.removesuffix('.src.rpm').removesuffix('.nosrc.rpm')
                        package = srpm_base.rsplit('-', 2)[0]
                        package = ALIASES.get(package, package)
                    else:
                        package = ALIASES.get(package, package)
                elif re.match(r'^License\s*:', line):
                    package_license = line.split(':', maxsplit=1)[-1].strip()
                elif re.match(r'^URL\s*:', line):
                    url = line.split(':', maxsplit=1)[-1].strip()
                elif re.match(r'^Description\s*:', line):
                    description = line.split(':', maxsplit=1)[-1].strip()
                    in_description = True
                elif re.match(r'^Name\s*:', line):
                    if package:
                        if package not in rpm_packages_seen:
                            if package.lower() not in oin_packages:
                                not_found_packages.append({'package': package, 'version': version,
                                                           'license': package_license,
                                                           'type': package_type, 'url': url,
                                                           'description': description,
                                                           'status': 'new'})
                            else:
                                if args.new_versions and oin_packages[package.lower()]['version'] < version:
                                    description = oin_packages[package.lower()]['description']
                                    not_found_packages.append({'package': package, 'version': version,
                                                               'license': package_license,
                                                               'type': package_type, 'url': url,
                                                               'description': description,
                                                               'status': 'update'})
                        rpm_packages_seen.add(package)

                    # as a placeholder record as some packages do not have
                    # a source RPM associated with them.
                    package = line.split(':', maxsplit=1)[1].strip()
                    version = ''
                    release = ''
                    package_license = ''
                    url = ''
                    summary = ''
                    description = ''
                    in_description = False
                elif in_description:
                    description += line

            # store the data for the final package
            if package and package not in rpm_packages_seen:
                if package.lower() not in oin_packages:
                    not_found_packages.append({'package': package, 'version': version,
                                               'license': package_license, 'type': package_type,
                                               'url': url, 'description': description,
                                               'status': 'new'})
                else:
                    if args.new_versions and oin_packages[package.lower()]['version'] < version:
                        description = oin_packages[package.lower()]['description']
                        not_found_packages.append({'package': package, 'version': version,
                                                   'license': package_license, 'type': package_type,
                                                   'url': url, 'description': description,
                                                   'status': 'update'})

    elif args.listing_type.lower() == 'deb':
        # walk the Deb listing. Use the "Package" attribute to determine
        # the package name. In case there is a "Source" attribute use that
        # instead.
        deb_packages_seen = set()

        with open(listing, 'r', encoding='utf-8') as deb_file:
            package = ''
            version = ''
            deb_version = ''
            url = ''
            description = ''
            package_license = ''
            package_type = 'deb'
            in_description = False
            for line in deb_file:
                if line.startswith('Package:'):
                    if '(' in package:
                        # sometimes some package names include a version
                        # number in brackets that should be cleaned up first
                        package = package.split('(', maxsplit=1)[0].strip()
                    package = ALIASES.get(package, package)
                    if package:
                        if package not in deb_packages_seen:
                            if package.lower() not in oin_packages:
                                not_found_packages.append({'package': package, 'version': version,
                                                           'license': package_license,
                                                           'type': package_type, 'url': url,
                                                           'description': description,
                                                           'status': 'new'})
                            else:
                                if args.new_versions and oin_packages[package.lower()]['version'] < deb_version:
                                    description = oin_packages[package.lower()]['description']
                                    not_found_packages.append({'package': package, 'version': version,
                                                               'license': package_license,
                                                               'type': package_type, 'url': url,
                                                               'description': description,
                                                               'status': 'update'})
                        deb_packages_seen.add(package)

                    # parse the package name, reset all other fields for a new package.
                    package = line.split(':', maxsplit=1)[-1].strip()
                    version = ''
                    deb_version = ''
                    url = ''
                    description = ''
                    in_description = False
                elif line.startswith('Homepage:'):
                    url = line.split(':', maxsplit=1)[-1].strip()
                elif line.startswith('Version:'):
                    version = line.split(':', maxsplit=1)[-1].strip()
                    if ':' in version:
                        # remove the Debian epoch if present
                        # https://www.debian.org/doc/debian-policy/ch-controlfields.html#version
                        version = version.split(':', maxsplit=1)[-1]
                    deb_version = re.split(r'[+-]', version)[0]
                elif line.startswith('Source:'):
                    package = line.split(':', maxsplit=1)[-1].strip()
                elif line.startswith('Description:'):
                    description = line.split(':', maxsplit=1)[-1].strip()
                    in_description = True
                elif in_description:
                    description += line

            # store the data for the final package, cleaned up in
            # the same way as the other packages
            if '(' in package:
                package = package.split('(', maxsplit=1)[0].strip()
            package = ALIASES.get(package, package)
            if package and package not in deb_packages_seen:
                if package.lower() not in oin_packages:
                    not_found_packages.append({'package': package, 'version': version,
                                               'license': package_license, 'type': package_type,
                                               'url': url, 'description': description,
                                               'status': 'new'})
                else:
                    if args.new_versions and oin_packages[package.lower()]['version'] < deb_version:
                        description = oin_packages[package.lower()]['description']
                        not_found_packages.append({'package': package, 'version': version,
                                                   'license': package_license, 'type': package_type,
                                                   'url': url, 'description': description,
                                                   'status': 'update'})

    elif args.listing_type.lower() == 'pip':
        # Python package names in the table are matched after PEP 503
        # normalization, so "typing_extensions" matches "typing-extensions"
        oin_pip_packages = {}
        for name in oin_packages:
            oin_pip_packages.setdefault(normalize_pip_name(name), name)

        pip_packages_seen = set()

        def add_pip_package(package, version, package_license, url, description):
            '''Record a package that is not in the table (or newer than in it)'''
            pip_name = normalize_pip_name(package)
            if pip_name in pip_packages_seen:
                return
            pip_packages_seen.add(pip_name)

            # the name, then 'python-{package}', as given; only then
            # the same after normalization
            table_name = None
            for candidate in [package.lower(), f'python-{package.lower()}']:
                if candidate in oin_packages:
                    table_name = candidate
                    break
            if not table_name:
                table_name = (oin_pip_packages.get(pip_name)
                              or oin_pip_packages.get(f'python-{pip_name}'))
            if not table_name:
                not_found_packages.append({'package': package.lower(), 'version': version,
                                           'license': package_license, 'type': 'pip',
                                           'url': url, 'description': description,
                                           'status': 'new'})
            elif args.new_versions and oin_packages[table_name]['version'] < version:
                not_found_packages.append({'package': table_name, 'version': version,
                                           'license': package_license, 'type': 'pip',
                                           'url': url,
                                           'description': oin_packages[table_name]['description'],
                                           'status': 'update'})

        with open(listing, 'r', encoding='utf-8') as pip_file:
            package = ''
            version = ''
            package_license = ''
            license_expression = ''
            url = ''
            description = ''
            for line in pip_file:
                if line.startswith('Name:'):
                    if package:
                        # License-Expression (PEP 639) is an SPDX expression,
                        # so it is preferred over the free-form License
                        add_pip_package(package, version, license_expression or package_license,
                                        url, description)

                    # parse the package name, reset everything
                    package = line.split(':', maxsplit=1)[-1].strip()
                    version = ''
                    package_license = ''
                    license_expression = ''
                    description = ''
                    url = ''
                elif line.startswith('Home-page:'):
                    url = line.split(':', maxsplit=1)[-1].strip()
                elif line.startswith('License:'):
                    package_license = line.split(':', maxsplit=1)[-1].strip()
                elif line.startswith('License-Expression:'):
                    license_expression = line.split(':', maxsplit=1)[-1].strip()
                elif line.startswith('Version:'):
                    version = line.split(':', maxsplit=1)[-1].strip()
                elif line.startswith('Summary:'):
                    description = line.split(':', maxsplit=1)[-1].strip()

            # store the data for the final package
            if package:
                add_pip_package(package, version, license_expression or package_license,
                                url, description)


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
                        out_file.write(f"Status: {p['status']}")
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
                print(f"Status: {p['status']}")
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
        column_names = ['Name', 'Version', 'License', 'URL', 'Status', 'Type']
        if args.out_path:
            try:
                with open(args.out_path, 'w', encoding='utf-8', newline='') as csvfile:
                    csv_writer = csv.writer(csvfile, quoting=csv.QUOTE_MINIMAL)
                    csv_writer.writerow(column_names)
                    for p in sorted(not_found_packages, key=lambda x: x['package']):
                        csv_writer.writerow([p['package'], p['version'], p['license'],
                                             p['url'], p['status'], p['type']])
            except Exception as e:
                print(f'{e}, exiting.', file=sys.stderr)
                sys.exit(1)
        else:
            csv_writer = csv.writer(sys.stdout, quoting=csv.QUOTE_MINIMAL)
            csv_writer.writerow(column_names)
            for p in sorted(not_found_packages, key=lambda x: x['package']):
                csv_writer.writerow([p['package'], p['version'], p['license'],
                                     p['url'], p['status'], p['type']])
    elif args.out_type == 'oin_csv':
        column_names = ['Number', 'Package Name', 'Nominated By...', 'Nomination type',
                        'Nominator comments', 'Version', 'License', 'Project Download URL',
                        'Project URL', 'Package Version URL', 'Package Version tag',
                        'Description', 'Project', 'OSS Platform', 'TechArea', 'Old name']

        # default values for columns. These will most likely not be used
        number = nominated_by = nomination_comments = project_download_url = ''
        package_version_url = package_version_tag = ''
        project = oss_platform = tech_area = old_name = ''

        if args.out_path:
            try:
                with open(args.out_path, 'w', encoding='utf-8', newline='') as csvfile:
                    csv_writer = csv.writer(csvfile, quoting=csv.QUOTE_MINIMAL)
                    csv_writer.writerow(column_names)
                    for p in sorted(not_found_packages, key=lambda x: x['package']):
                        if p['status'] == 'new':
                            nomination_type = 'NOMINATED'
                        elif p['status'] == 'update':
                            nomination_type = 'UPDATE'
                        csv_writer.writerow([number, p['package'], nominated_by, nomination_type,
                                             nomination_comments, p['version'], p['license'],
                                             project_download_url, p['url'], package_version_url,
                                             package_version_tag, p['description'], project,
                                             oss_platform, tech_area, old_name])
            except Exception as e:
                print(f'{e}, exiting.', file=sys.stderr)
                sys.exit(1)
        else:
            csv_writer = csv.writer(sys.stdout, quoting=csv.QUOTE_MINIMAL)
            csv_writer.writerow(column_names)
            for p in sorted(not_found_packages, key=lambda x: x['package']):
                if p['status'] == 'new':
                    nomination_type = 'NOMINATED'
                elif p['status'] == 'update':
                    nomination_type = 'UPDATE'
                csv_writer.writerow([number, p['package'], nominated_by, nomination_type,
                                     nomination_comments, p['version'], p['license'],
                                     project_download_url, p['url'], package_version_url,
                                     package_version_tag, p['description'], project,
                                     oss_platform, tech_area, old_name])

if __name__ == "__main__":
    main(sys.argv)
