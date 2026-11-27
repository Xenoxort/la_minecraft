"""Plot verified deliveries and matched effects of worked examples."""
import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt

ARMS = ("solo", "luna_examples", "astra_examples")
LABELS = ("From scratch", "Luna examples", "Astra examples")


def render(report, stem):
    fig, (left, right) = plt.subplots(1, 2, figsize=(10.8, 4.3), width_ratios=(1, 1.15), layout="constrained")
    means = [report["students"][arm]["mean_orders"] for arm in ARMS]
    bars = left.bar(range(3), means, width=.63, color=["#596573", "#08786e", "#a4512d"])
    left.bar_label(bars, labels=[f"{value:.2f}" for value in means], fontsize=9, padding=4)
    left.set(xticks=range(3), xticklabels=LABELS, ylim=(0, 4.25), title="Student deliveries",
             ylabel="Mean orders by six minutes (out of four)")

    effects = report["contrasts"]
    comparisons = ("luna_examples_minus_solo", "astra_examples_minus_solo", "astra_examples_minus_luna_examples")
    labels = ("Luna examples − from scratch", "Astra examples − from scratch", "Astra examples − Luna examples")
    rows = [effects[key]["count"] for key in comparisons]
    limits = [n for row in rows for n in [*row["values"], *row["interval"], 0]]
    for i, row in enumerate(rows):
        offsets = [((j * 17) % 13 - 6) * .020 for j in range(len(row["values"]))]
        right.scatter(row["values"], [i + delta for delta in offsets], s=20, color="#08786e", alpha=.50)
        middle = row["mean"]
        lower, upper = row["interval"]
        right.errorbar(middle, i, xerr=[[middle - lower], [upper - middle]],
                       fmt="o", color="#1e293b", capsize=5, markersize=7)
    right.axvline(0, color="#768191", linestyle="--", linewidth=1)
    right.set(yticks=range(3), yticklabels=labels, xlim=(min(limits)-.38,max(limits)+.38), ylim=(2.55,-.55),
              xlabel="Difference in delivered orders\nDots are kitchens. Bars show 95% intervals.",
              title="Paired differences")
    for ax in (left, right):
        ax.spines[["top","right"]].set_visible(False)
        ax.set_axisbelow(True)
    left.yaxis.grid(alpha=.20)
    right.xaxis.grid(alpha=.20)
    fig.suptitle("Worked examples on new Hell’s Kitchen recipes", fontsize=15)
    for ext in ("pdf", "png"):
        fig.savefig(stem.with_suffix("." + ext), dpi=180, facecolor="white")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    parser.add_argument("stem", type=Path)
    args = parser.parse_args()
    render(json.loads(args.results.read_text()), args.stem)
