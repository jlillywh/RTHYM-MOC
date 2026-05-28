# Security Policy

## Supported versions

Security fixes are applied to the latest release on the default branch (`main`).
Older tagged releases may receive backports at maintainer discretion.

| Version | Supported |
| ------- | --------- |
| latest on `main` | yes |
| earlier tags | best effort |

Install the current release from [PyPI](https://pypi.org/project/rthym-moc/) or
track `main` for the newest fixes.

## Reporting a vulnerability

If you believe you have found a security issue in **RTHYM-MOC** (the open-source
solver library in this repository), please report it privately rather than
opening a public GitHub issue.

**Preferred:** use [GitHub private vulnerability reporting](https://github.com/jlillywh/RTHYM-MOC/security/advisories/new)
for this repository.

**Alternative:** email **jason@lillywhitewater.com** with the subject
`RTHYM-MOC security`.

Please include:

- a description of the issue and potential impact
- steps to reproduce, or a minimal model/script if applicable
- the version or commit you tested (`pip show rthym-moc` or `git rev-parse HEAD`)
- your contact information for follow-up

## Scope

**In scope**

- this repository (`rthym-moc` Python package and C++ solver core)
- build/release tooling defined here (GitHub Actions, packaging)

**Out of scope**

- the hosted [R-THYM](https://lillywhitewater.com/products/r-thym/) web
  application (report through Lillywhite Water contact channels instead)
- general hydraulic modeling advice or incorrect user input in model files

## Response expectations

Maintainers aim to acknowledge new reports within **7 days** and to provide a
triage update within **30 days**. Complex issues may take longer; we will keep
reporters informed of status when possible.

## Safe harbor

We appreciate responsible disclosure. We will not pursue legal action against
researchers who report issues in good faith and avoid privacy violations, data
destruction, or service disruption when investigating this project.

## Security updates

Confirmed fixes are published through GitHub Security Advisories and included in
subsequent releases. Credit is given to reporters when they wish to be named.
