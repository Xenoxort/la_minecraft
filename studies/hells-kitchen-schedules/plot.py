"""Plot inventory attainment over the ten Minecraft execution periods."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

MODES = {
    "A": ("Isolated", "#656a72", "o"),
    "B": ("Always open", "#11657f", "s"),
    "C": ("Frequent", "#8c4e96", "^"),
    "D": ("Infrequent", "#a74d2a", "D"),
    "E": ("Increasing", "#2a7754", "v"),
    "F": ("Decreasing", "#956919", "P"),
    "G": ("Adaptive", "#423d88", "X"),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    parser.add_argument("prefix", type=Path)
    args = parser.parse_args()
    result = json.loads(args.results.read_text())
    if result["pending"]:
        raise ValueError("Complete all conditions before plotting")
    groups = result["groups"]
    fig, axes = plt.subplots(1, 2, sharey=True, figsize=(10.6, 5.4))
    for ax, (regime, caption) in zip(axes, (("public", "All cards visible"), ("split", "Cards held by partners"))):
        for mode, (label, color, marker) in MODES.items():
            group = groups.get(f"{regime}-{mode}")
            if group:
                ax.plot(range(1, 11), group["goals_by_period"], color=color, marker=marker,
                        markersize=4.1, linewidth=1.5, linestyle="--" if mode == "G" else "-", label=f"{mode}  {label}")
        ax.set_title(caption, loc="left", fontsize=12, weight="bold")
        ax.set_xlabel("Execution period")
        ax.set_xticks(range(1, 11))
        ax.set_yticks(range(0, 9, 2))
        ax.set_ylim(-0.15, 8.2)
        ax.grid(axis="y", color="#dde6eb")
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("Mean goals in assigned inventories (of 8)")
    fig.subplots_adjust(top=0.78, bottom=0.23, left=0.095, right=0.97, wspace=0.14)
    fig.text(0.095, 0.927, "How quickly Minecraft teams met their cooking goals", fontsize=18, weight="bold")
    fig.text(0.095, 0.873, "Hell’s Kitchen · Equal team token ceiling · 2, 4, and 8 bots", fontsize=11, color="#435463")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower left", bbox_to_anchor=(0.082, 0.043), ncols=4, frameon=False)
    for kind in ("png", "pdf"):
        fig.savefig(args.prefix.with_suffix("." + kind), dpi=200)


if __name__ == "__main__":
    main()
