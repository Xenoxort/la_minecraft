"""Plot the cell outcomes and the primary matched interaction."""
import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt

NAMES = {"fixed": "Fixed handoffs", "peer": "Self-organizing", "leader": "Orchestrated"}
COLORS = {"fixed": "#596273", "peer": "#00736c", "leader": "#994a22"}


def render(data, stem):
    fig, (left, right) = plt.subplots(1, 2, figsize=(10.4, 4.4), width_ratios=(1.0, 1.12), layout="constrained")
    for idx, (mode, label) in enumerate(NAMES.items()):
        y = [data["groups"][f"{mode}-{env}"]["mean_orders"] for env in ("normal", "outage")]
        left.plot([0, 1], y, "o-", linewidth=2, color=COLORS[mode], label=label, zorder=4 - idx)
    left.set(xticks=[0, 1], xticklabels=["Predictable kitchen", "Assembly outage"],
             xlim=(-.12, 1.12), ylim=(0, 10.4), ylabel="Mean orders delivered by 360 s (out of 10)",
             title="Verified deliveries")
    left.legend(loc="lower left", frameon=False)
    pairs = data["contrasts_orders"]
    series = [pairs[f"leader_minus_peer_{x}"] for x in ("normal", "outage", "interaction")]
    widest = max(1.0, max(abs(v) for row in series for v in [*row["interval"], *row["values"]]))
    for i, row in enumerate(series):
        midpoint = row["mean"]
        spread = [[midpoint - row["interval"][0]], [row["interval"][1] - midpoint]]
        offsets = [((j * 13) % 11 - 5) * .017 for j in range(len(row["values"]))]
        right.scatter(row["values"], [i + dy for dy in offsets], color="#6d8799", alpha=.53, s=15)
        right.errorbar(midpoint, i, xerr=spread, fmt="o", color="#232b36", markersize=6, capsize=5)
    right.axvline(0, color="#7f8790", linewidth=1, linestyle="--")
    right.set(yticks=[0, 1, 2], yticklabels=["Predictable", "Outage", "Outage − predictable"],
              xlim=(-widest * 1.15, widest * 1.15), ylim=(2.5, -.5),
              xlabel="Extra orders with an orchestrator", title="Orchestrated minus self-organizing")
    for ax in (left, right):
        ax.spines[["top", "right"]].set_visible(False)
    left.grid(axis="y", alpha=.24)
    right.grid(axis="x", alpha=.24)
    fig.suptitle("Hell’s Kitchen handoffs across ten matched menu seeds", fontsize=15)
    for ext in ("pdf", "png"):
        fig.savefig(stem.with_suffix("." + ext), dpi=180, facecolor="white")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary", type=Path)
    parser.add_argument("output_stem", type=Path)
    args = parser.parse_args()
    render(json.loads(args.summary.read_text()), args.output_stem)
