import fs from "node:fs";
import path from "node:path";
import {slotExpressions} from "./ke-specs.mjs";
import {canonicalEquation, makeEnvironment, parseEquation, typeCheckEquation} from "./ke-runtime.mjs";

const ROOT = path.dirname(new URL(import.meta.url).pathname).replace(/^\/(\w):/, "$1:");
const sourceData = JSON.parse(fs.readFileSync(path.join(ROOT, "KE-test.json"), "utf8"));
const MODEL = "OpenAI Codex (GPT-5)";
const ONTOLOGY_ID = "ke_memory_language_v0_2";
const WORKFLOW_ID = "workflow_run_ke_extract_v0_2";

const concepts = [];
const conceptIds = new Set();
function concept(id, symbol, parents = [], description = "") {
  if (conceptIds.has(id)) throw new Error(`Duplicate concept ${id}`);
  conceptIds.add(id);
  concepts.push({id, symbol, kind: "class", parent_concept_ids: parents, aliases: [], description, source_kind: "human_defined"});
}

concept("concept_entity", "Entity");
concept("concept_actor", "Actor", ["concept_entity"]);
concept("concept_person", "Person", ["concept_actor"]);
concept("concept_agent", "Agent", ["concept_actor"]);
concept("concept_organization", "Organization", ["concept_actor"]);
concept("concept_artifact", "Artifact", ["concept_entity"]);
concept("concept_project", "Project", ["concept_artifact"]);
concept("concept_document", "Document", ["concept_artifact"]);
concept("concept_directory", "Directory", ["concept_artifact"]);
concept("concept_software_project", "SoftwareProject", ["concept_project"]);
concept("concept_dependency", "Dependency", ["concept_artifact"]);
concept("concept_formula", "Formula", ["concept_artifact"]);
concept("concept_dataframe", "DataFrame", ["concept_artifact"]);
concept("concept_column", "Column", ["concept_artifact"]);
concept("concept_message", "Message", ["concept_document"]);
concept("concept_email", "Email", ["concept_message"]);
concept("concept_product", "Product", ["concept_artifact"]);
concept("concept_order", "Order", ["concept_artifact"]);
concept("concept_tool", "Tool", ["concept_artifact"]);
concept("concept_method", "Method", ["concept_artifact"]);
concept("concept_evidence", "Evidence", ["concept_artifact"]);
concept("concept_activity", "Activity", ["concept_entity"]);
concept("concept_event", "Event", ["concept_activity"]);
concept("concept_task", "Task", ["concept_activity"]);
concept("concept_action", "Action", ["concept_activity"]);
concept("concept_plan", "Plan", ["concept_artifact"]);
concept("concept_meeting", "Meeting", ["concept_event"]);
concept("concept_goal", "Goal", ["concept_entity"]);
concept("concept_requirement", "Requirement", ["concept_entity"]);
concept("concept_strategy", "Strategy", ["concept_plan"]);
concept("concept_option", "Option", ["concept_entity"]);
concept("concept_topic", "Topic", ["concept_entity"]);
concept("concept_claim", "Claim", ["concept_entity"]);
concept("concept_issue", "Issue", ["concept_entity"]);
concept("concept_value", "Value", ["concept_entity"]);
concept("concept_path", "Path", ["concept_value"]);
concept("concept_status", "Status", ["concept_value"]);
concept("concept_role", "Role", ["concept_value"]);
concept("concept_parameter", "Parameter", ["concept_entity"]);
concept("concept_theme", "Theme", ["concept_entity"]);
concept("concept_platform", "Platform", ["concept_organization"]);
concept("concept_stimulus", "Stimulus", ["concept_artifact"]);
concept("concept_flight", "Flight", ["concept_task"]);
concept("concept_payment_method", "PaymentMethod", ["concept_entity"]);
concept("concept_will", "Will", ["concept_document"]);
concept("concept_child", "Child", ["concept_person"]);
concept("concept_conversation_turn", "ConversationTurn", ["concept_event"]);
concept("concept_type_descriptor", "TypeDescriptor", ["concept_value"]);
concept("concept_scalar", "Scalar", ["concept_value"]);
concept("concept_string", "String", ["concept_scalar"]);
concept("concept_number", "Number", ["concept_scalar"]);
concept("concept_integer", "Integer", ["concept_number"]);
concept("concept_percentage", "Percentage", ["concept_number"]);
concept("concept_boolean", "Boolean", ["concept_scalar"]);
concept("concept_temporal", "TemporalValue", ["concept_value"]);
concept("concept_date", "Date", ["concept_temporal"]);
concept("concept_relative_date", "RelativeDate", ["concept_temporal"]);
concept("concept_day_of_month", "DayOfMonth", ["concept_temporal"]);
concept("concept_date_range", "DateRange", ["concept_temporal"]);
concept("concept_duration", "Duration", ["concept_temporal"]);
concept("concept_time", "Time", ["concept_temporal"]);
concept("concept_money", "Money", ["concept_value"]);
concept("concept_currency", "Currency", ["concept_value"]);
concept("concept_location", "Location", ["concept_entity"]);
concept("concept_reason", "Reason", ["concept_value"]);
concept("concept_action_result", "ActionResult", ["concept_value"]);
concept("concept_tone", "Tone", ["concept_value"]);

const operators = [];
const operatorSymbols = new Set();
function operator(symbol, kind, parameterTypes, returnType, mode = "assertion_lookup", properties = {}) {
  if (operatorSymbols.has(symbol)) throw new Error(`Duplicate operator ${symbol}`);
  operatorSymbols.add(symbol);
  operators.push({id: `op_${symbol.toLowerCase()}`, symbol, operator_kind: kind, arity: parameterTypes.length,
    parameters: parameterTypes.map((allowed, index) => ({name: `arg${index + 1}`, allowed_concept_ids: Array.isArray(allowed) ? allowed : [allowed]})),
    return_concept_id: returnType,
    properties: {pure: mode !== "tool_binding", deterministic: mode !== "tool_binding", ...properties},
    evaluation: {mode, implementation: mode === "constructor" ? "identity" : (mode === "assertion_lookup" ? "knowledge_base_lookup" : symbol), open_world: true, missing_result: returnType === "concept_boolean" ? "Boolean_unknown" : "Unknown"}, source_kind: "human_defined"});
}

const C = {entity:"concept_entity",actor:"concept_actor",person:"concept_person",agent:"concept_agent",org:"concept_organization",artifact:"concept_artifact",project:"concept_project",document:"concept_document",directory:"concept_directory",path:"concept_path",software:"concept_software_project",dependency:"concept_dependency",formula:"concept_formula",dataframe:"concept_dataframe",column:"concept_column",message:"concept_message",email:"concept_email",product:"concept_product",order:"concept_order",tool:"concept_tool",method:"concept_method",evidence:"concept_evidence",activity:"concept_activity",event:"concept_event",task:"concept_task",action:"concept_action",plan:"concept_plan",meeting:"concept_meeting",goal:"concept_goal",requirement:"concept_requirement",strategy:"concept_strategy",option:"concept_option",topic:"concept_topic",claim:"concept_claim",issue:"concept_issue",value:"concept_value",status:"concept_status",role:"concept_role",parameter:"concept_parameter",theme:"concept_theme",platform:"concept_platform",stimulus:"concept_stimulus",flight:"concept_flight",payment:"concept_payment_method",will:"concept_will",child:"concept_child",turn:"concept_conversation_turn",type:"concept_type_descriptor",string:"concept_string",number:"concept_number",integer:"concept_integer",percentage:"concept_percentage",boolean:"concept_boolean",temporal:"concept_temporal",date:"concept_date",relativeDate:"concept_relative_date",dayOfMonth:"concept_day_of_month",dateRange:"concept_date_range",duration:"concept_duration",time:"concept_time",money:"concept_money",currency:"concept_currency",location:"concept_location",reason:"concept_reason",actionResult:"concept_action_result",tone:"concept_tone"};

for (const [symbol, params, result] of [["Directory",[C.string],C.directory],["Path",[C.string],C.path],["Location",[C.string],C.location],["Date",[C.string],C.date],["RelativeDate",[C.string],C.relativeDate],["DayOfMonth",[C.number],C.dayOfMonth],["DateRange",[[C.temporal],[C.temporal]],C.dateRange],["Duration",[C.string],C.duration],["Time",[C.string],C.time],["Currency",[C.string],C.currency],["Money",[C.number,C.currency],C.money],["Integer",[C.number],C.integer],["Percent",[C.number],C.percentage],["Status",[C.string],C.status],["Role",[C.string],C.role],["Text",[C.string],C.string],["Reason",[C.string],C.reason],["ActionResult",[C.string],C.actionResult],["Tone",[C.string],C.tone],["Type",[C.string],C.type]]) operator(symbol,"constructor",params,result,"constructor");
operator("current_dir","builtin",[],C.directory,"builtin");
const A=(...x)=>x, pred=(s,...p)=>operator(s,"predicate",p,C.boolean), fn=(s,p,r)=>operator(s,"function",p,r);
fn("directory_of",[A(C.project,C.document)],C.directory); pred("doc_of",C.project,C.document);
pred("requests",C.actor,A(C.action,C.plan,C.task,C.topic,C.goal));
fn("employer_of",[C.person],C.org); pred("needs_more_work",C.person); fn("planning_window_of",[C.event],C.duration); fn("duration_of",[A(C.event,C.plan)],C.duration);
pred("asks_about",C.actor,A(C.topic,C.claim)); pred("concerned_about",C.actor,C.topic); pred("recommends",C.agent,A(C.action,C.strategy)); pred("requires",A(C.action,C.plan,C.artifact,C.task,C.will),C.requirement);
fn("status_of",[C.entity],C.status); pred("considers",C.person,C.option); pred("chooses",C.person,A(C.option,C.flight)); fn("date_range_of",[C.event],C.dateRange); pred("plans",C.actor,C.plan); fn("role_of",[C.person],C.role);
fn("required_compile_sdk_of",[C.dependency],C.integer); fn("value_of",[C.parameter],C.value); fn("target_value_of",[A(C.parameter,C.goal)],C.value); fn("path_of",[C.document],C.path); pred("uses",A(C.plan,C.task),A(C.tool,C.method));
fn("error_of",[A(C.software,C.task)],C.issue); fn("text_of",[C.issue],C.string); pred("precedes",C.action,C.action); fn("channel_of",[C.plan],C.platform); fn("theme_of",[C.plan],C.theme); pred("includes_step",C.plan,C.action); pred("revises",C.plan,C.plan);
fn("step_count_of",[C.plan],C.integer); fn("source_tone_of",[C.stimulus],C.tone); fn("target_tone_of",[C.stimulus],C.tone); pred("changes",C.plan,C.parameter); pred("equal_spacing_of",C.plan); pred("available_in",C.tool,C.tool);
fn("goal_count_of",[C.plan],C.integer); pred("includes_goal",C.plan,C.goal); fn("deadline_of",[A(C.goal,C.will)],C.temporal); fn("template_of",[C.formula],C.string); fn("input_type_of",[C.formula],C.type); fn("output_type_of",[C.formula],C.type);
fn("argument_of",[C.action],C.string); fn("output_of",[A(C.action,C.task)],C.artifact); pred("applies_formula",C.dataframe,C.formula); fn("input_column_of",[C.dataframe],C.column); fn("output_column_of",[C.dataframe],C.column);
pred("supported_by",C.claim,C.evidence); pred("supports",A(C.strategy,C.method),C.goal); fn("origin_of",[C.flight],C.location); fn("destination_of",[C.flight],C.location); fn("trip_type_of",[C.flight],C.type); fn("departure_date_of",[C.flight],C.temporal); fn("return_date_of",[C.flight],C.temporal);
pred("prefers",C.person,C.option); pred("accepts",C.agent,C.requirement); fn("price_of",[C.flight],C.money); fn("stop_count_of",[C.flight],C.integer); fn("departure_time_of",[C.flight],C.time); fn("arrival_time_of",[C.flight],C.time); pred("offers",C.agent,C.flight); pred("is_nonstop",C.flight);
fn("delivery_channel_of",[C.message],C.email); pred("compatible_with",C.product,C.product); fn("order_of",[C.product],C.order); fn("refund_method_of",[C.action],C.payment); pred("confirms",C.person,C.action); fn("refund_amount_of",[C.action],C.money); pred("knows",C.person,C.topic); pred("item_in_recent_order",C.product);
fn("attribute_of",[C.product,C.string],C.value); fn("date_of",[A(C.event,C.meeting)],C.date); fn("location_of",[A(C.event,C.meeting)],C.location); pred("executor_of",C.person,C.will); pred("participant_of",C.person,C.meeting); fn("goal_of",[C.plan],C.goal); fn("anchor_date_of",[C.turn],C.date); pred("guardian_of",C.person,C.child); pred("affects",C.plan,C.plan);
operator("return_delivered_order_items","action",[C.order,C.product,C.payment],C.actionResult,"tool_binding",{transactional:true}); operator("cancel_pending_order","action",[C.order,C.reason],C.actionResult,"tool_binding",{transactional:true}); operator("get_order_details","action",[C.order],C.actionResult,"tool_binding");

const prefixConcept={Action:C.action,Agent:C.agent,App:C.software,Artifact:C.artifact,Boolean:C.boolean,Child:C.child,Claim:C.claim,Column:C.column,DataFrame:C.dataframe,Dep:C.dependency,Doc:C.document,Email:C.email,Event:C.event,Evidence:C.evidence,Flight:C.flight,Formula:C.formula,Goal:C.goal,Issue:C.issue,Meeting:C.meeting,Message:C.message,Method:C.method,Option:C.option,Order:C.order,Org:C.org,Param:C.parameter,Payment:C.payment,Person:C.person,Plan:C.plan,Platform:C.platform,Product:C.product,Proj:C.project,Req:C.requirement,Stimulus:C.stimulus,Strategy:C.strategy,Task:C.task,Theme:C.theme,Tool:C.tool,Topic:C.topic,Turn:C.turn,Type:C.type,Will:C.will};
const ontologyIndividuals=[{symbol:"Boolean_true",concept_ids:[C.boolean],metadata:{value:true}},{symbol:"Boolean_false",concept_ids:[C.boolean],metadata:{value:false}},{symbol:"Boolean_unknown",concept_ids:[C.boolean],metadata:{value:null,open_world:true}},{symbol:"Proj_解释器",concept_ids:[C.project],metadata:{seed_example:true}},{symbol:"Doc_设计文档_语义",concept_ids:[C.document],metadata:{seed_example:true}}].map(x=>({id:`individual_${x.symbol}`,display_name:x.symbol,aliases:[],...x}));
function walk(term,out){if(term.kind==="symbol")out.add(term.symbol);else if(term.kind==="call")for(const arg of term.args)walk(arg,out);}
const examples=["directory_of(Proj_解释器)=current_dir()","directory_of(Doc_设计文档_语义)=Directory(\"docs/specs/ke_semantics.md\")","doc_of(Proj_解释器,Doc_设计文档_语义)=Boolean_true"];
const allExpressions=[...slotExpressions.values()].flat(), symbols=new Set();
for(const expression of [...allExpressions,...examples]){const eq=parseEquation(expression);walk(eq.left,symbols);walk(eq.right,symbols);}
const seeded=new Set(ontologyIndividuals.map(x=>x.symbol)), extractionIndividuals=[];
for(const symbol of [...symbols].sort()){if(seeded.has(symbol))continue;const prefix=symbol.split("_")[0],conceptId=prefixConcept[prefix];if(!conceptId)throw new Error(`Symbol ${symbol} has no declared type prefix`);extractionIndividuals.push({id:`individual_${symbol}`,symbol,display_name:symbol.slice(prefix.length+1),concept_ids:[conceptId],aliases:[],evidence_ids:[],metadata:{declared_by:"typed_symbol_prefix",prefix}});}
const workflowRun={id:WORKFLOW_ID,workflow_name:"lossless_ke_extraction_v0_2",status:"succeeded",created_by:"codex_agent",model:MODEL,prompt_version:"ke_extract_v0.2",pipeline_version:"0.2.0",parameters:{source:"KE-test.json",information_loss_policy:"raw_plus_total_source_segmentation",operator_contract:"executable"}};
const ontology={schema_version:"ke_ontology_v0.2",ontology_id:ONTOLOGY_ID,name:"KE Memory Typed Executable Language",model:MODEL,grammar:{equation:"OperatorApplication = Term",term:"TypedIndividual | OperatorApplication | StringLiteral | NumberLiteral",individual_rule:"Every non-literal instance must be declared and type-prefixed.",open_world_boolean:"Missing predicate facts evaluate to Boolean_unknown, not Boolean_false."},concepts,operators,individuals:ontologyIndividuals,language_examples:examples,workflow_run:workflowRun};
const env=makeEnvironment(ontology,{individuals:extractionIndividuals});for(const expression of [...allExpressions,...examples])typeCheckEquation(parseEquation(expression),env);

function splitSource(text,prefix){const out=[];let start=0;for(let i=0;i<text.length;i+=1)if(/[。！？；!?\n]/u.test(text[i])){const end=i+1;out.push({id:`${prefix}_${out.length+1}`,start,end,quote:text.slice(start,end)});start=end;}if(start<text.length)out.push({id:`${prefix}_${out.length+1}`,start,end:text.length,quote:text.slice(start)});if(!out.length)out.push({id:`${prefix}_1`,start:0,end:text.length,quote:text});return out;}
function classify(text,speaker){if(/谢谢|感谢|不客气|旅途愉快/u.test(text))return"discourse";if(/\[工具调用\]/u.test(text))return"tool_trace";if(/吗|么|怎样|怎么|哪里|是否|能不能|有没有|请/u.test(text)&&speaker==="user")return"request_or_question";if(/建议|应该|可以|最好|需要/u.test(text)&&speaker==="agent")return"recommendation";return"assertion_or_state";}
const evidence=[],candidateResults=[];let factCount=0,keCount=0,factOnlyCount=0,segmentCount=0;
for(const candidate of sourceData.candidates){const turnResults=[];candidate.turns.forEach((turn,offset)=>{const turnIndex=offset+1,speakerResults=[];for(const [speaker,rawText] of [["user",turn.user],["agent",turn.agent]]){const key=`${candidate.id}|${turnIndex}|${speaker}`,expressions=slotExpressions.get(key)||[],prefix=`segment_${candidate.id.toLowerCase().replace(/[^a-z0-9]+/g,"_")}_${turnIndex}_${speaker}`,sourceSegments=splitSource(rawText,prefix),evidenceIds=[],facts=[];for(const segment of sourceSegments){const evidenceId=`evidence_${segment.id}`;evidence.push({id:evidenceId,evidence_type:"text_span",source_file:"KE-test.json",candidate_id:candidate.id,turn_index:turnIndex,speaker,span:{start:segment.start,end:segment.end},quote:segment.quote,metadata:{lossless:true}});evidenceIds.push(evidenceId);const factId=`fact_${segment.id}`;facts.push({id:factId,verbatim:segment.quote,source_span:{start:segment.start,end:segment.end},classification:classify(segment.quote,speaker),epistemic_status:speaker==="user"?"extracted":(rawText.includes("[工具结果]")?"tool_observed":"generated_unverified"),evidence_ids:[evidenceId],represented_by_ke_ids:[]});factCount+=1;segmentCount+=1;}
const kes=expressions.map((expression,index)=>{const equation=parseEquation(expression),types=typeCheckEquation(equation,env),id=`ke_${candidate.id.toLowerCase().replace(/[^a-z0-9]+/g,"_")}_${turnIndex}_${speaker}_${index+1}`;for(const fact of facts)fact.represented_by_ke_ids.push(id);keCount+=1;return{id,expression,canonical_expression:canonicalEquation(equation),ast:equation,lhs_type:types.left_type,rhs_type:types.right_type,status:speaker==="user"||rawText.includes("[工具结果]")?"active":"inferred",epistemic_status:speaker==="user"?"extracted":(rawText.includes("[工具结果]")?"tool_observed":"generated_unverified"),evidence_ids:evidenceIds,workflow_run_id:WORKFLOW_ID,metadata:{candidate_id:candidate.id,turn_index:turnIndex,speaker}};});
const factOnly=expressions.length?[]:facts.map(f=>({id:`fact_only_${f.id}`,fact_id:f.id,verbatim:f.verbatim,reason:f.classification==="discourse"?"discourse_not_knowledge_equation":"not_formalized_without_inventing_semantics",evidence_ids:f.evidence_ids}));factOnlyCount+=factOnly.length;speakerResults.push({speaker,raw_text:rawText,source_segments:sourceSegments,facts,kes,fact_only:factOnly,coverage:{source_length:rawText.length,covered_ranges:sourceSegments.map(({start,end})=>({start,end})),uncovered_ranges:[],raw_text_preserved:true}});}turnResults.push({turn_index:turnIndex,speaker_results:speakerResults});});candidateResults.push({candidate_id:candidate.id,source:candidate.source,turn_results:turnResults});}
const extraction={schema_version:"ke_extraction_v0.2",ontology_id:ONTOLOGY_ID,model:MODEL,workflow_run:workflowRun,individuals:extractionIndividuals,evidence,candidate_results:candidateResults,summary:{candidate_count:candidateResults.length,turn_count:candidateResults.reduce((n,c)=>n+c.turn_results.length,0),speaker_slot_count:candidateResults.reduce((n,c)=>n+c.turn_results.length*2,0),source_segment_count:segmentCount,fact_count:factCount,ke_count:keCount,fact_only_count:factOnlyCount,information_loss:{raw_text_preserved:true,uncovered_range_count:0}}};
const mode=process.argv[2]||"summary",ontologyText=JSON.stringify(ontology,null,2)+"\n",extractionText=JSON.stringify(extraction)+"\n";
if(mode==="ontology")process.stdout.write(ontologyText);else if(mode==="extraction")process.stdout.write(extractionText);else if(mode==="ke-text"){const lines=[];for(const candidate of candidateResults){lines.push(`对话id: ${candidate.candidate_id}`);let number=1;for(const turn of candidate.turn_results)for(const speaker of turn.speaker_results)for(const ke of speaker.kes)lines.push(`KE${number++}: ${ke.expression}`);lines.push("");}process.stdout.write(lines.join("\n").trimEnd()+"\n");}else console.log(JSON.stringify(extraction.summary));
