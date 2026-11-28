# Search recall

Results: 100 papers; ground truth: 100 papers.
A paper counts if ANY curated ID is found. Denominator: ground-truth papers with a curated value for the field (papers missing from the results count as misses). `all` = papers curated for all three fields, found on all three.
Host species ground truth is labels only: labels are mapped to NCBITaxon with normalize_host_species, label match is a fallback (0 curated host label(s) did not resolve).
Papers whose results lack a `tags` key (primary used as the only tag): 0.

| field | n | top1 | tags exact | tags hierarchy |
|---|---|---|---|---|
| condition | 100 | 0.630 | 0.650 | 0.690 |
| body_site | 100 | 0.770 | 0.790 | 0.800 |
| host_species | 100 | 0.960 | 0.980 | 0.980 |
| all | 100 | 0.470 | 0.510 | 0.530 |
