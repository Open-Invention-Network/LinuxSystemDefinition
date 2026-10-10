# A Tool to Check OIN Linux System Definition Table 13 Coverage in RPM/DEB/PIP Package Managers

This tool compares the output of various package managers (RPM, DEB, PIP) with OIN Linux System Definition (LSD) Table 13 and provides output on which packages are not covered by the LSD Table 13.

The purpose of this script is to help companies quickly and easily compile a list of packages they use which are not covered under the LSD, and to then submit these packages to the OIN team for potential inclusion. This will increase the amount of patent non-aggression coverage in the OIN community over time.

It has been kept as simple as possible regarding dependencies so it can run on a wide range of systems. It does not have to run on the same machine as the package managers, so it can be used for testing various systems from one workstation.

## Getting the latest Linux System definition

The CSV files referenced below (e.g. `table-13_2026-02-25.csv`) are examples for local testing only. The current, authoritative Linux System definition should always be downloaded from [the export tool](https://definition.openinventionnetwork.com/export/):

```
TABLE=$(curl -sf https://definition.openinventionnetwork.com/api/tables/recent \
  | jq -r '.recent_table.file_name | sub("\\.json$"; "")')

curl -sf -o "${TABLE}_$(date +%F).csv" "https://definition.openinventionnetwork.com/api/export/csv?table=${TABLE}&fields=name,package_version,description,download_url,version_url,project_url,purl"
```

See [`test/README.md`](test/README.md) for further details.

## RPM

First run `rpm -qia` on the target system and redirect the output to a file, for example:

```
$ rpm -qia > /tmp/rpm
```

Then copy the file to the system running the script and run:

```
$ python package_nominations.py -l /tmp/rpm -c table-13_2026-02-25.csv -t rpm
```

It might be needed to adapt paths to point to the right locations.

To print to a file add the `-o` parameter, for example:

```
$ python package_nominations.py -l /tmp/rpm -c table-13_2026-02-25.csv -t rpm -o /tmp/tool_output.txt
```

By default the program will output in text format, but JSON and CSV are also supported, both as file output, as well as printed on the terminal:

```
$ python package_nominations.py -l /tmp/rpm -c table-13_2026-02-25.csv -t rpm -o /tmp/tool_output.json --output-type=json
$ python package_nominations.py -l /tmp/rpm -c table-13_2026-02-25.csv -t rpm -o /tmp/tool_output.csv --output-type=csv
```

## DEB

```
$ apt list --installed  | cut -f 1 -d / | xargs -I% apt show % > /tmp/deb

$ python package_nominations.py -l /tmp/deb -c table-13_2026-02-25.csv -t deb
```

## Python pip

```
$ pip list | tail -n +3 | cut -f 1 -d " " | xargs -I% pip show -v % > /tmp/pip

$ python package_nominations.py -l /tmp/pip -c table-13_2026-02-25.csv -t pip
```

## Output

The tool works on **source** packages: the source RPM for RPM listings, the
`Source` package (and its version) for DEB listings, and the project for pip.
For each package not found in the Linux System definition it reports:

- Name, Version and License
- URL: the project homepage recorded by the package
- Source URL: the source repository, when the package records one. For pip,
  `pip show -v` lists the `Project-URLs`, which usually include it; without
  `-v` only the homepage is available.
- Purl: a [package URL](https://github.com/package-url/purl-spec) identifying
  the source package, e.g. `pkg:rpm/almalinux/crypto-policies@20260216-1.el10?arch=src&distro=el10`,
  `pkg:deb/debian/avrdude@7.1%2Bdfsg-3?arch=source` or `pkg:pypi/asyncpg@0.32.0`.
  The purl lets the nomination tools look the package up in other sources,
  such as Repology.

The purl's distribution is taken from the listing (the RPM `Vendor`, or Ubuntu
for DEB listings with `Original-Maintainer` fields, otherwise Debian). Use
`--distro` to set it, e.g. `--distro mint`.

## Running the tests

The tests only use the Python standard library:

```
$ python -m unittest discover -s test
```

## Shortcomings

Some packages may have been renamed (for example: `pcre2`) so those are "false positives". This is not a concern, and you can just submit the output of this tool with such packages included. The OIN team will filter the output for you. 
