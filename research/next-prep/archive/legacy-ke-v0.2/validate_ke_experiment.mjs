import fs from "node:fs";
import {canonicalEquation, evaluateCall, makeEnvironment, parseEquation, typeCheckEquation} from "./ke-runtime.mjs";

const source = JSON.parse(fs.readFileSync("KE-test.json", "utf8"));
const ontology = JSON.parse(fs.readFileSync("KE-ontology.json", "utf8"));
const extraction = JSON.parse(fs.readFileSync("KE-extraction.json", "utf8"));
const fail = (message) => { throw new Error(message); };

if (ontology.schema_version !== "ke_ontology_v0.2") fail("ontology version");
if (extraction.schema_version !== "ke_extraction_v0.2") fail("extraction version");
const conceptIds = new Set(ontology.concepts.map((item) => item.id));
if (conceptIds.size !== ontology.concepts.length) fail("duplicate concept id");
const operatorIds = new Set();
const operatorSymbols = new Set();
for (const operator of ontology.operators) {
  if (operatorIds.has(operator.id) || operatorSymbols.has(operator.symbol)) fail(`duplicate operator ${operator.symbol}`);
  operatorIds.add(operator.id); operatorSymbols.add(operator.symbol);
  if (!Number.isInteger(operator.arity) || operator.arity !== operator.parameters.length) fail(`operator arity ${operator.symbol}`);
  if (!conceptIds.has(operator.return_concept_id)) fail(`operator return type ${operator.symbol}`);
  if (!operator.evaluation?.mode || !["constructor", "builtin", "assertion_lookup", "tool_binding"].includes(operator.evaluation.mode)) fail(`operator evaluation ${operator.symbol}`);
  for (const parameter of operator.parameters) if (!parameter.allowed_concept_ids.length || parameter.allowed_concept_ids.some((id) => !conceptIds.has(id))) fail(`operator parameter ${operator.symbol}`);
}
for (const concept of ontology.concepts) for (const parent of concept.parent_concept_ids) if (!conceptIds.has(parent)) fail(`concept parent ${concept.id}`);

const individualSymbols = new Set();
for (const individual of [...ontology.individuals, ...extraction.individuals]) {
  if (!individual.symbol || individualSymbols.has(individual.symbol)) fail(`duplicate or missing individual ${individual.symbol}`);
  individualSymbols.add(individual.symbol);
  if (!individual.concept_ids?.length || individual.concept_ids.some((id) => !conceptIds.has(id))) fail(`individual type ${individual.symbol}`);
}

const env = makeEnvironment(ontology, extraction);
for (const example of ontology.language_examples) typeCheckEquation(parseEquation(example), env);
const sourceById = new Map(source.candidates.map((candidate) => [candidate.id, candidate]));
const evidenceById = new Map(extraction.evidence.map((item) => [item.id, item]));
if (evidenceById.size !== extraction.evidence.length) fail("duplicate evidence id");
const factIds = new Set();
const keIds = new Set();
const factOnlyIds = new Set();
const knowledge = [];
let turnCount = 0;
let speakerCount = 0;
let segmentCount = 0;

for (const candidate of extraction.candidate_results) {
  const sourceCandidate = sourceById.get(candidate.candidate_id);
  if (!sourceCandidate || candidate.turn_results.length !== sourceCandidate.turns.length) fail(`candidate coverage ${candidate.candidate_id}`);
  for (const turn of candidate.turn_results) {
    turnCount += 1;
    const sourceTurn = sourceCandidate.turns[turn.turn_index - 1];
    if (!sourceTurn || turn.speaker_results.length !== 2) fail(`turn shape ${candidate.candidate_id}/${turn.turn_index}`);
    for (const speakerResult of turn.speaker_results) {
      speakerCount += 1;
      const expectedText = speakerResult.speaker === "user" ? sourceTurn.user : sourceTurn.agent;
      if (speakerResult.raw_text !== expectedText) fail(`raw text mismatch ${candidate.candidate_id}/${turn.turn_index}/${speakerResult.speaker}`);
      if (!speakerResult.coverage?.raw_text_preserved || speakerResult.coverage.source_length !== expectedText.length || speakerResult.coverage.uncovered_ranges.length) fail("coverage metadata");
      let cursor = 0;
      for (const segment of speakerResult.source_segments) {
        segmentCount += 1;
        if (segment.start !== cursor || segment.end <= segment.start || segment.quote !== expectedText.slice(segment.start, segment.end)) fail(`coverage gap ${candidate.candidate_id}/${turn.turn_index}/${speakerResult.speaker}`);
        cursor = segment.end;
      }
      if (cursor !== expectedText.length) fail(`coverage tail ${candidate.candidate_id}/${turn.turn_index}/${speakerResult.speaker}`);
      if (speakerResult.facts.length !== speakerResult.source_segments.length) fail("fact/segment mismatch");
      for (const fact of speakerResult.facts) {
        if (factIds.has(fact.id)) fail(`duplicate fact ${fact.id}`);
        factIds.add(fact.id);
        if (!fact.verbatim || !fact.evidence_ids.length || fact.evidence_ids.some((id) => !evidenceById.has(id))) fail(`fact evidence ${fact.id}`);
      }
      for (const ke of speakerResult.kes) {
        if (keIds.has(ke.id)) fail(`duplicate ke ${ke.id}`);
        keIds.add(ke.id);
        const equation = parseEquation(ke.expression);
        const types = typeCheckEquation(equation, env);
        if (ke.canonical_expression !== canonicalEquation(equation) || ke.lhs_type !== types.left_type || ke.rhs_type !== types.right_type) fail(`KE canonical/type ${ke.id}`);
        if (!ke.evidence_ids.length || ke.evidence_ids.some((id) => !evidenceById.has(id))) fail(`KE evidence ${ke.id}`);
        knowledge.push(equation);
      }
      for (const item of speakerResult.fact_only) {
        if (factOnlyIds.has(item.id)) fail(`duplicate fact-only ${item.id}`);
        factOnlyIds.add(item.id);
        if (!item.reason || !factIds.has(item.fact_id) || !item.verbatim) fail(`fact-only structure ${item.id}`);
      }
    }
  }
}

for (const evidence of extraction.evidence) {
  const candidate = sourceById.get(evidence.candidate_id);
  const turn = candidate?.turns[evidence.turn_index - 1];
  const raw = evidence.speaker === "user" ? turn?.user : turn?.agent;
  if (!raw || evidence.quote !== raw.slice(evidence.span.start, evidence.span.end)) fail(`evidence span ${evidence.id}`);
}

const summary = extraction.summary;
if (turnCount !== 43 || speakerCount !== 86 || segmentCount !== summary.source_segment_count || factIds.size !== summary.fact_count || keIds.size !== summary.ke_count || factOnlyIds.size !== summary.fact_only_count) fail("summary counts");
if (!summary.information_loss.raw_text_preserved || summary.information_loss.uncovered_range_count !== 0) fail("information loss summary");

const exampleKnowledge = ontology.language_examples.map(parseEquation);
const directoryResult = evaluateCall("directory_of(Doc_设计文档_语义)", env, exampleKnowledge);
if (directoryResult.symbol !== "Directory" || directoryResult.args?.[0]?.value !== "docs/specs/ke_semantics.md") fail("directory_of evaluation");
const predicateResult = evaluateCall("doc_of(Proj_解释器,Doc_设计文档_语义)", env, exampleKnowledge);
if (predicateResult.symbol !== "Boolean_true") fail("doc_of evaluation");
const unknownResult = evaluateCall("doc_of(Proj_解释器,Doc_设计文档_语义)", env, []);
if (unknownResult.symbol !== "Boolean_unknown") fail("open-world predicate evaluation");
const currentDirectory = evaluateCall("current_dir()", env, knowledge);
if (currentDirectory.symbol !== "Directory" || !currentDirectory.args?.[0]?.value) fail("current_dir evaluation");

console.log(`PASS ontology/runtime: concepts=${ontology.concepts.length} operators=${ontology.operators.length} typed_symbols=${individualSymbols.size}`);
console.log(`PASS lossless coverage: candidates=10 turns=${turnCount} speakers=${speakerCount} segments=${segmentCount} uncovered=0`);
console.log(`PASS KE extraction: kes=${keIds.size} fact_only=${factOnlyIds.size} all_typed=true`);
console.log("PASS operator execution: constructor+builtin+lookup+open_world_predicate");
console.log("ALL_VALIDATIONS_PASSED");
