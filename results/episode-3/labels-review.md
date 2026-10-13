# Episode 3 answer labels: review

Each of Alpha's answers from the first golden run, with its draft label. Confirm or overrule each one in `labels.csv` (column `label`, and `stale_as_current`), then change `labelled_by` to your name.

Labels: correct · partly · wrong · abstained wrongly · declined in own words · answered beside the point · accepted false premise.

Worth a second look first: G-008, G-009, G-013, G-015, G-018, G-024, G-044 (marked ⚑).

## G-001 · single-fact · **correct**

**Q:** How does the run budget estimate how many tokens a run has spent, given that the AI provider doesn't report usage?

**Reference:** It estimates from output length: estimateTokens(text) = ceil(len/4) over the response text; exact usage is deferred and the estimate is an accepted risk.

**Alpha:** The run budget estimates token usage by dividing the text length by four and rounding up, as the AI provider does not report actual usage. When estimated spend reaches 80%, the Decider's effort degrades, indicating the run is nearing its token limit.

**Retrieval:** hit at rank 1

**Why this label:** ceil(len/4) because the provider reports no usage; matches the reference.

## G-002 · single-fact · **correct**

**Q:** How does spectastic add trailers to its automatic commits: does it assemble the commit-message footer itself?

**Reference:** No. run.commit appends one git commit --trailer flag per trailer entry, so git owns RFC-correctness and dedup; this needs git >= 2.32, with interpret-trailers as the fallback.

**Alpha:** Spectastic uses one --trailer "k: v" per line to generate a correct footer. The commit-message footer is appended via one --trailer flag per entry, without manual assembly.

**Retrieval:** miss: right file, other chunks

**Why this label:** One --trailer flag per entry, no hand-built footer. Answered from design chunk 3, a strict retrieval miss.

## G-003 · single-fact · **abstained wrongly**

**Q:** What made the lines of a wrapped heading overlap when the heading contained inline code?

**Reference:** The h1 line-height of 1.05 was too tight, and inline code's padding, border and 0.9em size made a ~73px box inside a 57px line box; the fix raised h1 line-height to 1.14 and flattened code inside headings.

**Alpha:** Not in the archive.

**Retrieval:** hit at rank 2

**Why this label:** The right chunk was retrieved at rank 2, but both of Beta's claims paraphrased and were dropped, so Alpha got no quotations.

## G-004 · single-fact · **wrong**

**Q:** In the VS Code extension's canvas, why was the hover card cut off for nodes near the edge of the panel?

**Reference:** The card was appended inside the canvas surface, which the scroll container clips with overflow:auto. The fix renders it on document.body with position:fixed, viewport clamping and flip-above.

**Alpha:** The hover card was cut off for nodes near the edge of the panel because the compact card was rendered with position: fixed, which can cause it to be clipped by the scroll container.

**Retrieval:** hit at rank 2

**Why this label:** Right chunk at rank 2, but cause and fix are inverted: position:fixed was the fix, not the cause.

## G-005 · single-fact · **wrong**

**Q:** Does init --tools wire spectastic enforce into the pre-commit hook it installs?

**Reference:** Not automatically. That integration was deferred because 031's hook uses exec, so you wire it manually (spectastic enforce || exit 1), and FR-005 is only partially met.

**Alpha:** spectastic init --tools installs a git pre-commit gate that rejects a commit when spectastic validate finds an error. spectastic init --tools also installs the Claude Code command adapters.

**Retrieval:** miss: another spec

**Why this label:** Describes the validate gate the hook installs; never says enforce is not wired in.

## G-006 · single-fact · **correct**

**Q:** Why did the npm publish of v0.1.0-pre.28 fail?

**Reference:** It was a credential failure, not a code one: the npm step returned 404 Not Found on the PUT for @spectastic/render, which points to NPM_TOKEN expiring, rotating or losing scope. The fix moved publishing to OIDC trusted publishing.

**Alpha:** The v0.1.0-pre.28 publish failed with a 404 Not Found error, indicating a credential failure at the npm step. The timing of the failure suggests the NPM_TOKEN may have expired, rotated, or lost scope. npm is phasing out 2FA-bypass tokens for direct publishing, which may have impacted the token’s validity.

**Retrieval:** hit at rank 1

**Why this label:** 404 on the npm PUT, a credential failure, token expired or rotated.

## G-007 · single-fact · **abstained wrongly**

**Q:** Does the published web address for spectastic's config JSON schema actually resolve yet?

**Reference:** No. Fetching it at the pinned version returns 404 because the currently published version predates the schema file, so the check is to be repeated at the next release.

**Alpha:** Not in the archive.

**Retrieval:** miss: right file, other chunks

**Why this label:** 087 tasks.html chunk 2 was retrieved; Beta's only claim paraphrased and was dropped.

## G-008 · single-fact · **partly** ⚑

**Q:** When the kernel was extracted, what benchmark baseline was full-project validation expected to stay within 20% of?

**Reference:** The validate-full-project p50 should stay within ±20% of 175 ms on an M1 dev machine and 295 ms on ubuntu-latest CI.

**Alpha:** The full-project validation was expected to stay within 20% of a 175 ms baseline.

**Retrieval:** miss: right file, other chunks

**Why this label:** Gives the 175 ms M1 baseline; misses the 295 ms CI figure.

## G-009 · single-fact · **partly** ⚑

**Q:** In the change-risk verification run, what result did a diff with a staged binary plus a CI workflow edit produce?

**Reference:** Two findings, a 55/100 amber score and the disclaimer, with exit code 0.

**Alpha:** A diff with a staged binary plus a CI workflow edit produced two findings, a score, a band, and the 'surfaces risk, not detection' disclaimer.

**Retrieval:** hit at rank 1

**Why this label:** Two findings and the disclaimer; misses the 55/100 amber score and exit code 0. Quoted tasks.html, not the verify run.

## G-010 · single-fact · **wrong**

**Q:** Why does triage fan-out use a hand-rolled concurrency pool instead of the p-map library?

**Reference:** p-map is only a dev/CI transitive dependency, and promoting it would add a real runtime dependency to the published package. The owner kept @spectastic/core dependency-minimal, so a ~30-line mapPool copies p-map's input-order and concurrency-cap semantics.

**Alpha:** The serial list loop is the bottleneck to replace packages/core/src/commands/triage.ts:67 verified for (const item of items) { await characterise(…) } — one blocking call per item. The hedge gate is inline mid-loop — must move to a post-pass triage.ts:100-103, 117-159 verified escalateLayer calls ai.ask inside characterise; can't interleave under concurrency (FR-005). IDs are assigned interleaved in loop order — must become one post-pass triage.

**Retrieval:** miss: right file, other chunks

**Why this label:** Talks about the serial loop bottleneck; never says why p-map was not used.

## G-011 · paraphrase · **correct**

**Q:** Why does a design page bake in a duplicate of the API definition's text instead of pulling that file in live while someone is viewing it?

**Reference:** The artifact's Content-Security-Policy (default-src 'none', no connect-src) blocks a runtime fetch, and an iframe would be flagged by the no-executable-content rule, so the contract text is copied in at generate time and drift is guarded separately.

**Alpha:** The design page bakes in a duplicate of the API definition's text because the materialiser reads the file, escapes it, and emits it as part of the declaration. This approach was chosen to avoid runtime fetches, which are blocked by the default-src policy and the no-executable-content rule. The outbound pipeline ensures that the content is fully processed and written to a dated path before the browser opens the file, making byte-identity a property of the code.

**Retrieval:** miss: right file, other chunks

**Why this label:** CSP default-src blocks a runtime fetch and the no-executable-content rule rules out the alternative. Strict retrieval miss.

## G-012 · paraphrase · **wrong**

**Q:** If someone tweaks a file that came in from a design tool and later brings in a fresh version from that tool, are their tweaks kept?

**Reference:** Yes, manual changes survive a re-import, except on fields whose source of truth is the export; those fields are re-derived on every import.

**Alpha:** An installed adapter must be structurally impossible to drift from its source. The installed hook is intended to be portable across macOS and Linux shells.

**Retrieval:** miss: right file, other chunks

**Why this label:** Answers about installed adapters drifting, from 031; nothing about re-imports.

## G-013 · paraphrase · **partly** ⚑

**Q:** How does the prose theme make sure its fade-in-on-scroll effect can never leave text invisible if the page's code fails to load or errors out?

**Reference:** The stylesheet never hides anything. The script marks the document as reveal-capable when it runs, and only then does the hidden state exist, so a failure degrades to plain visible content.

**Alpha:** The prose theme ensures fully readable artifacts even with JavaScript disabled, preventing text from being invisible due to code failures. The reveal mechanism is designed as a progressive enhancement, requiring no markup changes and ensuring blocks are revealed exactly once, regardless of script errors.

**Retrieval:** miss: right file, other chunks

**Why this label:** Progressive enhancement and readable with JavaScript off, but not the mechanism (the script marks the document reveal-capable).

## G-014 · paraphrase · **wrong**

**Q:** Once a project's knowledge base outgrows simple lookup, which search upgrades should be layered on, in what sequence, and how much does each one help?

**Reference:** Contextual embeddings, then contextual BM25, then reranking, in that order. They cut retrieval failures by roughly a third, a half and two-thirds respectively.

**Alpha:** When a project's knowledge base outgrows simple lookup, re-ordering requirements is the first step to manage task renumbering and amendments. Light AI integration follows re-ordering, providing structured one-liner outputs for imperative tasks while delegating structural work to prior phases. Traceability mechanisms, such as spec-notes and warnings, are layered last to ensure all requirements are referenced and uncovered gaps are flagged.

**Retrieval:** miss: another spec

**Why this label:** Answers about re-ordering requirements, from 009; the ladder in 059 FR-002 was never retrieved.

## G-015 · paraphrase · **correct** ⚑

**Q:** Will validation stop me from checking in a reference book whose terms forbid sharing it?

**Reference:** No. A redistribution-restricted document raises a corpus-license finding at warning severity, not an error, because committing it is the project's call; the rule only makes the fact visible.

**Alpha:** Validation will not stop you from checking in a reference book whose terms forbid sharing it. The redistribution policy specifies that material that cannot be redistributed may be held by reference, with a sanctioned escape hatch for such cases.

**Retrieval:** miss: right spec, other pages

**Why this label:** Validation will not stop the commit; misses that it is a warning-severity finding.

## G-016 · paraphrase · **wrong**

**Q:** Is it acceptable for a success criterion to require that something never happens, or always happens, without giving any reasoning?

**Reference:** No. A criterion asserting a threshold of 0 or 100% (or two equal thresholds) must carry a stated justification, because a bare absolute is often an unfalsifiable reflex.

**Alpha:** A success criterion must define two thresholds: a failure level and an aspiration level. The structure of a criterion is critical; it cannot be implied or assumed, as no check reads or owns its shape.

**Retrieval:** miss: right file, other chunks

**Why this label:** Talks about failure and aspiration thresholds; misses the justification rule for 0 or 100%.

## G-017 · paraphrase · **correct**

**Q:** If the one-step visual flow is given a path to a design handoff that it can't open, how far does it get before giving up?

**Reference:** It refuses straight away, before any model call or any file write, and names the path it could not read.

**Alpha:** The one-step visual flow is designed to exit immediately upon encountering an unopenable path, as all visual actions currently end in process.exit(). If the path to a design handoff is unreadable, the one-step visual flow will not attempt to call any model or write any files, effectively giving up without further action.

**Retrieval:** miss: right file, other chunks

**Why this label:** Refuses before any model call or file write. Strict retrieval miss.

## G-018 · paraphrase · **correct** ⚑

**Q:** What performance problem pushed the project to break its flagship specification document into several smaller ones?

**Reference:** At 118 KB the meta-spec took about 140 ms to validate on CI (about 28 ms locally) against a 100 ms per-file budget, so the project failed its own performance requirement.

**Alpha:** The meta-spec breached its own NFR-001 validation budget on continuous integration hardware. The size gauge showed a consistent red status, indicating it exceeded the 5,000-word budget. The lifecycle provided a mechanism for splitting the document, which was followed.

**Retrieval:** hit at rank 1

**Why this label:** The meta-spec breached its own validation budget on CI; no figures.

## G-019 · paraphrase · **correct**

**Q:** Why did the auto-generated verification pages scroll sideways on a narrow phone screen, and how was it fixed?

**Reference:** renderVerifyHtml emitted the trace and observables tables with no scroll container. Both tables are now wrapped in an overflow-x:auto container where they are emitted.

**Alpha:** The auto-generated verification pages scrolled sideways on a narrow phone screen because the tables were not wrapped in an overflow container. The issue was fixed by modifying the renderVerifyHtml function to enclose both tables within an overflow-x:auto container.

**Retrieval:** miss: right file, other chunks

**Why this label:** Tables had no overflow container; renderVerifyHtml now wraps both in overflow-x:auto. Strict retrieval miss.

## G-020 · paraphrase · **correct**

**Q:** In a generated course, learners had nowhere to type their own explanation of an idea. What was wrong, and what changed?

**Reference:** The implementation rendered the teach-back prompt as static prose with no input. It now renders a textarea under the prompt, labelled as not saved, because course content isn't persisted.

**Alpha:** The issue was that the course lacked a <textarea> element for learners to input their own explanations. The change involved modifying the 'course.ts' file to include a <textarea> under the teach-back prompt.

**Retrieval:** hit at rank 3

**Why this label:** Static prompt with no input; a textarea added under the teach-back prompt.

## G-021 · identifier · **correct**

**Q:** What does FR-001 of spec 040, the run budget, require of the BudgetTracker?

**Reference:** It must accumulate the run's estimated output-token spend and expose a phase: normal below 80% of the ceiling, degrade at >=80%, halt at >=100% (always normal when there is no ceiling).

**Alpha:** FR-001 of spec 040, the run budget, requires the BudgetTracker to accumulate the run's estimated output-token spend and expose its phase: normal below 80% of the ceiling, degrade at ≥ 80%, halt at ≥ 100%. With no ceiling it is always normal. When the tracker is in degrade, the run MUST lower the effort it passes to the Decider by one band (via the 034 effort order), clamped at the floor — so decisions convene fewer voters.

**Retrieval:** hit at rank 4

**Why this label:** Accumulate estimated spend; normal, degrade at 80%, halt at 100%.

## G-022 · identifier · **wrong**

**Q:** What does NFR-001 in spec 045, artifact security, require?

**Reference:** FR-001 and FR-002 must be deterministic and must not break the rendering or interactivity of any existing spec-family artifact type, verified by opening representative artifacts in a browser.

**Alpha:** NFR-001 in spec 045, artifact security, requires verification. An unquantified NFR fails at the tiers that promise reliability.

**Retrieval:** miss: right spec, other pages

**Why this label:** Says NFR-001 requires verification; the requirement is determinism and not breaking existing artifacts.

## G-023 · identifier · **abstained wrongly**

**Q:** What does success criterion SC-002 of spec 119, decision resource scope, measure?

**Reference:** That a reviewer in a consuming service is flagged, at the decision's declared posture, when their change touches a store owned elsewhere, in both the direct-write and own-adapter cases: 2 of 2 non-owner fixture scenarios (C and D) must flag.

**Alpha:** Not in the archive.

**Retrieval:** miss: right spec, other pages

**Why this label:** Beta's only claim paraphrased and was dropped; the expected element was not retrieved either.

## G-024 · identifier · **correct** ⚑

**Q:** In the design for spec 026, git strategy, what does decision D-002 settle about where configuration lives?

**Reference:** Config lives in a root spectastic.json with a git section ({"git": {"auto": "off"}}); an absent file or key falls back to defaults (auto=off), chosen over a hidden .spectastic/ directory.

**Alpha:** Decision D-002 settles that configuration lives in a file named spectastic.json at the project root.

**Retrieval:** miss: right file, other chunks

**Why this label:** spectastic.json at the project root; misses the git section and the defaults.

## G-025 · identifier · **wrong**

**Q:** What is task T-100 in the task list for spec 065, corpus PDF convert?

**Reference:** Write a failing test that the default convert path (MarkItDown), with the stub runner and fixture shim, reaches the same terminal pack state as an equivalent adaptCorpus call, in packages/corpus/test/knowledge.convert.test.ts.

**Alpha:** Task T-100 is part of the task list for spec 065, corpus PDF convert, and is described as 'document conversion into the corpus'. Task numbering follows the spec's pattern, with T-1xx corresponding to US1.

**Retrieval:** miss: right file, other chunks

**Why this label:** Describes T-100 generically ('document conversion'); not the failing-test task it is.

## G-026 · identifier · **correct**

**Q:** What does FR-003 of spec 103, content budgets, say about checking a budget?

**Reference:** A budget must be treated as a design constraint and must not be checked against any running text, because the real copy lives in systems the vocabulary cannot see.

**Alpha:** FR-003 of spec 103, content budgets, states that a budget is never checked against running text, because the copy resides in a localisation system or a person's draft. FR-003 forbids a check rather than requiring one, and an assertion is used to prevent it from being added later.

**Retrieval:** miss: right file, other chunks

**Why this label:** A budget is never checked against running text; FR-003 forbids the check.

## G-027 · identifier · **wrong**

**Q:** What is decision D-001 in the design for spec 078, the federated resource URI?

**Reference:** The corpus kind joins the existing shared composer: extend ResourceKind with 'corpus', add a thin named wrapper, and add an optional edition parameter emitted as ?edition= before any fragment.

**Alpha:** Decision D-001 in the design for spec 078, the federated resource URI, is referenced in P-3 as the application of FR-012 to uphold the coordinate as an id contract.

**Retrieval:** miss: right file, other chunks

**Why this label:** Talks about P-3 and FR-012; not what D-001 decides (corpus joins the shared composer).

## G-028 · identifier · **wrong**

**Q:** What is success criterion SC-001 of spec 100, screen flows?

**Reference:** For a feature declaring a journey, a reader can state the order of its screens and the failure branch of each step from the declaration alone, opening 0 other files.

**Alpha:** Success criterion SC-001 of spec 100, screen flows requires acceptance proof through tests T-100 to T-106.

**Retrieval:** miss: right file, other chunks

**Why this label:** Quotes 108's verify page about tests T-100 to T-106; not spec 100's SC-001.

## G-029 · relation · **wrong**

**Q:** Which success criteria in spec 109, the prose theme, validate FR-008 (the receding sticky header)?

**Reference:** Two: SC-003 (keyboard readers reach every control the receding header carries, 100%) and SC-001 (reviewers read a long artifact end to end in one sitting); both list FR-008 in their validates attribute.

**Alpha:** FR-008, the receding sticky header, is validated by the rationale in FR-009 which scopes the sticky, backdrop-blurred header to vivid only, resolving the P-5 calm-density tension. The amendment in P-5 (calm density) is referenced as a check, not a blocker, which aligns with the validation of FR-008 through the calm-density tension resolution.

**Retrieval:** miss: another spec

**Why this label:** Answers from 016's triage log about FR-009; never names SC-001 or SC-003.

## G-030 · relation · **wrong**

**Q:** Which requirements does success criterion SC-002 of spec 110, visual one-step, validate, and what do they demand?

**Reference:** FR-003 and NFR-001: before any model call or file write, the invocation must refuse when the named export cannot be read and name the path; a refusing run makes 0 model calls and writes 0 files.

**Alpha:** Success criterion SC-002 of spec 110, visual one-step, validates the requirement to 'land the visuals in one step'. This requirement demands a method to run, demo, and verify the feature, with a Run/Demo block grounded in an actual run.

**Retrieval:** miss: right spec, other pages

**Why this label:** Never names FR-003 or NFR-001.

## G-031 · relation · **wrong**

**Q:** Spec 058's corpus-license rule reads a license field that 058 says it does not own. Which spec defines that field, and what else goes in that frontmatter?

**Reference:** 051-knowledge-corpus (FR-003): every corpus document carries provenance frontmatter of origin/origin-url, edition, license, converter, a content hash and a status.

**Alpha:** Spec 058's corpus-license rule references a license field that it does not own, as per the design document. The field in question is defined by the corpus-licensing spec, which includes a permissive allowlist and a written policy for escape hatches.

**Retrieval:** miss: right spec, other pages

**Why this label:** Says 058 itself defines the field; it is 051 FR-003.

## G-032 · relation · **wrong**

**Q:** Spec 055 (corpus in review) leaves injecting the corpus into the authoring verbs out of scope. Which spec handles that, and what does it require?

**Reference:** 054-corpus-in-prompt: when a corpus is present, core must inject its index and a grounding directive into every AI-verb prompt, using the same fenced mechanism that injects the principles.

**Alpha:** Spec 055 (corpus in review) does not include injecting the corpus into the authoring verbs. The requirement for injecting the corpus into the authoring verbs is addressed in another specification, though the exact reference is not provided in the quoted text.

**Retrieval:** miss: right file, other chunks

**Why this label:** Says another spec handles it but cannot say which; 054 was never retrieved.

## G-033 · relation · **correct**

**Q:** Spec 023's design dropped its decision on generating restore tasks after an exploration graduates. Which slice took that over, and how is restore invoked now?

**Reference:** It moved to the sibling slice TBD-explore-restore, now 024-explore-restore, where restore is a mode of /spectastic.tasks: /spectastic.tasks <id> --restore, or an announced prompt when a graduated marker is present.

**Alpha:** Spec 023's decision to generate restore tasks was split out into a separate slice, 024-explore-restore. The restore path is now invoked explicitly via a --restore flag or an announced prompt, and the output is banner-labelled with its classification.

**Retrieval:** miss: right file, other chunks

**Why this label:** Moved to 024-explore-restore; restore via --restore or an announced prompt.

## G-034 · relation · **correct**

**Q:** Which spec superseded 001-cli, and what did it require happen to the old Python CLI?

**Reference:** 003-init-node-port: at its apply, scripts/spectastic and scripts/test_spectastic.py were removed and 001-cli's status flipped to superseded with a forward link to 003; 001 stays as historical record.

**Alpha:** Spec 001-cli was superseded by 003-init-node-port on 15 Jun 2026. The old Python CLI described in 001-cli was deleted from the repo, and spectastic init now lives as a subcommand of @spectastic/cli.

**Retrieval:** miss: right spec, other pages

**Why this label:** Superseded by 003-init-node-port; the Python CLI was deleted.

## G-035 · relation · **wrong**

**Q:** In spec 062, corpus identity migration, which test task proves success criterion SC-002, and what does that task test?

**Reference:** T-300: red-first resolver tests showing two packs sharing a legacy id resolve by registry identity, not array order; edition-pinned citations to a retained superseded edition still resolve; and a registry-present absent id returns null.

**Alpha:** In spec 062, the test task that proves success criterion SC-002 is 'Phase 3a — US1 · Reshape & register both packs Tests (write & fail first)'. This task tests regression-testing the migrated registry, asserting the committed root registry holds exactly KB-0001/KB-0002 at their expected coordinates and that allocateRegistryIds/mergeRegistryRows never reuse an id.

**Retrieval:** hit at rank 2

**Why this label:** Names a phase heading, not T-300, and describes a different test.

## G-036 · relation · **wrong**

**Q:** Spec 076 emits a change notification when a contract is promoted. Which spec provides that promotion hook, and where does promotion actually run?

**Reference:** 071-contract-promotion (its US1 promotion hook); per 071's D-002, promotion runs inside applyCommand, immediately before the existing proposal-archive step, with no new verb.

**Alpha:** Spec 076's change notification is triggered by the promotion process, which is a side effect of the apply function. The promotion hook is provided by the apply function, which folds a proposal and archives it.

**Retrieval:** miss: right file, other chunks

**Why this label:** Says the apply function provides the hook; never names 071.

## G-037 · stale · **correct**

**Q:** How does spec 004's npm publish workflow derive the dist-tag, and what implements that logic?

**Reference:** A tested Node script, scripts/derive-dist-tag.mjs: a pure deriveDistTags(version, publishedVersions) plus one network function, keyed on whether a stable release exists, and failing rather than guessing when registry state is unknown.

**Alpha:** Spec 004's npm publish workflow derives the dist-tag via scripts/derive-dist-tag.mjs, which computes the tag set based on the existence of a stable release rather than the version string. The logic implemented in scripts/derive-dist-tag.mjs moves pre-releases to both next and latest until a stable release exists, after which pre-releases are directed only to next.

**Retrieval:** miss: right file, other chunks

**Why this label:** The derive-dist-tag.mjs script keyed on whether a stable release exists: the current D-006, not the superseded inline bash rule.

## G-038 · stale · **wrong** · stale as current

**Q:** How quickly must spectastic init complete in an empty directory?

**Reference:** Under 500 ms p95 on a modern laptop (Apple M-series or comparable); the work is pure filesystem with no network.

**Alpha:** In an empty directory on a modern macOS or Linux machine, spectastic init MUST complete in under 2 seconds wall-clock.

**Retrieval:** miss: another spec

**Why this label:** 'Under 2 seconds' is the superseded 001-cli requirement; the current one is under 500 ms p95.

## G-039 · stale · **correct**

**Q:** What are the eight lifecycle slash commands spectastic must ship?

**Reference:** /spectastic.principles, .spec, .design, .tasks, .implement, .propose, .apply and .triage; extended opt-in verbs such as explain and explore may also ship.

**Alpha:** Spectastic must ship eight lifecycle slash commands: /spectastic.principles, /spectastic.spec, /spectastic.design, /spectastic.tasks, /spectastic.implement, /spectastic.propose, /spectastic.apply, and /spectastic.triage.

**Retrieval:** miss: another spec

**Why this label:** All eight commands, including /spectastic.implement.

## G-040 · stale · **wrong** · stale as current

**Q:** How many files does spectastic init produce in an empty directory after a global npm install, according to the publish spec's success criterion?

**Reference:** A 40-file tree, byte-identical to the local-clone install (the count rose from 32 when the default scaffold began writing the eight portable Agent-Skills SKILL.md files).

**Alpha:** According to the publish spec's success criterion, spectastic init produces a 29-file tree in an empty directory after a global npm install.

**Retrieval:** miss: right spec, other pages

**Why this label:** '29-file tree' comes from an older archived proposal; the current criterion is 40 files. Not caught by the stale check: that proposal is not in the question's stale list.

## G-041 · stale · **wrong**

**Q:** In spec 094, the visual sidecar convention, which operation must stat only the declared paths, and what are its limits?

**Reference:** Path resolution: at most 1 filesystem call per declaration and 0 directory walks, so a project with many specs pays a cost linear in declarations rather than files.

**Alpha:** In spec 094, the visual sidecar convention requires that a declared path must sit at its scope's conventional location. The operation must stat only the declared paths, and its limits are that two designs disagreeing about where the token set lives is an error rather than a union.

**Retrieval:** miss: right file, other chunks

**Why this label:** Answers about conventional locations and token-set disagreement; not path resolution's 1 call and 0 walks.

## G-042 · stale · **wrong**

**Q:** In spec 099, the visual embedded view, what must happen when a materialised view no longer matches what it projects, and what is it compared against?

**Reference:** It must be reported, comparing the view against the files it projects as they currently are, not against a stored digest.

**Alpha:** When a materialised view no longer matches what it projects, a drift check must occur. The drift check compares a rendering of the declared screens against what the design carries.

**Retrieval:** miss: right file, other chunks

**Why this label:** Says the drift check compares rendered screens; the current rule compares against the files as they are now, not a digest.

## G-043 · stale · **wrong** · stale as current

**Q:** How is an individual declared screen addressed by a resource coordinate in spectastic?

**Reference:** By a resource coordinate of its own kind, qualified by the owning spec; each screen must declare the name it is addressed by, and two screens in one spec resolving to the same name are an error.

**Alpha:** An individual declared screen is addressed by a resource coordinate that extends the existing spectastic:// grammar. The resource kind 'screen' is explicitly included in the shared list of resource kinds for the coordinate grammar. The screen resource URI does not include a name, as the view's model is designed to remain minimal.

**Retrieval:** miss: right spec, other pages

**Why this label:** Partly from a withdrawn proposal ('the screen resource URI does not include a name'), which contradicts the current FR-013. Not caught by the stale check.

## G-044 · stale · **partly** ⚑

**Q:** How does the verify view (spec 021) decide which tasks are test tasks when tracing success criteria, and what happens if a story phase has no Tests subsection?

**Reference:** The primary signal is a task under the story's 'Tests (write & fail first)' subsection; when a phase has no Tests subsection, it falls back to a file-path test pattern (.test. / .spec.).

**Alpha:** The verify view identifies test tasks by file path (TEST_PATH) when tracing success criteria, as seen in the case of 025-id-uniqueness. If a story phase has no Tests subsection, the verify view falls back to identifying test tasks by file path matching test-file patterns (.test. / .spec.).

**Retrieval:** miss: right spec, other pages

**Why this label:** Gets the fallback to file-path patterns, but presents it as the primary signal.

## G-045 · unanswerable · **declined in own words**

**Q:** Is there a JetBrains plugin (IntelliJ or WebStorm) for spectastic's lifecycle canvas, like the VS Code extension?

**Reference:** Not covered in specs/.

**Alpha:** The archive mentions a lifecycle canvas for VS Code, but does not reference a JetBrains plugin for spectastic. The design document describes a lifecycle canvas as a webview feature, not a JetBrains plugin.

**Retrieval:** nothing to find

**Why this label:** 'does not reference a JetBrains plugin': a correct decline the exact-phrase check misses.

## G-046 · unanswerable · **answered beside the point**

**Q:** Can spectastic push the tasks in tasks.html to Jira so that they show up as tickets?

**Reference:** Not covered in specs/.

**Alpha:** spectastic generates a single-file artifact for tasks.html, which is ready to write to specs/<spec-id>/tasks.html. spectastic is designed to fold a proposal's tasks into a target's tasks.html, creating a new <spec-task> phase linked to the target's sequence.

**Retrieval:** nothing to find

**Why this label:** Describes tasks.html generation; never says there is no Jira sync.

## G-047 · unanswerable · **accepted false premise**

**Q:** Which compliance frameworks, such as SOC 2, HIPAA, GDPR or ISO 27001, does the enterprise profile map its controls to?

**Reference:** Not covered in specs/.

**Alpha:** The enterprise profile maps its controls to compliance frameworks by defining required categories and gate severity, ensuring coverage through signal presence. The enforcement mechanism is grounded in spectastic's own rules, with guarantees enforced at the git/CI boundary rather than through direct validation.

**Retrieval:** nothing to find

**Why this label:** Says the enterprise profile maps controls to compliance frameworks; nothing in the archive says so.

## G-048 · unanswerable · **answered beside the point**

**Q:** Can two people edit the same spec at the same time, Google Docs style, with live collaboration?

**Reference:** Not covered in specs/.

**Alpha:** The archive discusses collaboration via GitHub PR with a rendered preview or a dedicated viewer supporting inline comments. The diff process is mechanical, involving heading + paragraph → component with stable ID and priority.

**Retrieval:** nothing to find

**Why this label:** Talks about PR review with inline comments; never says there is no live co-editing.

## G-049 · unanswerable · **answered beside the point**

**Q:** Is there an official Docker image for running the spectastic CLI in CI?

**Reference:** Not covered in specs/.

**Alpha:** The spectastic CLI includes a 'run' command with full suite and validate options, indicating a structured testing approach. Versioning for cli, schema, and core packages is synchronized, suggesting a coordinated release strategy. A stub AIProvider is used in specCommand without Claude Code, which is already covered by T-100.

**Retrieval:** nothing to find

**Why this label:** Lists CLI facts; never addresses a Docker image.

## G-050 · unanswerable · **declined in own words**

**Q:** Can spectastic export a finished spec as a Microsoft Word (.docx) document?

**Reference:** Not covered in specs/.

**Alpha:** Spectastic MAY shell out to a CLI for deterministic operations, but there is no mention of exporting to .docx. The kernel function MUST NOT write to the filesystem, implying that file export, including .docx, is not part of its core functionality.

**Retrieval:** nothing to find

**Why this label:** 'no mention of exporting to .docx': a correct decline the exact-phrase check misses.
