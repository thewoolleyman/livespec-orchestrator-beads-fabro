// Enemy-unit probe: link against Fabro's actual workflow/graphviz crates.
// argv[1] is the shipped workflow.fabro; no imitation preamble builder lives here.
use fabro_graphviz::{parser::parse, Fidelity};
use fabro_workflow::handler::llm::preamble::build_preamble;
use fabro_workflow::{
    context::{keys, Context},
    outcome::{Outcome, OutcomeExt},
};
use std::collections::HashMap;

fn main() {
    let graph_path = std::env::args().nth(1).expect("workflow.fabro path");
    let graph = parse(&std::fs::read_to_string(graph_path).unwrap()).unwrap();
    let fidelity: Fidelity = graph.nodes["fix"]
        .attrs
        .get("fidelity")
        .and_then(|v| v.as_str())
        .unwrap_or("compact")
        .parse()
        .unwrap();
    for source in ["proof_capture", "proof_verify"] {
        let finding = format!("{source}: assertion 1; reproduce unsorted item IDs [z,a]; expected rejection, observed acceptance");
        let context = Context::new();
        let mut proof = Outcome::success();
        proof
            .context_updates
            .insert(keys::response_key(source), finding.clone().into());
        let mut janitor = Outcome::success();
        janitor
            .context_updates
            .insert(keys::COMMAND_OUTPUT.into(), "All checks passed".into());
        let outcomes = HashMap::from([("janitor".into(), janitor), (source.into(), proof)]);
        let completed = vec!["janitor".into(), source.into()];
        let rendered = build_preamble(fidelity, &context, &graph, &completed, &outcomes);
        assert!(
            rendered.contains(&finding),
            "{source} finding was lost: {rendered}"
        );
        assert!(rendered.contains(&format!("## Stage: {source}")));
        let compact = build_preamble(Fidelity::Compact, &context, &graph, &completed, &outcomes);
        assert!(
            !compact.contains(&finding),
            "negative control did not reproduce loss"
        );
        println!(
            "PASS: green janitor + {source} preserves exact finding; compact control loses it"
        );
    }
    let context = Context::new();
    let failure = "FAILED test_metadata_order: expected sorted IDs";
    let mut janitor = Outcome::fail_deterministic(failure);
    janitor
        .context_updates
        .insert(keys::COMMAND_OUTPUT.into(), failure.into());
    let outcomes = HashMap::from([("janitor".into(), janitor)]);
    let rendered = build_preamble(fidelity, &context, &graph, &["janitor".into()], &outcomes);
    assert!(rendered.contains(failure));
    println!("PASS: red janitor failure output remains actionable");
}
