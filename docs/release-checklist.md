# Release checklist

[한국어](kor/release-checklist.md)

Use this checklist for a specific release candidate. Record the commit, version,
reviewer, date, command/environment, result, and evidence location for each check.
A written policy or a previous development run does not complete a release check.
Unchecked items below are release work, not missing user documentation.

## Rights and assets

- [ ] Confirm Apache-2.0, the copyright holder/year, and the scope of the parser
  license for this release.
- [ ] Include the reviewed [LICENSE](../LICENSE) and
  [THIRD_PARTY_NOTICES](../THIRD_PARTY_NOTICES) in the published source, preserving
  the supplied license texts, dependency names/versions, sources, and copyrights.
- [ ] Include the router checkpoint Apache-2.0 LICENSE and NOTICE in any weights
  distribution and preserve the declared copyright attribution.
- [ ] Review every bundled checkpoint, PDF, image, ground-truth file, and pickle
  in [the asset register](assets/manifest.json); record source, owner, license,
  redistribution permission, version, and SHA-256, or exclude it from the release.
- [ ] Preserve required third-party licenses/notices. Inspect the actual parser,
  Dolphin, and Paddle distributions, including PDFium dependency notices.
- [ ] Check model use/distribution conditions. PP-DocLayoutV3 is the commercial
  recommendation; Dolphin v2 requires compliance with its research license or
  evidence of a separate commercial license. Verify any advertised adapter.

## Security and dependencies

- [ ] Scan candidate files and Git history for credentials, private addresses,
  confidential content, and unintended artifacts. A `.gitignore` is not evidence
  that tracked files or history are clean.
- [ ] Scan direct/transitive dependencies in all three environments, review
  findings and prerelease pins, record versions, and run `python -m pip check`.
- [ ] Run relevant input-limit tests and verify loopback entrypoints, request
  limits, safe YAML handling, and sanitized examples.
- [ ] Confirm secret-scan operation and required repository checks on the target
  repository; local workflow configuration alone does not prove a successful run.

## Candidate installation and configuration

- [ ] Install from a fresh clone of the candidate, using documented OS/Python
  environments; record commands and resolved dependencies.
- [ ] Check CLI help, the offline compiler example, all selected YAML profiles,
  environment references, DTO connections, and output nodes.
- [ ] Include any documented test files, helper modules, tutorials, and static UI
  assets in the candidate. Do not advertise tests absent from the distribution.
- [ ] Replace private fixture defaults in release examples with a redistributable
  sample or a clear user-supplied input path; confirm all example paths exist.

## Runtime validation

- [ ] With approved data and provider access, run the local quickstart and inspect
  final Markdown, `[Error]` markers, tables, images, and retained artifacts.
- [ ] Verify selected router weights and each advertised router/provider profile.
  Record hashes, model versions, resource needs, and inference results.
- [ ] Test vLLM/Triton inference contracts and managed/group-service full runs
  before describing those combinations as validated.
- [ ] Record a regression baseline for the same graph/input identities; use a
  separate output root for each profile and retain comparison results.
- [ ] If Langfuse delivery is advertised, verify authorized real delivery.
- [ ] If Confluence behavior is advertised, distinguish loader/compiler, create,
  update, attachment replacement, and full CLI checks; use a permitted test space.

- [ ] Run the Global Context skip regression for the candidate. Check zero L1
  renders/requests, L2/missing-level calls, content/errors/cancellation and editor
  round trips. Record `skip_levels` in live quality/cost comparisons; historical
  benchmarks do not establish the new policy's quality or savings amount.

## Documentation and publication

- [ ] Check English/Korean documentation, relative links, examples, policies,
  model conditions, and third-party notices; remove drafting placeholders.
- [ ] Check evaluation dataset publication rights and README scores against the
  selected evaluation evidence. Record judge/model/configuration versions.
- [ ] Inspect public examples and benchmark artifacts for source content,
  personal data, and provider details.
- [ ] Confirm the organization CLA acceptance/verification process for PRs,
  published PSIRT/conduct contacts, and project support routes.
- [ ] Assign the release version/date, update `[Unreleased]`, and prepare tag and
  release notes with source/asset checksums and known validation limits.
- [ ] Confirm final publication review and approval under the Advanced IP team's
  guidance and publish only the selected
  candidate; replace any prerelease announcement with current release information.
