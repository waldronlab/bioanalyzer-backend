# Search recall

Results: 100 papers; ground truth: 100 papers.
A paper counts if ANY curated ID is found. Denominator: ground-truth papers with a curated value for the field (papers missing from the results count as misses). `all` = papers curated for all three fields, found on all three.
Host species ground truth is labels only: labels are mapped to NCBITaxon with normalize_host_species, label match is a fallback (0 curated host label(s) did not resolve).
Papers whose results lack a `tags` key (primary used as the only tag): 0.

| field | n | top1 | tags exact | tags hierarchy |
|---|---|---|---|---|
| condition | 100 | 0.620 | 0.660 | 0.700 |
| body_site | 100 | 0.810 | 0.840 | 0.840 |
| host_species | 100 | 0.970 | 0.990 | 0.990 |
| all | 100 | 0.500 | 0.570 | 0.600 |
