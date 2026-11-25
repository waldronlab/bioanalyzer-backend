# Search recall, 3 repeats per set (commit fb727b5)

Mean (min-max) over 3 runs. top1 = primary value only; tags = any tag by ID/label; hierarchy = any tag whose ontology ancestors include the curated ID.

## fresh (100 papers)

| field | top1 | tags exact | tags hierarchy |
|---|---|---|---|
| condition | 0.62 (0.60-0.63) | 0.64 (0.62-0.65) | 0.68 (0.66-0.69) |
| body_site | 0.76 (0.75-0.77) | 0.78 (0.77-0.79) | 0.79 (0.77-0.80) |
| host_species | 0.96 (0.96-0.97) | 0.98 (0.98-0.99) | 0.98 (0.98-0.99) |
| all | 0.45 (0.44-0.47) | 0.49 (0.48-0.51) | 0.51 (0.50-0.53) |

## original (100 papers)

| field | top1 | tags exact | tags hierarchy |
|---|---|---|---|
| condition | 0.63 (0.62-0.63) | 0.67 (0.66-0.68) | 0.71 (0.70-0.72) |
| body_site | 0.81 (0.81-0.81) | 0.84 (0.84-0.84) | 0.84 (0.84-0.84) |
| host_species | 0.97 (0.97-0.97) | 0.99 (0.99-0.99) | 0.99 (0.99-0.99) |
| all | 0.51 (0.50-0.51) | 0.58 (0.57-0.58) | 0.60 (0.60-0.61) |

