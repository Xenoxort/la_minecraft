"""Plot the selected plan quality and its range across the two puzzle seeds."""
import argparse
import json
from pathlib import Path
from statistics import mean

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

LABELS = {
    "A": "Isolated",
    "B": "Always open",
    "C": "Frequent",
    "D": "Infrequent",
    "E": "Increasing",
    "F": "Decreasing",
    "G": "Adaptive",
}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("results", type=Path)
    ap.add_argument("output", type=Path, help="Output prefix")
    args = ap.parse_args()
    rows = json.loads(args.results.read_text())["episodes"]
    modes = [mode for mode in LABELS if any(r["cell"][3] == mode for r in rows)]
    fig, axes = plt.subplots(1, 2, sharey=True, figsize=(10.6, 5.8))
    for ax, regime, title in zip(axes, ("public", "distributed"), ("All rules visible", "Rules split across agents")):
        for i, (n, marker, color) in enumerate(((2, "o", "#186681"), (4, "D", "#835589"), (8, "^", "#a04526"))):
            for j, mode in enumerate(modes):
                values = [r["selected_quality"] for r in rows if tuple(r["cell"][1:]) == (regime, n, mode)]
                y = j + (i - 1) * 0.215
                ax.hlines(y, min(values), max(values), color=color, linewidth=1.25, alpha=0.68)
                ax.scatter(mean(values), y, s=34, marker=marker, color=color, zorder=3,
                           label=f"{n} agents" if j == 0 else None)
        ax.set_title(title, loc="left", fontsize=12, weight="bold", pad=9)
        ax.set_xticks([0, 0.25, 0.5, 0.75, 1], labels=["0%", "25%", "50%", "75%", "100%"])
        ax.set_xlim(-0.025, 1.035)
        ax.grid(axis="x", color="#e3e9ec")
        ax.set_axisbelow(True)
        if "G" in modes:
            ax.axhspan(modes.index("G") - 0.45, modes.index("G") + 0.45, color="#f1f5f7", zorder=0)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.spines["bottom"].set_color("#a0aeba")
        ax.tick_params(left=False, bottom=False, labelsize=9)
    axes[0].set_yticks(range(len(modes)), [f"{mode}   {LABELS[mode]}" for mode in modes])
    axes[0].set_ylim(len(modes) - 0.52, -0.52)
    fig.subplots_adjust(left=0.16, right=0.97, top=0.77, bottom=0.18, wspace=0.12)
    fig.text(0.16, 0.932, "Communication timing and team solution quality", fontsize=18, weight="bold")
    fig.text(0.16, 0.877, "Selected plan benefit as a share of the exact optimum", fontsize=11, color="#425568")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower left", bbox_to_anchor=(0.145, 0.095), ncols=3, frameon=False)
    fig.text(0.16, 0.066, "Points show means and lines span two puzzle seeds. Infeasible plans score zero.",
             fontsize=9, color="#425568")
    for extension in ("png", "pdf"):
        fig.savefig(args.output.with_suffix("." + extension), dpi=200)


if __name__ == "__main__":
    main()
