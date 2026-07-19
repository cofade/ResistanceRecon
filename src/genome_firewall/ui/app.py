"""Streamlit demo (issue #28): firewall rule table + evidence drill-down + calibration view
+ a non-dismissible lab-confirmation disclaimer banner on every render.

Calls service.analyze_genome in-process -- no FastAPI/HTTP hop for the UI (ADR-0022); the
standalone FastAPI app (api/main.py) wraps the same orchestrator as a separate deliverable
surface. Kept as a direct script (developing-with-streamlit best practice: page bodies are not
wrapped in a render function); shared logic lives in ui/render.py, which this is the only
module allowed to combine with the ``streamlit`` API itself.
"""

from __future__ import annotations

import streamlit as st

from genome_firewall.kb.embedder import HashingBagOfWordsEmbedder
from genome_firewall.kb.evidence_rag import EvidenceRAG
from genome_firewall.llm.factory import make_client
from genome_firewall.predictor.model_registry import PredictorRegistry
from genome_firewall.reader.fasta_parser import FastaParseError
from genome_firewall.service import (
    DEFAULT_MODELS_DIR,
    DEMO_FASTA_PATH,
    DEMO_GENOMES,
    Annotator,
    PipelineError,
    analyze_genome,
    default_annotator,
    materialize_upload,
    using_docker_annotator,
)
from genome_firewall.ui import render

st.set_page_config(page_title="Genome Firewall", page_icon="\U0001f9ec")


@st.cache_resource
def _load_registry() -> PredictorRegistry:
    return PredictorRegistry.load(DEFAULT_MODELS_DIR)


@st.cache_resource
def _load_retriever() -> EvidenceRAG:
    return EvidenceRAG.from_seed(embedder=HashingBagOfWordsEmbedder())


@st.cache_resource
def _load_annotator() -> Annotator:
    return default_annotator()


def _disclaimer_banner() -> None:
    """Rendered unconditionally, top and bottom of every run -- Streamlit reruns this whole
    script on every interaction, so there is no widget state that could suppress it and
    st.error carries no dismiss control: non-dismissible by construction (golden rule #4).
    """
    st.error(render.disclaimer_text(), icon=":material/warning:")


st.title("Genome Firewall")
st.caption("Per-antibiotic decision support for *Klebsiella pneumoniae* — not a diagnosis.")
_disclaimer_banner()

registry = _load_registry()
annotator = _load_annotator()
retriever = _load_retriever()
client = make_client()

st.session_state.setdefault("source_mode", "Bundled demo genome")

with st.sidebar:
    st.radio("Genome source", ["Bundled demo genome", "Upload FASTA"], key="source_mode")
    st.caption(
        "LLM narrative: "
        + ("enabled" if client is not None else "disabled (no API key) — deterministic template")
    )
    if not using_docker_annotator(annotator):
        st.caption("AMRFinderPlus: mock/offline (set GF_USE_DOCKER=1 for real Docker annotation)")

fasta_path = None
upload_bytes = None

if st.session_state.source_mode == "Bundled demo genome":
    genome_id = st.selectbox(
        "Demo genome",
        options=list(DEMO_GENOMES),
        format_func=lambda gid: f"{gid} — {DEMO_GENOMES[gid]}",
    )
    fasta_path = DEMO_FASTA_PATH
else:
    uploaded = st.file_uploader("Genome assembly FASTA", type=["fasta", "fna", "fa", "txt"])
    genome_id = st.text_input("Genome ID", value="uploaded-genome")
    if uploaded is not None:
        upload_bytes = uploaded.getvalue()
    if not using_docker_annotator(annotator):
        st.info(
            "Docker/AMRFinderPlus is not configured in this environment, so an uploaded genome "
            "can only be analyzed if its genome ID matches a bundled fixture. Try the bundled "
            "demo genome, or run with GF_USE_DOCKER=1 for real annotation.",
            icon=":material/info:",
        )

has_source = fasta_path is not None or upload_bytes is not None
run = st.button("Analyze", type="primary", disabled=not has_source)

if run and genome_id:
    envelope = None
    with st.spinner("Running the firewall pipeline..."):
        try:
            if upload_bytes is not None:
                with materialize_upload(upload_bytes) as tmp_path:
                    envelope = analyze_genome(
                        tmp_path,
                        genome_id=genome_id,
                        annotator=annotator,
                        registry=registry,
                        client=client,
                        retriever=retriever,
                    )
            elif fasta_path is not None:
                envelope = analyze_genome(
                    fasta_path,
                    genome_id=genome_id,
                    annotator=annotator,
                    registry=registry,
                    client=client,
                    retriever=retriever,
                )
        except FastaParseError as exc:
            st.error(f"Invalid FASTA: {exc}")
        except PipelineError as exc:
            st.error(f"Analysis failed: {exc}")

    if envelope is not None:
        report = envelope.report
        st.subheader(f"Firewall verdicts — {report.genome_id}")
        for row in render.firewall_rows(report):
            with st.container(border=True):
                st.markdown(
                    f"**{row.antibiotic}** — :{row.color}[{row.label}]  "
                    f"({row.confidence_pct}% confidence)"
                )
                caption = f"Evidence: {row.evidence_badge}"
                if row.conformal_labels:
                    caption += f" · Conformal set: {{{', '.join(row.conformal_labels)}}}"
                st.caption(caption)

        st.subheader("Evidence drill-down")
        for prediction in report.predictions:
            title = (
                f"{prediction.antibiotic} — {render.evidence_badge(prediction.evidence_category)}"
            )
            with st.expander(title):
                lines = render.evidence_lines(prediction)
                if lines:
                    for line in lines:
                        st.markdown(f"- {line}")
                else:
                    st.caption("No supporting evidence recorded.")

        st.subheader("Narrative")
        st.write(report.narrative_summary)
        st.caption(f"Source: {envelope.source} · Review status: {envelope.review_status}")

        st.subheader("Calibration")
        st.caption(
            "Per-drug calibrated confidence and conformal prediction set above; see GET "
            "/model-card (or the committed per-drug model_card.md files) for full reliability "
            "curves and held-out metrics."
        )

    _disclaimer_banner()
