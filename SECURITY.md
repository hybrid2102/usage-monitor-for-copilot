# Security policy

## Supported versions

Security fixes are applied to the latest published version.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting for this repository. Do not open a public issue containing credentials, tokens, private account data, or an exploit that has not yet been fixed.

Include the affected version, operating system, reproduction steps, and expected impact. You should receive an initial response within seven days.

## Authentication boundary

Usage Monitor for Copilot delegates authentication to the installed Copilot CLI through `copilot --server`. A report that shows the monitor reading or persisting Copilot credentials, or that shows the `copilot --server` subprocess accepting a connection without the monitor's own per-run connection token, is considered security-sensitive.
