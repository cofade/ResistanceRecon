# 12. Glossary

| Term | Meaning |
|---|---|
| **AMR** | Antimicrobial resistance. |
| **AST** | Antimicrobial susceptibility testing (the wet-lab measurement of R/S/I). |
| **SIR** | Susceptible / Intermediate / Resistant phenotype classification. |
| **AMRFinderPlus** | NCBI tool detecting known AMR genes + resistance-associated point mutations. |
| **BV-BRC** | Bacterial and Viral Bioinformatics Resource Center (formerly PATRIC); our data source. |
| **Calibration** | Making predicted probabilities match observed frequencies (here: sigmoid/Platt). |
| **Conformal prediction** | Method producing prediction *sets* with a coverage guarantee; basis of the no-call. |
| **No-call** | Deliberate abstention when evidence is weak, conflicting (`{S,R}`), or novel/OOD (`{}`). |
| **Evidence category** | `known_mechanism` (deterministic gene/mutation hit) vs `statistical_association` (model/SHAP) vs `no_signal`. |
| **Molecular-target gate** | Deterministic override: a known resistance mechanism, or absence of the drug's target, decides the verdict without the model. |
| **Homology-aware grouped split** | Train/test split that keeps near-identical (clonal) genomes on one side. |
| **MLST / ST** | Multi-locus sequence typing / sequence type — the epidemiological grouping key. |
| **Mash / ANI** | MinHash genome distance / Average Nucleotide Identity — clustering fallback (@ 99.5%). |
| **QRDR** | Quinolone-resistance-determining region (gyrA/parC mutations). |
| **ESBL / carbapenemase** | Extended-spectrum β-lactamase / carbapenem-hydrolyzing enzyme (e.g. blaCTX-M / blaKPC, blaNDM, blaOXA-48). |
| **Brier score** | Mean squared error of probabilistic predictions (calibration quality). |
| **Evidence RAG** | Retrieval-augmented generation over the AMR-mechanism KB for cited context (retrieval-only). |
