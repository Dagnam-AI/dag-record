# Security Policy

## Supported Versions

Security fixes are provided for the current public release line.

| Version | Supported |
| --- | --- |
| `0.1.x` | yes |

## Reporting a Vulnerability

Do not open a public GitHub issue for suspected vulnerabilities.

Email security reports to `security@dagnam.ai` with:

- A description of the issue and the affected `dagnam-record` version
- Reproduction steps or proof of concept, if available
- Impact assessment, in particular whether recorded prompts or answers, or anything the recorder
  promises never to store (headers, keys, `extra_*` arguments), could be exposed, written outside
  the trace directory, or sent anywhere
- Any relevant logs or stack traces with secrets removed

We will acknowledge receipt as soon as practical, investigate privately, and
coordinate a fix and disclosure timeline based on severity.

## Secret Handling

Never include real API keys, trace files or customer data in bug reports, tests,
screenshots, logs, or pull requests. A recorded file holds prompts and answers in
clear text (see the README); redact a sample before sharing it.
