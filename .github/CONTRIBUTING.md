# Contributing to HMG-Doc Parser

[한국어](../docs/kor/CONTRIBUTING.md)

We welcome bug reports, documentation, tests, fixes, new nodes, and provider
adapters. The project focuses on Korean business PDFs and Markdown output.
Search existing [issues](https://github.com/hyundaimotorgroup/hmg-doc-parser/issues)
and PRs first. Discuss substantial pipeline or public-contract changes in an issue.
Participation is governed by the [Code of Conduct](CODE_OF_CONDUCT.md).
Report vulnerabilities privately through [SECURITY.md](SECURITY.md).

## Reports and proposals

Use the bug, feature, or question template. Include a reproducible command,
expected/actual behavior, OS/Python versions, YAML profile, provider/model IDs,
and relevant errors. Use synthetic documents or samples you may share. Remove
credentials, private endpoints, personal data, and document-derived content from
configs, screenshots, and logs. Do not attach confidential PDFs or checkpoints.

## Development workflow

1. Fork [hmg-doc-parser](https://github.com/hyundaimotorgroup/hmg-doc-parser) and
   branch from `main`, for example `fix/layout-boxes` or `docs/quickstart`.
2. Follow [installation](../docs/installation.md) and
   [development and validation](../docs/development.md). The parser uses Python
   3.12; Dolphin and Paddle tutorials have separate environments.
3. Keep changes focused and follow surrounding Python style and type annotations.
   Register nodes and schemas as described in
   [adding a node](../docs/development.md#adding-or-changing-a-node).
4. Run relevant checks and add tests for changed contracts or failure behavior
   where appropriate. Offline compiler checks need no provider credentials.
   Live inference may transfer documents and incur charges; use your authorized
   services and documents.
5. Update affected documentation and its Korean counterpart, including DTO,
   configuration, provider, output, and data-handling changes.
6. Submit a PR with the problem, change, related issue, validation results, and
   compatibility impact, using the PR template.

We recommend [Conventional Commits](https://www.conventionalcommits.org/), such
as `fix(layout): preserve reading order`. No repository-wide formatter or linter
command is prescribed. Maintainers review technical quality, security, licensing,
and scope, and may request changes or decline a PR.

## Contributor License Agreement

Contributions are subject to the Hyundai Motor Group CLA. Read:

- [CLA — English](https://github.com/hyundaimotorgroup/.github/blob/main/legal/CLA-ENG.md)
- [CLA — Korean](https://github.com/hyundaimotorgroup/.github/blob/main/legal/CLA-KOR.md)

The CLA describes electronic acceptance through the authenticated GitHub account
used to contribute. Follow the acceptance instructions presented for your PR;
maintainers must verify applicable acceptance before merging. If instructions
are unavailable, contact [opensource@hyundai.com](mailto:opensource@hyundai.com)
for the CLA process. A PR submission alone is not an electronic acceptance record.
This guide does not imply an automated CLA check is installed.

Submit only work you may contribute, including necessary employer authorization.
Disclose third-party materials and their source/licenses, and preserve required
notices. Parser code contributions are distributed under [Apache-2.0](../LICENSE).
Models, datasets, and third-party materials can have separate conditions; see
[third-party notices](../THIRD_PARTY_NOTICES) and
[model/data assets](../docs/model-and-data-assets.md).

## Support

Use [GitHub Issues](https://github.com/hyundaimotorgroup/hmg-doc-parser/issues)
for technical questions and proposals. Private group-service access follows the
[provider guide](../docs/providers.md#group-and-internal-setup). Security reports
use [PSIRT](SECURITY.md); conduct reports use the
[Code of Conduct contact](CODE_OF_CONDUCT.md#enforcement).
