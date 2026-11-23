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
           'pcre2': 'pcre',
           'python3.12': 'python',
           'requests': 'python-requests',
          }

TOOL_VERSION='2.3.0'

def compare_versions(version_1, version_2):
    '''Compare versions in a slightly more intelligent way than
       just a string comparison. This requires that the versions
       actually can be compared. If this is not the case, then
       this method will fall back to just a string comparison.
       Returns if version_1 is smaller than version_2.'''

    if version_1 == version_2:
        return False

    # First try to see the string can be split in individual
    # components and if there are known "dividers" (such as '.')
    if '.' in version_1 and '.' in version_2:
        version_1_splits = version_1.split('.')
        version_2_splits = version_2.split('.')
        if len(version_1_splits) != len(version_2_splits):
            # versions cannot be compared as the
            # versions are formatted differently
            return version_1 < version_2
        for v1, v2 in zip(version_1_splits, version_2_splits):
            try:
                v1_cast = int(v1)
                v2_cast = int(v2)
            except:
                v1_cast = v1
                v2_cast = v2
            if v1_cast < v2_cast:
                return True
    else:
        try:
            v1_cast = int(version_1)
            v2_cast = int(version_2)
        except:
            v1_cast = version_1
            v2_cast = version_2
        if v1_cast < v2_cast:
            return True

    return False

def main(argv):
    parser = argparse.ArgumentParser()

    # the following options are provided on the commandline
    parser.add_argument("-l", "--listing", action="store", dest="listing",
                        help="package manager listing file or directory with files",
                        metavar="PATH")

    parser.add_argument("-c", "--csv", action="store", dest="table_csv",
                        help="OIN Linux System Definition table in CSV",
                        metavar="CSV")

    parser.add_argument("--new-versions", action="store_true", dest="new_versions",
                        help="Report packages with newer versions")

    parser.add_argument("-o", "--out", action="store", dest="out_path",
                        help="Output file (or stdout)")

    parser.add_argument("--output-type", action="store", dest="out_type",
                        help="Output type (TXT, JSON, CSV, OIN_CSV), case insensitive, default: TXT")

    parser.add_argument("--summary", action="store_true", dest="summary",
                        help="Create a summary (only use with --out)")

    parser.add_argument("--force", action="store_true", dest="force",
                        help="Overwrite output file")

    parser.add_argument("--covered", action="store_true", dest="covered",
                        help="Count covered packages")

    args = parser.parse_args()

    if not args.listing:
        parser.error("File listing or directory missing")

    if not args.table_csv:
        parser.error("Linux System Definition CSV missing")

    if not args.out_type:
        args.out_type = 'txt'
    args.out_type = args.out_type.lower()

    if args.out_type not in ['txt', 'json', 'csv', 'oin_csv']:
        parser.error("Unsupported output type")

    if args.out_path:
        out = pathlib.Path(args.out_path)
        if out.exists() and not args.force:
            parser.error(f"Path '{out}' already exists")

    if args.summary and not args.out_path:
        parser.error("--summary can only be used together with --out")

    package_files = []

    # checks for the listing file or directory
    listing = pathlib.Path(args.listing)
    if not listing.exists():
        print(f"Path '{listing}' does not exist", file=sys.stderr)
        sys.exit(1)
    if not (listing.is_file() or listing.is_dir()):
        print(f"Path '{listing}' is not a file or directory", file=sys.stderr)
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
        csv_reader = csv.reader(csv_file)
        is_first = True
        for line in csv_reader:
            if is_first:
                is_first = False
                continue
            package_version, description, download_url, version_url, name, project_url, purl = line
            oin_packages[name.lower()] = {'version': package_version, 'dl_url': download_url,
                                          'version_url': version_url, 'project_url': project_url,
                                          'package_url': purl, 'description': description,
                                          'name': name}

    # check the
    if listing.is_file():
        package_files.append(listing)
    else:
        for top, _, l, in listing.walk():
            for ll in l:
                if top / ll != table_csv:
                    package_files.append(top / ll)

    not_found_packages = []
    covered_packages = []

    # first try to determine the format. It is assumed that the entire
    # file with package manager information is coming from a single package
    # manager (i.e. output of different package managers has not been mixed).
    for package_listing in package_files:
        listing_type = ''
        with open(package_listing, 'r', encoding='utf-8') as package_manager_file:
            try:
                for line in package_manager_file:
                    if '"DEPENDENCIES WITH LICENSES"' in line:
                        listing_type = 'buildroot'
                        break
                    if '"installed-size":' in line:
                        listing_type = 'alpine'
                        break
                    if ':' in line:
                        key = line.split(':', maxsplit=1)[0].strip()
                        if key in ['APT-Sources', 'APT-Manual-Installed']:
                            listing_type = 'deb'
                            break
                        if key in ['Source RPM']:
                            listing_type = 'rpm'
                            break
                        if key in ['Author-email', 'Home-page']:
                            listing_type = 'pip'
                            break
            except UnicodeDecodeError:
                print(f"{package_listing} could not be read (binary file?)",
                      file=sys.stderr)
                continue

        if not listing_type:
            print(f"Package manager type for {package_listing} could not be determined",
                  file=sys.stderr)
            continue

        if listing_type == 'rpm':
            # walk the RPM listing. Use the "Source RPM" attribute to filter
            # duplicates and to determine the package name. The "URL" attribute
            # is stored to assist with the comparison.
            rpm_packages_seen = set()

            with open(package_listing, 'r', encoding='utf-8') as rpm_file:
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
                                    if not compare_versions(oin_packages[package.lower()]['version'], version):
                                        covered_packages.append(oin_packages[package.lower()])
                                    elif args.new_versions:
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
                        if not compare_versions(oin_packages[package.lower()]['version'], version):
                            covered_packages.append(oin_packages[package.lower()])
                        elif args.new_versions:
                            description = oin_packages[package.lower()]['description']
                            not_found_packages.append({'package': package, 'version': version,
                                                       'license': package_license, 'type': package_type,
                                                       'url': url, 'description': description,
                                                       'status': 'update'})

        elif listing_type == 'deb':
            # walk the Deb listing. Use the "Package" attribute to determine
            # the package name. In case there is a "Source" attribute use that
            # instead.
            deb_packages_seen = set()

            with open(package_listing, 'r', encoding='utf-8') as deb_file:
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
                                    if not compare_versions(oin_packages[package.lower()]['version'], deb_version):
                                        covered_packages.append(oin_packages[package.lower()])
                                    elif args.new_versions:
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

                # store the data for the final package
                if package and package not in deb_packages_seen:
                    if package.lower() not in oin_packages:
                        not_found_packages.append({'package': package, 'version': version,
                                                   'license': package_license, 'type': package_type,
                                                   'url': url, 'description': description,
                                                   'status': 'new'})
                    else:
                        if not compare_versions(oin_packages[package.lower()]['version'], deb_version):
                            covered_packages.append(oin_packages[package.lower()])
                        elif args.new_versions:
                            description = oin_packages[package.lower()]['description']
                            not_found_packages.append({'package': package, 'version': version,
                                                       'license': package_license, 'type': package_type,
                                                       'url': url, 'description': description,
                                                       'status': 'update'})

        elif listing_type == 'pip':
            with open(package_listing, 'r', encoding='utf-8') as pip_file:
                package = ''
                version = ''
                package_license = ''
                url = ''
                description = ''
                package_type = 'pip'
                for line in pip_file:
                    if line.startswith('Name:'):
                        if package:
                            process = False
                            status = None
                            package_name = package.lower()
                            if package.lower() not in oin_packages:
                                # try 'python-{package}' as well
                                p_name = f'python-{package.lower()}'
                                if p_name not in oin_packages:
                                    process = True
                                    status = 'new'
                                else:
                                    if not compare_versions(oin_packages[p_name]['version'], version):
                                        covered_packages.append(oin_packages[p_name])
                                    elif args.new_versions:
                                        description = oin_packages[p_name]['description']
                                        package_name = p_name
                                        process = True
                                        status = 'update'
                            else:
                                if not compare_versions(oin_packages[package_name]['version'], version):
                                    covered_packages.append(oin_packages[package_name])
                                elif args.new_versions:
                                    description = oin_packages[package_name]['description']
                                    process = True
                                    status = 'update'
                            if process:
                                not_found_packages.append({'package': package_name, 'version': version,
                                                           'license': package_license, 'type': package_type,
                                                           'url': url, 'description': description,
                                                           'status': status})

                        # parse the package name, reset everything
                        package = line.split(':', maxsplit=1)[-1].strip()
                        version = ''
                        package_license = ''
                        description = ''
                        url = ''
                    elif line.startswith('Home-page:'):
                        url = line.split(':', maxsplit=1)[-1].strip()
                    elif line.startswith('License:'):
                        package_license = line.split(':', maxsplit=1)[-1].strip()
                    elif line.startswith('Version:'):
                        version = line.split(':', maxsplit=1)[-1].strip()
                    elif line.startswith('Summary:'):
                        description = line.split(':', maxsplit=1)[-1].strip()

                # store the data for the final package
                if package:
                    process = False
                    status = None
                    package_name = package.lower()
                    if package.lower() not in oin_packages:
                        p_name = f'python-{package.lower()}'
                        if p_name not in oin_packages:
                            process = True
                            status = 'new'
                        else:
                            if not compare_versions(oin_packages[p_name]['version'], version):
                                covered_packages.append(oin_packages[p_name])
                            elif args.new_versions:
                                description = oin_packages[p_name]['description']
                                package_name = p_name
                                process = True
                                status = 'update'
                    else:
                        if not compare_versions(oin_packages[package_name]['version'], version):
                            covered_packages.append(oin_packages[package_name])
                        elif args.new_versions:
                            description = oin_packages[package_name]['description']
                            process = True
                            status = 'update'
                    if process:
                        not_found_packages.append({'package': package_name, 'version': version,
                                                   'license': package_license, 'type': package_type,
                                                   'url': url, 'description': description,
                                                   'status': status})

        elif listing_type == 'buildroot':
            package_type = 'buildroot'
            with open(package_listing, encoding='utf-8') as csv_file:
                csv_reader = csv.reader(csv_file)
                is_first = True
                for line in csv_reader:
                    if is_first:
                        is_first = False
                        continue
                    package, version, package_license, license_files, source_archive, source_site, dependencies = line
                    package = ALIASES.get(package, package)
                    if package.lower() not in oin_packages:
                        not_found_packages.append({'package': package, 'version': version,
                                                   'license': package_license, 'type': package_type,
                                                   'url': source_site, 'description': '',
                                                   'status': 'new'})
                    else:
                        if not compare_versions(oin_packages[package.lower()]['version'], version):
                            covered_packages.append(oin_packages[package.lower()])
                        elif args.new_versions:
                            description = oin_packages[package.lower()]['description']
                            not_found_packages.append({'package': package, 'version': version,
                                                       'license': package_license, 'type': package_type,
                                                       'url': source_site, 'description': description,
                                                       'status': 'update'})

        elif listing_type == 'alpine':
            package_type = 'alpine'
            with open(package_listing, encoding='utf-8') as package_file:
                alpine_packages = json.load(package_file)
                for alpine_package in alpine_packages:
                    package = ALIASES.get(alpine_package['name'], alpine_package['name'])
                    version = alpine_package['version'].rsplit('-', maxsplit=1)[0]
                    if package.lower() not in oin_packages:
                        not_found_packages.append({'package': package, 'version': version,
                                                   'license': '', 'type': package_type,
                                                   'url': alpine_package['url'],
                                                   'description': alpine_package['description'],
                                                   'status': 'new'})
                    else:
                        if not compare_versions(oin_packages[package.lower()]['version'], version):
                            covered_packages.append(oin_packages[package.lower()])
                        elif args.new_versions:
                            description = oin_packages[package.lower()]['description']
                            not_found_packages.append({'package': package, 'version': version,
                                                       'license': '', 'type': package_type,
                                                       'url': alpine_package['url'],
                                                       'description': description,
                                                       'status': 'update'})

    # deduplicate not_found_packages
    seen = set()
    new_not_found_packages = []
    for p in not_found_packages:
        if (p['package'], p['version']) in seen:
            continue
        seen.add((p['package'], p['version']))
        p['tool'] = f'package-nominations.py-{TOOL_VERSION}'
        new_not_found_packages.append(p)

    not_found_packages = new_not_found_packages

    # deduplicate covered_packages
    seen = set()
    new_covered_packages = []
    for p in covered_packages:
        if (p['name'], p['version']) in seen:
            continue
        seen.add((p['name'], p['version']))
        new_covered_packages.append(p)

    covered_packages = new_covered_packages

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
                        out_file.write(f"Tool: {p['tool']}")
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
                print(f"Tool: {p['tool']}")
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
        column_names = ['Name', 'Version', 'License', 'URL', 'Status', 'Type', 'OIN_id']
        if args.out_path:
            try:
                with open(args.out_path, 'w', encoding='utf-8', newline='') as csvfile:
                    csv_writer = csv.writer(csvfile, quoting=csv.QUOTE_MINIMAL)
                    csv_writer.writerow(column_names)
                    for p in sorted(not_found_packages, key=lambda x: x['package']):
                        csv_writer.writerow([p['package'], p['version'], p['license'],
                                             p['url'], p['status'], p['type'], p['tool']])
            except Exception as e:
                print(f'{e}, exiting.', file=sys.stderr)
                sys.exit(1)
        else:
            csv_writer = csv.writer(sys.stdout, quoting=csv.QUOTE_MINIMAL)
            csv_writer.writerow(column_names)
            for p in sorted(not_found_packages, key=lambda x: x['package']):
                csv_writer.writerow([p['package'], p['version'], p['license'],
                                     p['url'], p['status'], p['type'], p['tool']])
    elif args.out_type == 'oin_csv':
        column_names = ['Number', 'Package Name', 'Nominated By...', 'Nomination type',
                        'Nominator comments', 'Version', 'License', 'Project Download URL',
                        'Project URL', 'Package Version URL', 'Package Version tag',
                        'Description', 'Project', 'OSS Platform', 'TechArea', 'Old name',
                        'Source']

        # default values for columns. These will most likely not be used
        number = nominated_by = nomination_comments = project_download_url = ''
        package_version_url = package_version_tag = ''
        project = oss_platform = tech_area = old_name = ''
        source = f'package_nominations.py-{TOOL_VERSION}'

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
                                             oss_platform, tech_area, old_name, source])
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
                                     oss_platform, tech_area, old_name, source])

    if args.summary:
        new_packages = 0
        updates = 0
        for p in not_found_packages:
            if p['status'] == 'new':
                new_packages += 1
            if p['status'] == 'update':
                updates += 1
        print('SUMMARY\n')
        print(f'New packages: {new_packages}')
        print(f'Updated packages: {updates}')
        print(f'New and updated packages: {new_packages + updates}')
        if args.covered:
            print(f'Covered packages: {len(covered_packages)}')
    else:
        if args.covered:
            for p in sorted(covered_packages, key=lambda x: x['name']):
                print(f'Covered: {p["name"]} {p["version"]}')



if __name__ == "__main__":
    main(sys.argv)
