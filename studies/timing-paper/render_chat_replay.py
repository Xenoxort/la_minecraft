"""Render an annotated replay of recorded trajectories and delivered chat."""
import argparse
from bisect import bisect_right
import json
from math import ceil
import os
from pathlib import Path
import subprocess
import textwrap

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT, FPS = 1280, 760, 20
INK, SOFT, GREEN = "#f3f5ee", "#a8bdc1", "#93dabb"
ACTORS = (("Andy_0", "#79bcff"), ("Jill_0", "#ffaf8e"))
MODES = (("always", "Always-open chat"), ("alternating", "20 s chat / 40 s closed"))


def read(path):
    return json.loads(path.read_text())


class Episode:
    def __init__(self, folder, judged):
        self.clock = read(folder / "start.json")
        self.start = self.clock["startMs"]
        finish = read(folder / "finish.json")
        self.stop = (finish["verifiedCompletionMs"] - self.start) / 1000
        rows = [json.loads(line) for line in (folder / "events.jsonl").read_text().splitlines()]
        self.states = [[r for r in rows if r["event"] == "state" and r["agent"] == actor]
                       for actor, _ in ACTORS]
        self.state_times = [[r["ms"] for r in states] for states in self.states]
        self.chat = judged["turns"]
        self.chat_times = [r["elapsed_s"] for r in self.chat]

    def state(self, actor, elapsed):
        stamps, rows = self.state_times[actor], self.states[actor]
        i = max(0, bisect_right(stamps, self.start + elapsed * 1000) - 1)
        return rows[i]

    def messages(self, elapsed):
        i = bisect_right(self.chat_times, elapsed)
        return self.chat[max(0, i - 2):i]


def paint(elapsed, episodes, targets, fonts):
    image = Image.new("RGB", (WIDTH, HEIGHT), "#0e1b24")
    d = ImageDraw.Draw(image)
    regular, small, panel, title = fonts

    def caption(x, y, value, color=INK, font=regular):
        d.text((x, y), value, fill=color, font=font)

    caption(30, 20, "MineCollab · Two bots, eight goals", font=title)
    caption(32, 73, "Woodwork  /  GPT-6 Luna  /  Matched runs", SOFT)
    caption(915, 74, "Recorded trace replay · 3× speed", SOFT)
    for column, (_, heading) in enumerate(MODES):
        episode = episodes[column]
        x = 30 + column * 620
        d.rounded_rectangle((x, 115, x + 600, 704), 13, fill="#172b35")
        caption(x + 19, 130, heading, font=panel)
        time = min(elapsed, episode.stop)
        mins, secs = divmod(int(time), 60)
        opened = any(a <= time * 1000 < b for a, b in episode.clock["chatWindowsMs"])
        label = "8/8 verified" if elapsed >= episode.stop else "Chat open" if opened else "Chat closed"
        caption(x + 19, 171, f"{mins}:{secs:02d}  ·  {label}", GREEN if opened or elapsed >= episode.stop else SOFT)
        left, top, tile = x + 23, 213, 6.4

        def position(px, pz):
            return left + (px + 24) * tile, top + (pz + 20) * tile

        d.rectangle((left, top, left + 48 * tile, top + 40 * tile), fill="#283f49", outline="#71929d", width=2)
        for tx in range(-20, 24, 4):
            d.line((*position(tx, -20), *position(tx, 20)), fill="#304a55")
        for tz in range(-16, 20, 4):
            d.line((*position(-24, tz), *position(24, tz)), fill="#304a55")
        for px, pz, label in [(-15, -7, "Chest"), (15, 7, "Chest"), (0, 0, "Table")]:
            xx, yy = position(px, pz)
            d.rounded_rectangle((xx - 5, yy - 5, xx + 5, yy + 5), 2, fill="#efc174")
            caption(xx + 9, yy - 10, label, "#e8d2a4", small)

        for actor, (agent, color) in enumerate(ACTORS):
            name = agent.removesuffix("_0")
            state = episode.state(actor, time)
            px, _, pz = state["position"]
            trail = []
            for second in range(max(0, int(time) - 9), int(time)):
                tx, _, tz = episode.state(actor, second)["position"]
                trail.append(position(tx, tz))
            xx, yy = position(px, pz)
            if trail:
                d.line([*trail, (xx, yy)], fill=color, width=2)
            d.ellipse((xx - 8, yy - 8, xx + 8, yy + 8), fill=color, outline="#0e1b24", width=2)

            ix, iy = x + 354, top + actor * 131
            inventory = state["inventory"]
            caption(ix, iy - 3, f"{name}  ·  {sum(inventory.get(t, 0) > 0 for t in targets[actor])}/4", color, panel)
            for n, goal in enumerate(targets[actor]):
                gy = iy + 34 + n * 20
                has = inventory.get(goal, 0) > 0
                d.ellipse((ix, gy + 4, ix + 8, gy + 12), fill=color if has else None, outline=color)
                caption(ix + 15, gy, goal.replace("_", " "), INK if has else SOFT, small)

        d.line((x + 20, 486, x + 580, 486), fill="#3b565f", width=1)
        caption(x + 20, 500, "DELIVERED CHAT", SOFT, small)
        for j, message in enumerate(episode.messages(time)):
            name = message["sender"].removesuffix("_0")
            color = dict(ACTORS)[message["sender"]]
            y = 533 + j * 81
            caption(x + 20, y, name, color)
            for k, line in enumerate(textwrap.wrap(message["message"], 64, max_lines=3, placeholder="…")):
                caption(x + 86, y + k * 19, line, INK, small)

    caption(31, 722, "Positions and inventories use recorded bot states. Each panel freezes at its server-verified finish.", SOFT, small)
    return image


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("study", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--font-dir", type=Path, required=True, help="Folder containing Arial.ttf and Arial Bold.ttf")
    args = ap.parse_args()
    judges = read(args.study / "chat-judgments.json")["episodes"]
    episodes = []
    for mode, _ in MODES:
        name = f"b01-woodwork-{mode}"
        judged = next(r for r in judges if r["cohort"] == "extended" and r["episode"] == name)
        episodes.append(Episode(args.study / "data" / "extended" / name, judged))
    targets = read(args.study / "long_scenarios.json")["woodwork"]["targets"]
    fonts = [ImageFont.truetype(str(args.font_dir / file), size) for file, size in
             (("Arial.ttf", 20), ("Arial.ttf", 17), ("Arial Bold.ttf", 26), ("Arial Bold.ttf", 40))]
    end = max(e.stop for e in episodes)
    frames = ceil((end / 3 + 3) * FPS)
    with subprocess.Popen([os.environ.get("FFMPEG", "ffmpeg"), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                           "-s", f"{WIDTH}x{HEIGHT}", "-r", str(FPS), "-i", "-", "-an",
                           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "19",
                           "-movflags", "+faststart", str(args.output)], stdin=subprocess.PIPE) as enc:
        for frame in range(frames):
            enc.stdin.write(paint(frame * 3 / FPS, episodes, targets, fonts).tobytes())
        enc.stdin.close()
        if enc.wait():
            raise RuntimeError("FFmpeg failed to encode the replay")


if __name__ == "__main__":
    main()
