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
from urllib.parse import quote

# RPM header lines look like "Name        : bash". Matching on the
# padded key and colon avoids picking up Description text such as
# "License for binaries is ..." as a field.
RPM_FIELD = re.compile(r'^(Name|Version|Release|License|Source RPM|Vendor|URL|Description)\s*:\s?(.*)$')

# URLs that point at source code (a repository or forge) rather than a
# project website
CODE_HOST = re.compile(r'github\.com/|gitlab\.|codeberg\.org/|bitbucket\.org/|sr\.ht/|pagure\.io/|'
                       r'salsa\.debian\.org/|sourceforge\.net/p(rojects)?/|//git\.|/git/|/cgit/|\.git$', re.I)

# pip "Project-URL" labels that name the source repository
SOURCE_URL_LABEL = re.compile(r'^(source|source code|sources|repository|repo|code|github|gitlab|vcs|git)\b', re.I)

# purl namespaces for RPM vendors. The namespace is the vendor or distribution
# (https://github.com/package-url/purl-spec)
RPM_VENDOR_NAMESPACES = [('almalinux', 'almalinux'), ('fedora', 'fedora'), ('red hat', 'redhat'),
                         ('centos', 'centos'), ('rocky', 'rocky'), ('opensuse', 'opensuse'),
                         ('suse', 'suse'), ('oracle', 'oracle'), ('rpm fusion', 'rpmfusion')]

def normalize_pip_name(name):
    '''Normalize a Python package name as per PEP 503'''
    return re.sub(r'[-_.]+', '-', name).lower()

def rpm_namespace(vendor):
    '''Turn an RPM Vendor (e.g. "Fedora Project") into a purl namespace'''
    vendor = vendor.lower()
    for key, namespace in RPM_VENDOR_NAMESPACES:
        if key in vendor:
            return namespace
    return re.sub(r'[^a-z0-9]+', '-', vendor).strip('-')

def rpm_distro(release):
    '''The distribution from an RPM release dist tag, e.g. "1.el10_1" -> "el10", "2.fc39" -> "fedora-39"'''
    match = re.search(r'\.(el|fc)(\d+)', release)
    if not match:
        return ''
    return f'el{match.group(2)}' if match.group(1) == 'el' else f'fedora-{match.group(2)}'

def make_purl(purl_type, namespace, name, version, qualifiers=None):
    '''Build a package URL (purl) as per https://github.com/package-url/purl-spec'''
    purl = f'pkg:{purl_type}/'
    if namespace:
        purl += f"{quote(namespace, safe='')}/"
    purl += quote(name, safe='')
    if version:
        purl += f"@{quote(version, safe='')}"
    qualifiers = {k: v for k, v in (qualifiers or {}).items() if v}
    if qualifiers:
        purl += '?' + '&'.join(f"{k}={quote(v, safe='')}" for k, v in sorted(qualifiers.items()))
    return purl

def pick_source_url(urls):
    '''Pick the URL most likely to be the source repository from (label, url) pairs'''
    for label, url in urls:
        if url and SOURCE_URL_LABEL.match(label or ''):
            return url
    for _, url in urls:
        if url and CODE_HOST.search(url):
            return url
    return ''

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

    parser.add_argument("--distro", action="store", dest="distro",
                        help="Distribution for package URLs, e.g. debian, ubuntu, almalinux, fedora "
                             "(default: detected from the listing)")

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
        # duplicates and to determine the (source) package name. The "URL"
        # attribute is stored to assist with the comparison.
        rpm_packages_seen = set()

        def add_rpm_package(package, version, release, package_license, url, vendor):
            if not package or package in rpm_packages_seen:
                return
            rpm_packages_seen.add(package)
            if package.lower() in oin_packages:
                return
            namespace = args.distro or rpm_namespace(vendor)
            purl = make_purl('rpm', namespace, package, f'{version}-{release}' if release else version,
                             {'arch': 'src', 'distro': rpm_distro(release)})
            not_found_packages.append({'package': package, 'version': version, 'license': package_license,
                                       'type': 'rpm', 'url': url, 'purl': purl,
                                       'source_url': url if CODE_HOST.search(url) else ''})

        with open(listing, 'r', encoding='utf-8') as rpm_file:
            package = ''
            version = ''
            release = ''
            package_license = ''
            url = ''
            vendor = ''
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
                elif field == 'Vendor':
                    vendor = value
                elif field == 'URL':
                    url = value
                elif field == 'Description':
                    in_description = True
                elif field == 'Name':
                    add_rpm_package(package, version, release, package_license, url, vendor)
                    package = ''
                    version = ''
                    release = ''
                    package_license = ''
                    url = ''
                    vendor = ''
                    in_description = False
            add_rpm_package(package, version, release, package_license, url, vendor)

    elif args.listing_type.lower() == 'deb':
        # walk the Deb listing. Use the "Package" attribute to determine
        # the package name. In case there is a "Source" attribute use that
        # instead, along with the source version it gives in brackets
        # (e.g. "Source: binutils-arm-none-eabi (23)"), which can differ
        # from the binary package's version.
        deb_packages_seen = set()

        def add_deb_package(package, version, url, ubuntu):
            if '(' in package:
                package, source_version = package.split('(', maxsplit=1)
                package = package.strip()
                version = source_version.rstrip(')').strip() or version
            if package in ALIASES:
                package = ALIASES[package]
            if package and package not in deb_packages_seen:
                if package.lower() not in oin_packages:
                    namespace = args.distro or ('ubuntu' if ubuntu else 'debian')
                    purl = make_purl('deb', namespace, package, version, {'arch': 'source'})
                    not_found_packages.append({'package': package, 'version': version, 'license': '',
                                               'type': 'deb', 'url': url, 'purl': purl,
                                               'source_url': url if CODE_HOST.search(url) else ''})
                deb_packages_seen.add(package)

        with open(listing, 'r', encoding='utf-8') as deb_file:
            package = ''
            version = ''
            url = ''
            # Ubuntu keeps the Debian maintainer as "Original-Maintainer"
            # on the packages it modifies
            ubuntu = False
            for line in deb_file:
                if line.startswith('Package:'):
                    add_deb_package(package, version, url, ubuntu)

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
                elif line.startswith('Original-Maintainer:'):
                    ubuntu = True
            add_deb_package(package, version, url, ubuntu)
    elif args.listing_type.lower() == 'pip':
        # walk the pip listing. "pip show -v" also lists the "Project-URLs",
        # which usually include the source repository.
        pip_packages_seen = set()

        def add_pip_package(package, version, package_license, url, project_urls):
            name = normalize_pip_name(package)
            if not package or name in pip_packages_seen:
                return
            pip_packages_seen.add(name)
            # try 'python-{package}' as well
            if name not in oin_pip_packages and f'python-{name}' not in oin_pip_packages:
                if not url:
                    url = next((u for label, u in project_urls if re.match(r'home', label, re.I)), '')
                purl = make_purl('pypi', '', name, version)
                not_found_packages.append({'package': package, 'version': version, 'license': package_license,
                                           'type': 'pip', 'url': url, 'purl': purl,
                                           'source_url': pick_source_url(project_urls + [('', url)])})

        with open(listing, 'r', encoding='utf-8') as pip_file:
            package = ''
            version = ''
            package_license = ''
            url = ''
            project_urls = []
            in_project_urls = False
            for line in pip_file:
                if in_project_urls and line.startswith(' '):
                    # indented "label, url" lines under "Project-URLs:"
                    label, _, project_url = line.strip().partition(', ')
                    project_urls.append((label, project_url.strip()))
                    continue
                in_project_urls = False
                if line.startswith('Name:'):
                    add_pip_package(package, version, package_license, url, project_urls)

                    # parse the package name, reset everything
                    package = line.split(':', maxsplit=1)[-1].strip()
                    version = ''
                    package_license = ''
                    url = ''
                    project_urls = []
                elif line.startswith('Home-page:'):
                    url = line.split(':', maxsplit=1)[-1].strip()
                elif line.startswith('License-Expression:'):
                    # an SPDX expression is preferred over the free text License field
                    package_license = line.split(':', maxsplit=1)[-1].strip()
                elif line.startswith('License:') and not package_license:
                    package_license = line.split(':', maxsplit=1)[-1].strip()
                elif line.startswith('Version:'):
                    version = line.split(':', maxsplit=1)[-1].strip()
                elif line.startswith('Project-URLs:'):
                    in_project_urls = True
            add_pip_package(package, version, package_license, url, project_urls)

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
                        out_file.write(f"Source URL: {p['source_url']}")
                        out_file.write('\n')
                        out_file.write(f"Purl: {p['purl']}")
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
                print(f"Source URL: {p['source_url']}")
                print(f"Purl: {p['purl']}")
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
                    csv_writer.writerow(['Name', 'Version', 'License', 'URL', 'Type', 'Source URL', 'Purl'])
                    for p in sorted(not_found_packages, key=lambda x: x['package']):
                        csv_writer.writerow([p['package'], p['version'], p['license'],
                                             p['url'], p['type'], p['source_url'], p['purl']])
            except Exception as e:
                print(f'{e}, exiting.', file=sys.stderr)
                sys.exit(1)
        else:
            csv_writer = csv.writer(sys.stdout, quoting=csv.QUOTE_MINIMAL)
            csv_writer.writerow(['Name', 'Version', 'License', 'URL', 'Type', 'Source URL', 'Purl'])
            for p in sorted(not_found_packages, key=lambda x: x['package']):
                csv_writer.writerow([p['package'], p['version'], p['license'],
                                     p['url'], p['type'], p['source_url'], p['purl']])

if __name__ == "__main__":
    main(sys.argv)
