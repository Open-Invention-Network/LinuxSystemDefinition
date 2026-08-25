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

## DEB

```
$ apt list --installed  | cut -f 1 -d / | xargs -I% apt show % > /tmp/deb

$ python package_nominations.py -l /tmp/deb -c table-13_2026-02-25.csv -t deb
```

## Python pip

```
$ pip list | tail -n +3 | cut -f 1 -d " " | xargs -I% pip show % > /tmp/pip

$ python package_nominations.py -l /tmp/pip -c table-13_2026-02-25.csv -t pip
```

## Shortcomings

Some packages may have been renamed (for example: `pcre2`) so those are "false positives". This is not a concern, and you can just submit the output of this tool with such packages included. The OIN team will filter the output for you. 

