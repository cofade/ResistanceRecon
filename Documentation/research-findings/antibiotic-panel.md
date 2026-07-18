# Antibiotic Panel & Gene→Target Mapping (K. pneumoniae)

*Transcribed from the 2026-07-18 Genome Firewall design workflow (research agent R4). Web-grounded; sources below. Prevalence percentages are illustrative cohort findings, not universal constants.*

## Recommended panel

| Antibiotic | Include? | Molecular target | Key evidence genes/mutations | Genotype→phenotype strength |
|---|---|---|---|---|
| Meropenem | Include — antibiotic #1, highest priority | Penicillin-binding proteins (PBPs) — transpeptidases in peptidoglycan synthesis | blaKPC (KPC-2/3 most common), blaNDM (NDM-1/5), blaOXA-48-like (OXA-48/181/232) carbapenemases; secondary/no-call-inducing: ESBL/AmpC + ompK35/ompK36 porin loss or truncation; OXA-48 plasmid copy-number effects | VERY STRONG when a carbapenemase gene is present (near 100% specificity for resistance); a carbapenemase-negative genotype does NOT guarantee susceptibility (porin-loss route) — flag for lower confidence / NO-CALL |
| Ceftriaxone | Include — antibiotic #2 | PBPs (transpeptidases) | blaCTX-M family (CTX-M-15 dominant globally, also CTX-M-14/27 etc.), plus blaSHV extended-spectrum variants and blaTEM ESBL variants (distinguished from chromosomal non-ESBL blaSHV-1) | STRONG for calling resistance (high specificity, ~99%) but can UNDER-call resistance (moderate sensitivity, ~44% in one cohort) due to AmpC hyperproduction, porin loss, promoter effects |
| Ciprofloxacin | Include — antibiotic #3 | DNA gyrase (GyrA/GyrB) and topoisomerase IV (ParC/ParE) | QRDR point mutations in gyrA (e.g. S83/D87) and parC (e.g. S80/E84); acquired PMQR genes qnrA/B/S, aac(6')-Ib-cr, and qepA/oqxAB efflux | MODERATE: single QRDR mutation or single PMQR gene often only reduced susceptibility; COMBINATIONS (multiple QRDR mutations + PMQR) reliably produce high-level resistance — needs mutation-count/combination features |
| Gentamicin | Include — antibiotic #4 | 30S ribosomal subunit / 16S rRNA (protein synthesis initiation) | Aminoglycoside-modifying enzymes aac(3)-I/II, aac(6')-Ib, aph(3')-VI, ant(2'')-Ia (drug-specific substrate ranges); 16S rRNA methyltransferases armA/rmtB/rmtC/rmtD (near-universal high-level pan-aminoglycoside resistance) | WELL-predicted for the 16S-RMTase route (deterministic, near-binary); only MODERATE for AME-only genotypes (drug- and dose-specific effect size, frequent AME co-occurrence) |
| Trimethoprim-sulfamethoxazole | Include — antibiotic #5 | Dihydropteroate synthase (sulfamethoxazole component, folate synthesis) and dihydrofolate reductase (trimethoprim component) | sul1/sul2 (target-bypass dihydropteroate synthase, ~78-86% of resistant isolates) and dfrA gene family (dfrA1/dfrA4/dfrA5/dfrA7/dfrA12/dfrA14/dfrA15/dfrA17/dfrA27/dfrA30 etc.), often co-located on class-1 integrons | VERY STRONG — among the best-performing antibiotics in published ML benchmarks (~0.98 accuracy); clean target-bypass mechanisms; best positive-control drug |
| Ampicillin/amoxicillin | EXCLUDE / intrinsic — treat as a fixed intrinsic-resistance flag only, not a model target | Chromosomal SHV-1 (or LEN-1) class A beta-lactamase (intrinsic) | Chromosomal blaSHV-1/LEN-1 (fixed intrinsic-resistance flag, not a model feature) | N/A — essentially all isolates resistant regardless of accessory genotype; EUCAST Expert Rules discourage reporting ampicillin as susceptible for Klebsiella spp.; no discriminative ML signal |
| Colistin/polymyxin B | Stretch goal — documented as a stretch-goal/follow-up antibiotic, not part of the core 5-drug panel | Lipid A of lipopolysaccharide (outer membrane) | mgrB inactivation, pmrAB/phoPQ regulatory mutations, mcr plasmid genes | WEAKER / less complete: rule-based known-variant detection AUROC 0.791 vs whole-genome ML AUROC 0.894 (p=0.006); prone to heteroresistance; higher NO-CALL rate |

## Per-antibiotic detail

### Meropenem (representative carbapenem; imipenem as optional secondary label if data allows)

**Decision:** Include as antibiotic #1 — highest priority

**Choice:** Meropenem (representative carbapenem; imipenem as optional secondary label if data allows)

**Rationale:** MOLECULAR TARGET: penicillin-binding proteins (PBPs) — transpeptidases in peptidoglycan synthesis. KEY EVIDENCE GENES (deterministic layer): blaKPC (KPC-2/3 most common), blaNDM (NDM-1/5), blaOXA-48-like (OXA-48/181/232) carbapenemases — acquired, plasmid-borne, near-binary strong predictors when present. SECONDARY/NO-CALL-INDUCING mechanisms: ESBL/AmpC + ompK35/ompK36 porin loss or truncation (non-carbapenemase-producing CR-Kp), OXA-48 plasmid copy-number effects. Genotype predicts phenotype VERY STRONGLY when a carbapenemase gene is present (near 100% specificity for resistance) but a carbapenemase-negative genotype does NOT guarantee susceptibility (porin-loss route) — flag these cases for lower confidence / NO-CALL rather than a confident LIKELY-TO-WORK call. Clinically this is the single most important resistance call (last-line agent). No intrinsic-resistance issue for K. pneumoniae.

### Ceftriaxone (representative 3rd-gen cephalosporin; cefotaxime as a near-equivalent alternative)

**Decision:** Include as antibiotic #2

**Choice:** Ceftriaxone (representative 3rd-gen cephalosporin; cefotaxime as a near-equivalent alternative)

**Rationale:** MOLECULAR TARGET: PBPs (transpeptidases). KEY EVIDENCE GENES: blaCTX-M family (CTX-M-15 dominant globally, also CTX-M-14/27 etc.), plus blaSHV extended-spectrum variants and blaTEM ESBL variants (as distinguished from the chromosomal non-ESBL blaSHV-1). Genotype predicts phenotype STRONGLY for calling resistance (high specificity, ~99%) but can UNDER-call resistance (moderate sensitivity, ~44% in one cohort) because AmpC hyperproduction, porin loss, and promoter effects also drive resistance without an ESBL gene — justifies conformal NO-CALL when no ESBL/AmpC gene is found but other risk signals are ambiguous. No intrinsic-resistance caveat (unlike ampicillin).

### Ciprofloxacin (representative fluoroquinolone)

**Decision:** Include as antibiotic #3

**Choice:** Ciprofloxacin (representative fluoroquinolone)

**Rationale:** MOLECULAR TARGET: DNA gyrase (GyrA/GyrB) and topoisomerase IV (ParC/ParE). KEY EVIDENCE: QRDR point mutations in gyrA (most common, e.g. S83/D87) and parC (e.g. S80/E84) — AMRFinderPlus supports Klebsiella-specific point-mutation calling for these; plus acquired PMQR genes qnrA/B/S, aac(6')-Ib-cr, and qepA/oqxAB efflux. Genotype predicts phenotype MODERATELY: single QRDR mutations or a single PMQR gene often produce only reduced susceptibility, while COMBINATIONS (multiple QRDR mutations + PMQR) reliably produce high-level resistance — model should encode mutation counts/combinations as features rather than a single binary gene call, and should have wider uncertainty bands / more frequent NO-CALL than carbapenems or TMP-SMX.

### Gentamicin (representative aminoglycoside; amikacin as documented follow-on given differing AME substrate profile)

**Decision:** Include as antibiotic #4

**Choice:** Gentamicin (representative aminoglycoside; amikacin as documented follow-on given differing AME substrate profile)

**Rationale:** MOLECULAR TARGET: 30S ribosomal subunit / 16S rRNA (protein synthesis initiation). KEY EVIDENCE GENES: aminoglycoside-modifying enzymes aac(3)-I/II, aac(6')-Ib, aph(3')-VI, ant(2'')-Ia (drug-specific substrate ranges — must be mapped per antibiotic, e.g. aac(6')-Ib affects amikacin/tobramycin more than gentamicin) and 16S rRNA methyltransferases armA/rmtB/rmtC/rmtD (near-universal high-level pan-aminoglycoside resistance when present, strongest single predictor). Genotype predicts phenotype WELL for the 16S-RMTase route (deterministic, near-binary) but only MODERATELY for AME-only genotypes because effect size is drug- and dose-specific and multiple AMEs often co-occur — justify NO-CALL when only weak/uncertain AMEs are present without an RMTase.

### Trimethoprim-sulfamethoxazole (co-trimoxazole)

**Decision:** Include as antibiotic #5

**Choice:** Trimethoprim-sulfamethoxazole (co-trimoxazole)

**Rationale:** MOLECULAR TARGET: dihydropteroate synthase (sulfamethoxazole component, folate synthesis) and dihydrofolate reductase (trimethoprim component). KEY EVIDENCE GENES: sul1/sul2 (target-bypass dihydropteroate synthase, ~78-86% of resistant isolates) and dfrA gene family (target-bypass dihydrofolate reductase; dfrA1/dfrA4/dfrA5/dfrA7/dfrA12/dfrA14/dfrA15/dfrA17/dfrA27/dfrA30 etc.), often co-located on class-1 integrons. Genotype predicts phenotype VERY STRONGLY — among the best-performing antibiotics in published ML benchmarks (~0.98 accuracy) and both resistance genes act via clean target bypass, making this class the most reliable positive-control drug for validating the whole pipeline before trusting harder classes like fluoroquinolones/aminoglycosides. No intrinsic-resistance caveat.

### Ampicillin/amoxicillin

**Decision:** EXCLUDE from the core predictive panel; treat as a fixed intrinsic-resistance flag only, not a model target

**Choice:** Ampicillin/amoxicillin

**Rationale:** K. pneumoniae carries a chromosomal SHV-1 (or LEN-1) class A beta-lactamase and is intrinsically/"expected" resistant per EUCAST Expert Rules, which explicitly discourage reporting ampicillin as susceptible for Klebsiella spp. Almost all isolates will be labeled resistant regardless of accessory genotype, so there is no useful discriminative signal for an ML classifier — but the system should still emit a deterministic "intrinsic resistance, do not test" style note if a user asks about it, consistent with the project's target-presence gate design.

### Colistin/polymyxin B

**Decision:** Documented as a stretch-goal / follow-up antibiotic, not part of the core 5-drug panel

**Choice:** Colistin/polymyxin B

**Rationale:** Resistance mechanisms (mgrB inactivation, pmrAB/phoPQ regulatory mutations, mcr plasmid genes) are less completely characterized than the core panel's mechanisms; a peer-reviewed benchmark found genotype-based rule detection (AUROC 0.791) meaningfully underperforms whole-genome ML (AUROC 0.894) for this drug in K. pneumoniae, and colistin resistance is also prone to heteroresistance — all of which make it a higher-NO-CALL-rate, harder target better suited to a documented follow-up phase than the 24-hour build.

## Key findings

- AMRFinderPlus (NCBI) natively detects the acquired beta-lactamase, quinolone, aminoglycoside, sulfonamide/trimethoprim, phenicol, macrolide and tetracycline gene families needed for this panel, and Klebsiella pneumoniae is one of its curated '--organism' options, which enables point-mutation calling (gyrA/parC QRDR) in addition to acquired-gene presence/absence — this is the deterministic 'known-mechanism' evidence layer the project wants (github.com/ncbi/amr).
- Carbapenem resistance in K. pneumoniae is dominated by three carbapenemase families with very high prevalence and strong genotype→phenotype linkage: blaNDM (~55% of carbapenem-resistant isolates in one large series), blaOXA-48-like (~44%), blaKPC (~15%); at least one of these genes was found in ~90% of carbapenem-resistant isolates, with ~25% dual-carriage (mainly NDM+OXA-48-like). This makes meropenem/imipenem the single strongest label+mechanism combination for the panel.
- 3rd-gen cephalosporin (ceftriaxone/cefotaxime) resistance is dominated by blaCTX-M ESBLs. In one bloodstream-infection cohort, cephalosporin genotype-phenotype agreement was 92.6% (specificity 99.2%, sensitivity only 43.75%) using ESBL-gene presence as the resistance rule — genotype rarely false-flags resistance but can miss resistant isolates driven by other/combined mechanisms (AmpC hyperproduction, porin loss, promoter mutations). Nearly all ceftriaxone-resistant isolates in that cohort carried blaCTX-M-15. Most CTX-M variants hydrolyze ceftriaxone/cefotaxime strongly but not always ceftazidime (CTX-M-15/16/19 are exceptions with enhanced ceftazidime activity).
- K. pneumoniae is intrinsically ('expected') resistant to ampicillin/amoxicillin via its chromosomal SHV-1 (or LEN-1) class A beta-lactamase; EUCAST Expert Rules state phenotypic ampicillin/amoxicillin susceptibility should not be reported for Klebsiella spp. — any target-presence gate must special-case this as a fixed intrinsic-resistance call, not a learned prediction, and ampicillin should be EXCLUDED from the ML panel because it carries essentially no discriminative label signal.
- Fluoroquinolone (ciprofloxacin) resistance is multifactorial: QRDR mutations in gyrA (~85% of resistant isolates in one series) and parC (~80%), plus plasmid-mediated quinolone resistance (PMQR) genes qnrB/qnrS/qnrA, aac(6')-Ib-cr (an AME variant that also acetylates ciprofloxacin), and qepA efflux. Co-occurrence of QRDR mutations with PMQR genes reached 68.5% in one cohort and increases resistance level — meaning a simple single-gene rule under-predicts; the ML model needs mutation-count/combination features, not just presence/absence of one gene.
- Aminoglycoside (gentamicin/amikacin) resistance genotype-phenotype linkage is heterogeneous and dose/enzyme-substrate specific: many aminoglycoside-modifying enzymes (AMEs: aac(3), aac(6')-Ib, aph(3'), ant(2'')/ant(3'')) confer variable-level, drug-specific resistance (e.g., aac(6')-Ib does not affect gentamicin the way it affects amikacin/tobramycin), whereas acquired 16S rRNA methyltransferases (armA, rmtB/C/D) confer very-high-level, pan-aminoglycoside resistance and are the strongest single predictors when present. One study found rmtB dominant (70%) among high-level-resistant strains. AME gene panels have been shown to be predictive of aminoglycoside MICs in carbapenem-resistant K. pneumoniae, but drug-specific substrate profiles must be encoded correctly per antibiotic.
- Trimethoprim-sulfamethoxazole resistance is well explained by acquired genes: sul1/sul2 (dihydropteroate synthase bypass, ~78-86% prevalence among resistant isolates in surveys) and dfrA gene family variants (dfrA1, dfrA4, dfrA5/7/12/14/15/17/27/30 etc., dihydrofolate reductase bypass), frequently carried together on class 1 integrons (found in ~63% of TMP-SMX-resistant isolates in one study). This is one of the most genotype-predictable classes, and a 2024 ML benchmark on K. pneumoniae genomic data achieved 0.980 accuracy for SXT, among the best-performing antibiotics.
- Porin loss (ompK35/ompK36 inactivation via frameshift, insertion sequence disruption, promoter mutation, or the ST258-associated Gly115-Asp116 loop-3 insertion in OmpK36) combined with ESBL/AmpC production is a well-documented cause of carbapenem resistance WITHOUT a carbapenemase gene, and is a major source of genotype-phenotype discordance because simple presence/absence gene calls miss promoter mutations, small indels causing early truncation, and IS-element disruptions unless the annotation pipeline specifically screens porin gene integrity. Increased blaOXA-48 plasmid copy number combined with OmpK36 loss has also been shown to drive high carbapenem MICs independent of new gene acquisition — a copy-number/expression effect invisible to binary gene-presence features.
- Efflux overexpression (acrAB-tolC upregulation via regulatory mutations in ramA, ramR, marA, soxS, or acquired oqxAB) and gene expression-level effects (promoter mutations altering blaSHV or other beta-lactamase expression) are additional mechanisms that decouple genotype (gene present) from phenotype (actual MIC), and there is no simple presence/absence feature that reliably captures them without deeper regulatory-variant or expression modeling — a legitimate justification for a calibrated NO-CALL / conformal-abstention decision rather than a forced call.
- Colistin/polymyxin resistance is the clearest published example that whole-genome, ML-based (reference-free) approaches can materially outperform rule-based known-gene-only approaches in K. pneumoniae: an mSystems study on >600 CG258 genomes found AUROC 0.894 for an ML/k-mer approach vs 0.791 for a rule-based known-variant detector (p=0.006), attributed to incomplete characterization of polymyxin-resistance mechanisms (mgrB inactivation, pmrAB/phoPQ mutations) and likely polygenic effects — directly supports the project's decision to pair a deterministic evidence layer with a learned classifier plus abstention, and is a caution against relying only on 'known mechanism' features for colistin specifically (colistin itself is a reasonable stretch-goal antibiotic but riskier for the core panel given its documented heteroresistance and higher NO-CALL rate).
- BV-BRC/PATRIC is a viable self-sourced label source: genome-level AMR phenotype metadata (Resistant/Susceptible/Intermediate) is ingested from NCBI BioSample/antibiogram records plus curated genomic-surveillance-center submissions; one recent K. pneumoniae study pulled 18,645 BV-BRC genomes and found AMR phenotype data for 76 antibiotics across 4,976 of those genomes (15 antibiotic classes) — confirms adequate label volume exists for the 5-drug panel, though per-antibiotic label counts will vary and should be checked directly (carbapenems, 3GCs, and TMP-SMX are typically among the best-populated in BV-BRC/NCBI Pathogen Detection).
- A 2024 ML benchmark on genomic features for K. pneumoniae resistance found accuracy >0.97 for aztreonam, ceftazidime, colistin, and trimethoprim-sulfamethoxazole, but only 0.68-0.83 for fosfomycin, illustrating that genotype-based predictability varies sharply by drug even within one modeling pipeline — useful as an expectation-setting prior for which of the recommended panel drugs should calibrate more confidently (TMP-SMX, cephalosporins, carbapenems via carbapenemases) vs. which need wider abstention bands (fluoroquinolones, aminoglycosides).

## Known-mechanism evidence gene groups

Suggested evidence-layer gene groups to hardcode as "known-mechanism" features per drug (transcribed exactly as recommended):

```
MEROPENEM      = { blaKPC*, blaNDM*, blaOXA-48-like, ompK35, ompK36 }
CEFTRIAXONE    = { blaCTX-M*, blaSHV (ESBL variants), blaTEM (ESBL variants), blaCMY/AmpC }
CIPROFLOXACIN  = { gyrA QRDR mutation, parC QRDR mutation, qnrA/B/S, aac(6')-Ib-cr, oqxAB, qepA }
GENTAMICIN     = { aac(3)-I/II, aac(6')-Ib, aph(3')-VI, ant(2'')-Ia, armA, rmtB/C/D }
TMP-SMX        = { sul1, sul2, dfrA* }
AMPICILLIN     = { blaSHV-1/LEN-1 chromosomal -- fixed intrinsic-resistance flag, not a model feature }
```

Reference AMRFinderPlus (Docker/WSL2) invocation for the annotation layer:

```
docker run --rm -v ${PWD}:/data ncbi/amr amrfinder -p /data/protein.faa -n /data/assembly.fasta --organism Klebsiella_pneumoniae --plus -o /data/amr_results.tsv
```

## Recommendations

- Final recommended panel (5 antibiotics): meropenem, ceftriaxone, ciprofloxacin, gentamicin, trimethoprim-sulfamethoxazole — this set spans 5 distinct target classes/mechanism families, has among the best documented genotype-phenotype concordance in the literature, and BV-BRC/NCBI Pathogen Detection label coverage should be adequate (verify per-drug label counts directly against your pulled genome set before finalizing).
- Order model confidence expectations from most to least genotype-predictable based on the literature reviewed: trimethoprim-sulfamethoxazole and meropenem (carbapenemase-positive cases) as your most reliable "positive control" classes, ceftriaxone next (high specificity, moderate sensitivity), then gentamicin and ciprofloxacin as your hardest classes needing wider conformal intervals / higher NO-CALL rates.
- Build ampicillin/amoxicillin handling as a hard-coded intrinsic-resistance rule (chromosomal SHV-1/LEN-1), separate from the learned panel, and surface it in the report UI as an example of "expected resistance" distinct from acquired/predicted resistance — good for demo narrative credibility.
- For the deterministic "known-mechanism" evidence layer, use AMRFinderPlus with --organism Klebsiella_pneumoniae so that gyrA/parC point mutations are called in addition to acquired-gene presence/absence; without the organism flag you will silently lose the fluoroquinolone point-mutation signal.
- Explicitly engineer combination/count features for fluoroquinolones (number of QRDR mutations + PMQR gene presence) and aminoglycosides (RMTase presence as a dominant feature, AME identity as secondary, drug-specific substrate mapping) rather than flat one-hot gene presence, since the literature shows these classes are driven by combinatorial/co-occurrence effects.
- For the report's honest-limitations language, explicitly name porin loss (ompK35/ompK36), efflux overexpression (acrAB-tolC via ramA/ramR/marA), gene-copy-number/expression effects, and heteroresistance as mechanisms that justify NO-CALL — these are well documented and give the report genuine defensibility rather than a generic disclaimer.
- Keep the "confirm with standard lab testing" line especially prominent for cephalosporin and fluoroquinolone calls, given their comparatively lower sensitivity/moderate concordance versus carbapenems and TMP-SMX.

## Risks & to-validate

- No K. pneumoniae-specific AMRFinderPlus validation study with published per-class concordance/sensitivity/specificity was found in this search (the main published AAC validation paper, Feldgarden et al. 2019, validated on Salmonella/Campylobacter/E. coli, not Klebsiella) — you should run your own genotype-phenotype concordance check on your pulled BV-BRC K. pneumoniae dataset rather than assuming AMRFinderPlus performance transfers directly; treat this as a to-validate item, not an established fact.
- Cephalosporin genotype-phenotype sensitivity (~44% in the one cohort found) is markedly lower than specificity, meaning a rule using ESBL-gene-presence alone will systematically under-call resistance — if the ML layer inherits this bias without correction it could produce falsely reassuring LIKELY-TO-WORK calls for ceftriaxone; calibration must be checked per-class, not assumed uniform.
- Aminoglycoside AME-to-drug substrate mapping is genuinely complex (enzyme-specific spectra differ for gentamicin vs amikacin vs tobramycin) — using a single generic "aminoglycoside resistance gene present" feature without drug-specific mapping will produce misleading confidence for gentamicin specifically; this needs a small curated substrate-mapping table (CARD's aro ontology has this) rather than being inferred from search snippets alone.
- BV-BRC label volume and class balance per antibiotic (esp. gentamicin and ciprofloxacin, vs. the better-populated carbapenems/cephalosporins) was not directly verified in this session — confirm actual per-drug R/S/I counts in your specific pulled K. pneumoniae genome set before committing the final 5-drug panel, since a thin or class-imbalanced label set for one drug could force it out of the panel late.
- Search-derived prevalence and concordance percentages come from individual regional/cohort studies (Jordan, Iran, China, Egypt, Thailand etc.) with small-to-moderate sample sizes and should be treated as illustrative ranges, not universal constants — do not hardcode these exact percentages into the report UI as if globally authoritative; cite them as example findings from the literature.

## Sources

- https://github.com/ncbi/amr
- https://www.ncbi.nlm.nih.gov/pathogens/antimicrobial-resistance/AMRFinder/
- https://journals.asm.org/doi/10.1128/aac.00483-19
- https://www.nature.com/articles/s41598-021-91456-0
- https://www.nature.com/articles/s41467-024-51374-x
- https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9045624/
- https://www.sciencedirect.com/science/article/pii/S1018364724001459
- https://pmc.ncbi.nlm.nih.gov/articles/PMC11256406/
- https://pmc.ncbi.nlm.nih.gov/articles/PMC7886241/
- https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4216573/
- https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8173869/
- https://pmc.ncbi.nlm.nih.gov/articles/PMC10757003/
- https://www.frontiersin.org/journals/microbiology/articles/10.3389/fmicb.2021.636396/full
- https://pmc.ncbi.nlm.nih.gov/articles/PMC9097246/
- https://doi.org/10.3390/microorganisms14020463
- https://www.sciencedirect.com/science/article/abs/pii/S0924857918300980
- https://www.nature.com/articles/s41467-019-11756-y
- https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12217476/
- https://pubmed.ncbi.nlm.nih.gov/17276039/
- https://www.mdpi.com/2079-6382/15/1/37
- https://www.frontiersin.org/journals/microbiology/articles/10.3389/fmicb.2025.1676614/full
- https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5289562/
- https://www.bv-brc.org/docs/quick_references/organisms_taxon/antimicrobial_resistance.html
- https://www.bv-brc.org/docs/system_documentation/data.html
- https://www.biorxiv.org/content/10.1101/2025.04.08.647753.full.pdf
- https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7253370/
- https://msystems.asm.org/content/5/3/e00656-19
- https://pmc.ncbi.nlm.nih.gov/articles/PMC11410219/
- https://www.biorxiv.org/content/10.1101/2024.12.10.627815v1.full
