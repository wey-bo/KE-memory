import fs from "node:fs";
import path from "node:path";

const IDENTIFIER = /[A-Za-z_\u0080-\uFFFF][A-Za-z0-9_\u0080-\uFFFF-]*/u;

export class KeSyntaxError extends Error {}
export class KeTypeError extends Error {}

function tokenize(source) {
  const tokens = [];
  let index = 0;
  while (index < source.length) {
    const char = source[index];
    if (/\s/u.test(char)) { index += 1; continue; }
    if (char === "(") { tokens.push({kind: "lparen", value: char}); index += 1; continue; }
    if (char === ")") { tokens.push({kind: "rparen", value: char}); index += 1; continue; }
    if (char === ",") { tokens.push({kind: "comma", value: char}); index += 1; continue; }
    if (char === "=") { tokens.push({kind: "equals", value: char}); index += 1; continue; }
    if (char === "\"") {
      let end = index + 1;
      let escaped = false;
      while (end < source.length) {
        const c = source[end];
        if (!escaped && c === "\"") break;
        escaped = !escaped && c === "\\";
        if (c !== "\\") escaped = false;
        end += 1;
      }
      if (end >= source.length) throw new KeSyntaxError(`Unclosed string at ${index}`);
      const raw = source.slice(index, end + 1);
      let value;
      try { value = JSON.parse(raw); } catch { throw new KeSyntaxError(`Invalid string at ${index}`); }
      tokens.push({kind: "string", value});
      index = end + 1;
      continue;
    }
    const number = source.slice(index).match(/^-?(?:\d+\.\d+|\d+)/u);
    if (number) {
      tokens.push({kind: "number", value: Number(number[0])});
      index += number[0].length;
      continue;
    }
    const identifier = source.slice(index).match(IDENTIFIER);
    if (identifier) {
      tokens.push({kind: "identifier", value: identifier[0]});
      index += identifier[0].length;
      continue;
    }
    throw new KeSyntaxError(`Unexpected character ${char} at ${index}`);
  }
  tokens.push({kind: "eof", value: ""});
  return tokens;
}

export function parseTerm(source) {
  const tokens = tokenize(source);
  let cursor = 0;
  const parse = () => {
    const token = tokens[cursor];
    if (token.kind === "string") { cursor += 1; return {kind: "string", value: token.value}; }
    if (token.kind === "number") { cursor += 1; return {kind: "number", value: token.value}; }
    if (token.kind !== "identifier") throw new KeSyntaxError(`Expected term at token ${cursor}`);
    cursor += 1;
    if (tokens[cursor].kind !== "lparen") return {kind: "symbol", symbol: token.value};
    cursor += 1;
    const args = [];
    if (tokens[cursor].kind !== "rparen") {
      while (true) {
        args.push(parse());
        if (tokens[cursor].kind === "rparen") break;
        if (tokens[cursor].kind !== "comma") throw new KeSyntaxError(`Expected comma at token ${cursor}`);
        cursor += 1;
      }
    }
    cursor += 1;
    return {kind: "call", symbol: token.value, args};
  };
  const term = parse();
  if (tokens[cursor].kind !== "eof") throw new KeSyntaxError(`Trailing tokens at ${cursor}`);
  return term;
}

export function parseEquation(source) {
  let splitAt = -1;
  let depth = 0;
  let inString = false;
  let escaped = false;
  for (let i = 0; i < source.length; i += 1) {
    const c = source[i];
    if (inString) {
      if (!escaped && c === "\"") inString = false;
      escaped = !escaped && c === "\\";
      if (c !== "\\") escaped = false;
      continue;
    }
    if (c === "\"") { inString = true; continue; }
    if (c === "(") depth += 1;
    else if (c === ")") depth -= 1;
    else if (c === "=" && depth === 0) { splitAt = i; break; }
  }
  if (splitAt < 0) throw new KeSyntaxError("KE must contain one top-level '='");
  return {kind: "equation", left: parseTerm(source.slice(0, splitAt).trim()), right: parseTerm(source.slice(splitAt + 1).trim()), source};
}

function conceptAncestors(concepts) {
  const byId = new Map(concepts.map((concept) => [concept.id, concept]));
  const memo = new Map();
  const visit = (id, active = new Set()) => {
    if (memo.has(id)) return memo.get(id);
    if (active.has(id)) throw new KeTypeError(`Concept cycle at ${id}`);
    const concept = byId.get(id);
    if (!concept) return new Set();
    const result = new Set([id]);
    const nextActive = new Set(active).add(id);
    for (const parent of concept.parent_concept_ids || []) for (const item of visit(parent, nextActive)) result.add(item);
    memo.set(id, result);
    return result;
  };
  return (id) => visit(id);
}

export function makeEnvironment(ontology, extraction = null) {
  const byOperator = new Map(ontology.operators.map((operator) => [operator.symbol, operator]));
  const bySymbol = new Map((ontology.individuals || []).map((individual) => [individual.symbol, individual]));
  for (const individual of extraction?.individuals || []) bySymbol.set(individual.symbol, individual);
  const ancestors = conceptAncestors(ontology.concepts);
  return {ontology, extraction, byOperator, bySymbol, isSubtype: (actual, expected) => actual === expected || ancestors(actual).has(expected)};
}

function termType(term, env) {
  if (term.kind === "string") return "concept_string";
  if (term.kind === "number") return "concept_number";
  if (term.kind === "symbol") {
    const individual = env.bySymbol.get(term.symbol);
    if (!individual) throw new KeTypeError(`Undeclared typed individual ${term.symbol}`);
    if (!individual.concept_ids?.length) throw new KeTypeError(`Individual has no type ${term.symbol}`);
    return individual.concept_ids[0];
  }
  if (term.kind === "call") {
    const operator = env.byOperator.get(term.symbol);
    if (!operator) throw new KeTypeError(`Unknown operator ${term.symbol}`);
    if (term.args.length !== operator.arity) throw new KeTypeError(`${term.symbol} expects ${operator.arity} args, got ${term.args.length}`);
    for (let i = 0; i < term.args.length; i += 1) {
      const actual = termType(term.args[i], env);
      const allowed = operator.parameters[i]?.allowed_concept_ids || [];
      if (allowed.length && !allowed.some((expected) => env.isSubtype(actual, expected))) throw new KeTypeError(`${term.symbol} arg ${i + 1} type ${actual} not in ${allowed.join(",")}`);
    }
    return operator.return_concept_id;
  }
  throw new KeTypeError("Unknown term kind");
}

export function typeCheckEquation(equation, env) {
  if (equation.kind !== "equation" || equation.left.kind !== "call") throw new KeTypeError("KE lhs must be an operator application");
  const leftType = termType(equation.left, env);
  const rightType = termType(equation.right, env);
  if (!env.isSubtype(rightType, leftType)) throw new KeTypeError(`KE result mismatch: ${leftType} = ${rightType}`);
  return {left_type: leftType, right_type: rightType};
}

export function canonicalTerm(term) {
  if (term.kind === "symbol") return term.symbol;
  if (term.kind === "string") return JSON.stringify(term.value);
  if (term.kind === "number") return String(term.value);
  return `${term.symbol}(${term.args.map(canonicalTerm).join(",")})`;
}

export function canonicalEquation(equation) { return `${canonicalTerm(equation.left)}=${canonicalTerm(equation.right)}`; }

function evaluateTerm(term, env, knowledge) {
  if (term.kind === "symbol") return {kind: "symbol", symbol: term.symbol, type: termType(term, env)};
  if (term.kind === "string" || term.kind === "number") return {kind: term.kind, value: term.value, type: termType(term, env)};
  const operator = env.byOperator.get(term.symbol);
  const args = term.args.map((arg) => evaluateTerm(arg, env, knowledge));
  if (operator.evaluation?.mode === "builtin") {
    if (term.symbol === "current_dir") return {kind: "call", symbol: "Directory", args: [{kind: "string", value: process.cwd()}], type: operator.return_concept_id};
    if (operator.evaluation.implementation === "identity") return {kind: "call", symbol: operator.symbol, args, type: operator.return_concept_id};
  }
  if (operator.evaluation?.mode === "constructor") return {kind: "call", symbol: operator.symbol, args, type: operator.return_concept_id};
  if (operator.evaluation?.mode === "assertion_lookup") {
    const key = canonicalTerm(term);
    const match = (knowledge || []).find((equation) => canonicalTerm(equation.left) === key);
    if (match) return evaluateTerm(match.right, env, knowledge);
    if (operator.return_concept_id === "concept_boolean") return {kind: "symbol", symbol: "Boolean_unknown", type: "concept_boolean"};
    return {kind: "symbol", symbol: "Unknown", type: operator.return_concept_id};
  }
  return {kind: "call", symbol: operator.symbol, args, type: operator.return_concept_id, evaluation: "unbound"};
}

export function evaluateCall(source, env, knowledge = []) {
  const term = source.includes("=") ? parseEquation(source).left : parseTerm(source);
  if (term.kind !== "call") throw new KeSyntaxError("Evaluation input must be an operator application");
  termType(term, env);
  return evaluateTerm(term, env, knowledge);
}

function cli() {
  const command = process.argv[2];
  if (!command) return;
  const root = path.dirname(new URL(import.meta.url).pathname).replace(/^\/(\w):/, "$1:");
  const ontology = JSON.parse(fs.readFileSync(path.join(root, "KE-ontology.json"), "utf8"));
  const extraction = JSON.parse(fs.readFileSync(path.join(root, "KE-extraction.json"), "utf8"));
  const env = makeEnvironment(ontology, extraction);
  if (command === "check") {
    let total = 0;
    for (const candidate of extraction.candidate_results) for (const turn of candidate.turn_results) for (const speaker of turn.speaker_results) for (const ke of speaker.kes) { typeCheckEquation(parseEquation(ke.expression), env); total += 1; }
    console.log(`PASS ke-runtime check: ${total} equations typed`);
  } else if (command === "eval") {
    const expression = process.argv.slice(3).join(" ");
    const knowledge = [];
    for (const candidate of extraction.candidate_results) for (const turn of candidate.turn_results) for (const speaker of turn.speaker_results) for (const ke of speaker.kes) knowledge.push(parseEquation(ke.expression));
    console.log(JSON.stringify(evaluateCall(expression, env, knowledge)));
  } else if (command === "selftest") {
    const examples = ontology.language_examples || [];
    for (const expression of examples) typeCheckEquation(parseEquation(expression), env);
    console.log(`PASS ke-runtime selftest: ${examples.length} typed examples accepted`);
  }
}

const invoked = process.argv[1] ? path.resolve(process.argv[1]).replaceAll("\\", "/") : "";
if (invoked && import.meta.url.endsWith(invoked.replace(/^\w:/, ""))) cli();
