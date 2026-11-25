"""Search-recall chart: main value only vs tags incl. parent terms, mean of 3 runs."""
import json
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

data = json.load(sys.stdin)  # {set: {field: {"top1": [..3], "hier": [..3]}}}
FIELDS = [("condition", "Condition"), ("body_site", "Body site"),
          ("host_species", "Host species"), ("all", "All three")]
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
S1, S2 = "#2a78d6", "#eb6834"  # reference palette slots 1-2 (validated pair)

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), sharey=True, facecolor=SURFACE)
w = 0.36
for ax, (setname, title) in zip(axes, [("fresh", "Fresh test set (100 papers)"),
                                       ("original", "Original test set (100 papers)")]):
    ax.set_facecolor(SURFACE)
    for i, (key, _) in enumerate(FIELDS):
        for j, (series, color) in enumerate([("top1", S1), ("hier", S2)]):
            vals = data[setname][key][series]
            m = sum(vals) / len(vals)
            x = i + (j - 0.5) * (w + 0.03)
            ax.bar(x, m, w, color=color, edgecolor=SURFACE, linewidth=1, zorder=2)
            ax.plot([x, x], [min(vals), max(vals)], color=INK, linewidth=1.2, zorder=3)
            if series == "hier":
                ax.text(x, max(vals) + 0.02, f"{m:.2f}", ha="center", va="bottom",
                        color=INK, fontsize=9)
    ax.set_xticks(range(len(FIELDS)))
    ax.set_xticklabels([lab for _, lab in FIELDS], color=INK2)
    ax.set_title(title, color=INK, fontsize=11, loc="left")
    ax.set_ylim(0, 1.08)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8, zorder=0)
    ax.tick_params(colors=INK2, length=0)
    for sp in ax.spines.values():
        sp.set_visible(False)
axes[0].set_ylabel("Share of papers found", color=INK2)
handles = [plt.Rectangle((0, 0), 1, 1, color=S1), plt.Rectangle((0, 0), 1, 1, color=S2)]
fig.legend(handles, ["Main value only", "Search tags incl. parent ontology terms"],
           loc="upper left", bbox_to_anchor=(0.005, 0.935), ncol=2, frameon=False, labelcolor=INK)
fig.suptitle("Search recall: is the paper found by its BugSigDB-curated value?",
             x=0.01, y=0.985, ha="left", color=INK, fontsize=12)
fig.text(0.01, 0.01, "PubMed data only, gemini-2.5-flash. Bars: mean of 3 runs; "
         "lines: min-max. Labels: tags incl. parent terms.", color=INK2, fontsize=8.5)
fig.tight_layout(rect=(0, 0.04, 1, 0.87))
fig.savefig(sys.argv[1], dpi=160, facecolor=SURFACE)
